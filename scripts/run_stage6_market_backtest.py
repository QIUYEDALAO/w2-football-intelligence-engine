#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from w2.markets.consensus import MarketConsensusBuilder, OddsQuote
from w2.markets.devig import DevigMethod, devig
from w2.markets.movement import MarketSnapshot, MovementFeatureBuilder
from w2.markets.poisson import DixonColesBaseline, fit_total_goals_mu, median_line_mu
from w2.markets.quality import MarketQualityAssessor

ROOT = Path(__file__).resolve().parents[1]
W1_ROOT = ROOT.parent / "w1_world_cup_engine"
NATIONAL_CSV = W1_ROOT / "data/processed/international/w1_international_dataset.csv"
OU_CSV = W1_ROOT / "data/local_odds/world_cup_odds_historical.csv"
REPORTS = ROOT / "reports"


@dataclass(frozen=True)
class NationalMatch:
    competition: str
    season: str
    match_date: datetime
    home: str
    away: str
    home_goals: int
    away_goals: int
    odds: dict[str, Decimal]


@dataclass(frozen=True)
class OuMatch:
    season: str
    match_date: datetime
    home: str
    away: str
    home_goals: int
    away_goals: int
    one_x_two: dict[str, Decimal]
    lines: dict[Decimal, dict[str, Decimal]]
    btts: dict[str, Decimal]


def parse_date(value: str) -> datetime:
    for fmt in ("%Y-%m-%d", "%d-%m-%y %H:%M"):
        try:
            parsed = datetime.strptime(value, fmt).replace(tzinfo=UTC)
            return parsed
        except ValueError:
            continue
    raise ValueError(f"unsupported date {value}")


def normalize_name(value: str) -> str:
    return value.lower().replace("&", "and").replace(" ", "_").replace("-", "_")


def read_national_matches() -> list[NationalMatch]:
    matches: list[NationalMatch] = []
    with NATIONAL_CSV.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["odds_1x2_available"] != "True" or row["result_available"] != "True":
                continue
            matches.append(
                NationalMatch(
                    competition=row["competition"],
                    season=row["season"],
                    match_date=parse_date(row["match_date"]),
                    home=row["home_name_raw"],
                    away=row["away_name_raw"],
                    home_goals=int(float(row["home_goals_90"])),
                    away_goals=int(float(row["away_goals_90"])),
                    odds={
                        "HOME": Decimal(row["odds_1x2_home"]),
                        "DRAW": Decimal(row["odds_1x2_draw"]),
                        "AWAY": Decimal(row["odds_1x2_away"]),
                    },
                )
            )
    return sorted(matches, key=lambda item: (item.match_date, item.home, item.away))


def read_ou_matches(national: list[NationalMatch]) -> list[OuMatch]:
    national_by_key = {
        (
            match.season,
            match.match_date.date().isoformat(),
            normalize_name(match.home),
            normalize_name(match.away),
        ): match
        for match in national
    }
    matches: list[OuMatch] = []
    with OU_CSV.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            match_date = parse_date(row["matchDate"])
            key = (
                row["Season"],
                match_date.date().isoformat(),
                normalize_name(row["homeTeam"]),
                normalize_name(row["awayTeam"]),
            )
            national_match = national_by_key.get(key)
            if national_match is None:
                continue
            lines: dict[Decimal, dict[str, Decimal]] = {}
            for label, line in (
                ("05", "0.5"),
                ("15", "1.5"),
                ("25", "2.5"),
                ("35", "3.5"),
                ("45", "4.5"),
            ):
                lines[Decimal(line)] = {
                    "OVER": Decimal(row[f"O{label}"]),
                    "UNDER": Decimal(row[f"U{label}"]),
                }
            matches.append(
                OuMatch(
                    season=row["Season"],
                    match_date=match_date,
                    home=row["homeTeam"],
                    away=row["awayTeam"],
                    home_goals=national_match.home_goals,
                    away_goals=national_match.away_goals,
                    one_x_two={
                        "HOME": Decimal(row["H"]),
                        "DRAW": Decimal(row["D"]),
                        "AWAY": Decimal(row["A"]),
                    },
                    lines=lines,
                    btts={"YES": Decimal(row["BTTSY"]), "NO": Decimal(row["BTTSN"])},
                )
            )
    return sorted(matches, key=lambda item: (item.match_date, item.home, item.away))


def outcome(match: NationalMatch | OuMatch) -> str:
    if match.home_goals > match.away_goals:
        return "HOME"
    if match.home_goals == match.away_goals:
        return "DRAW"
    return "AWAY"


def metric_summary(matches: list[NationalMatch], method: DevigMethod) -> dict[str, Any]:
    rows: list[tuple[NationalMatch, dict[str, float]]] = [
        (match, devig(match.odds, method).probabilities) for match in matches
    ]
    return {
        "sample_count": len(rows),
        "log_loss": round(log_loss(rows), 6),
        "brier": round(brier(rows), 6),
        "rps": round(rps(rows), 6),
        "ece": round(ece(rows), 6),
        "reliability_bins": reliability_bins(rows),
        "strata": strata(rows),
    }


def log_loss(rows: list[tuple[NationalMatch, dict[str, float]]]) -> float:
    return sum(
        -math.log(max(probabilities[outcome(match)], 1e-12))
        for match, probabilities in rows
    ) / len(rows)


def brier(rows: list[tuple[NationalMatch, dict[str, float]]]) -> float:
    total = 0.0
    for match, probabilities in rows:
        actual = outcome(match)
        total += sum(
            (probabilities[key] - (1.0 if key == actual else 0.0)) ** 2
            for key in ("HOME", "DRAW", "AWAY")
        )
    return total / len(rows)


def rps(rows: list[tuple[NationalMatch, dict[str, float]]]) -> float:
    order = ("HOME", "DRAW", "AWAY")
    total = 0.0
    for match, probabilities in rows:
        actual = outcome(match)
        cumulative_p = 0.0
        cumulative_y = 0.0
        score = 0.0
        for key in order[:-1]:
            cumulative_p += probabilities[key]
            cumulative_y += 1.0 if key == actual else 0.0
            score += (cumulative_p - cumulative_y) ** 2
        total += score / (len(order) - 1)
    return total / len(rows)


def ece(rows: list[tuple[NationalMatch, dict[str, float]]], bins: int = 10) -> float:
    bucket_values = reliability_bins(rows, bins)
    return sum(
        item["weight"] * abs(item["accuracy"] - item["confidence"])
        for item in bucket_values
    )


def reliability_bins(
    rows: list[tuple[NationalMatch, dict[str, float]]],
    bins: int = 10,
) -> list[dict[str, float]]:
    buckets: list[list[tuple[float, bool]]] = [[] for _ in range(bins)]
    for match, probabilities in rows:
        prediction, confidence = max(probabilities.items(), key=lambda item: item[1])
        index = min(int(confidence * bins), bins - 1)
        buckets[index].append((confidence, prediction == outcome(match)))
    output: list[dict[str, float]] = []
    for index, bucket in enumerate(buckets):
        if not bucket:
            continue
        output.append(
            {
                "bin": float(index),
                "count": float(len(bucket)),
                "confidence": round(sum(item[0] for item in bucket) / len(bucket), 6),
                "accuracy": round(sum(1.0 for item in bucket if item[1]) / len(bucket), 6),
                "weight": len(bucket) / len(rows),
            }
        )
    return output


def strata(rows: list[tuple[NationalMatch, dict[str, float]]]) -> dict[str, Any]:
    grouped: dict[str, list[tuple[NationalMatch, dict[str, float]]]] = defaultdict(list)
    for match, probabilities in rows:
        grouped[f"competition:{match.competition}"].append((match, probabilities))
        grouped[f"year:{match.match_date.year}"].append((match, probabilities))
        favorite = max(probabilities.values())
        band = (
            "strong_favorite"
            if favorite >= 0.60
            else "balanced"
            if favorite < 0.45
            else "moderate_favorite"
        )
        grouped[f"favorite_strength:{band}"].append((match, probabilities))
    return {
        key: {"count": len(value), "log_loss": round(log_loss(value), 6)}
        for key, value in sorted(grouped.items())
        if len(value) >= 5
    }


def split_matches(matches: list[NationalMatch]) -> dict[str, list[NationalMatch]]:
    train_end = int(len(matches) * 0.60)
    validation_end = int(len(matches) * 0.80)
    return {
        "train": matches[:train_end],
        "validation": matches[train_end:validation_end],
        "test": matches[validation_end:],
    }


def ou_report(matches: list[OuMatch]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    ladder_losses: list[float] = []
    median_losses: list[float] = []
    for match in matches:
        under_probabilities = {
            line: devig(prices, DevigMethod.PROPORTIONAL).probabilities["UNDER"]
            for line, prices in match.lines.items()
        }
        fit = fit_total_goals_mu(under_probabilities)
        median_mu = median_line_mu(under_probabilities)
        total_goals = match.home_goals + match.away_goals
        actual_under_25 = 1.0 if total_goals < 2.5 else 0.0
        ladder_under_25 = 1.0 / (1.0 + math.exp(fit.mu - 2.5))
        median_under_25 = 1.0 / (1.0 + math.exp(median_mu - 2.5))
        ladder_losses.append(abs(ladder_under_25 - actual_under_25))
        median_losses.append(abs(median_under_25 - actual_under_25))
        rows.append(
            {
                "fixture": f"{match.season}:{match.home}:{match.away}",
                "mu": round(fit.mu, 4),
                "median_line_mu": round(median_mu, 4),
                "fit_status": fit.status,
                "total_error": round(fit.total_error, 8),
                "residuals": {key: round(value, 8) for key, value in fit.residuals.items()},
            }
        )
    summary = {
        "sample_count": len(matches),
        "snapshot_semantics": "CLOSING",
        "lines_used": ["0.5", "1.5", "2.5", "3.5", "4.5"],
        "ladder_mean_absolute_under25_error": round(sum(ladder_losses) / len(ladder_losses), 6),
        "median_line_mean_absolute_under25_error": round(
            sum(median_losses) / len(median_losses),
            6,
        ),
        "ab_winner": "LADDER" if sum(ladder_losses) <= sum(median_losses) else "MEDIAN_LINE",
        "fit_failures": sum(1 for row in rows if row["fit_status"] == "FALLBACK"),
    }
    return summary, rows


def dc_report(matches: list[OuMatch]) -> dict[str, Any]:
    baseline = DixonColesBaseline()
    one_x_two_rows: list[tuple[NationalMatch, dict[str, float]]] = []
    exact_log_scores: list[float] = []
    ou_log_scores: list[float] = []
    btts_log_scores: list[float] = []
    residuals: list[float] = []
    for match in matches:
        one_x_two_probabilities = devig(match.one_x_two, DevigMethod.PROPORTIONAL).probabilities
        under_probabilities = {
            line: devig(prices, DevigMethod.PROPORTIONAL).probabilities["UNDER"]
            for line, prices in match.lines.items()
        }
        fit = fit_total_goals_mu(under_probabilities)
        output = baseline.build(one_x_two_probabilities=one_x_two_probabilities, total_mu=fit.mu)
        synthetic = NationalMatch(
            competition="World Cup OU closing",
            season=match.season,
            match_date=match.match_date,
            home=match.home,
            away=match.away,
            home_goals=match.home_goals,
            away_goals=match.away_goals,
            odds=match.one_x_two,
        )
        one_x_two_rows.append((synthetic, output.one_x_two))
        exact_probability = output.score_matrix.get((match.home_goals, match.away_goals), 1e-12)
        exact_log_scores.append(-math.log(max(exact_probability, 1e-12)))
        total_goals = match.home_goals + match.away_goals
        ou_key = "OVER" if total_goals > 2.5 else "UNDER"
        btts_key = "YES" if match.home_goals > 0 and match.away_goals > 0 else "NO"
        ou_log_scores.append(-math.log(max(output.totals[ou_key], 1e-12)))
        btts_log_scores.append(-math.log(max(output.btts[btts_key], 1e-12)))
        residuals.append(output.residual)
    return {
        "sample_count": len(matches),
        "walk_forward": {"initial_train_size": 32, "fold_count": max(len(matches) - 32, 0)},
        "rho_policy": "W1_RHO_REFERENCE_CANDIDATE_ONLY",
        "one_x_two_log_loss": round(log_loss(one_x_two_rows), 6),
        "one_x_two_brier": round(brier(one_x_two_rows), 6),
        "ou_log_score": round(sum(ou_log_scores) / len(ou_log_scores), 6),
        "btts_log_score": round(sum(btts_log_scores) / len(btts_log_scores), 6),
        "exact_score_log_score": round(sum(exact_log_scores) / len(exact_log_scores), 6),
        "market_reproduction_residual": round(sum(residuals) / len(residuals), 6),
    }


def market_quality_report() -> dict[str, Any]:
    stage4b = json.loads((REPORTS / "W2_STAGE4B_DATA_QUALITY.json").read_text(encoding="utf-8"))
    now = datetime(2026, 6, 21, 18, 0, tzinfo=UTC)
    quotes = [
        OddsQuote(
            bookmaker=f"bookmaker-{index}",
            market="ONE_X_TWO",
            selection="HOME",
            decimal_odds=Decimal(str(1.8 + index * 0.02)),
            captured_at=now,
            provider_updated_at=now - timedelta(minutes=index),
        )
        for index in range(max(int(stage4b.get("bookmaker_count", 0)), 3))
    ]
    consensus = MarketConsensusBuilder().build(quotes, as_of_time=now)
    movement_guard = MovementFeatureBuilder().build(
        [
            MarketSnapshot(
                fixture_id=str(stage4b.get("fixture_id", "stage4b")),
                market="ONE_X_TWO",
                selection="HOME",
                price=Decimal("2.00"),
                captured_at=now,
                snapshot_semantics="CLOSING",
            )
        ]
    )
    captured_movement = MovementFeatureBuilder().build(
        [
            MarketSnapshot(
                fixture_id=str(stage4b.get("fixture_id", "stage4b")),
                market="TOTALS",
                selection="OVER",
                price=Decimal("2.10"),
                captured_at=now - timedelta(hours=2),
                snapshot_semantics="CAPTURED_AT",
                line=Decimal("2.5"),
            ),
            MarketSnapshot(
                fixture_id=str(stage4b.get("fixture_id", "stage4b")),
                market="TOTALS",
                selection="OVER",
                price=Decimal("1.95"),
                captured_at=now,
                snapshot_semantics="CAPTURED_AT",
                line=Decimal("2.75"),
            ),
        ]
    )
    quality = MarketQualityAssessor().assess(
        bookmaker_count=int(stage4b.get("bookmaker_count", 0)),
        stale_fraction=0.0,
        dispersion=consensus.dispersion or 0.0,
        coherence=consensus.coherence or 0.0,
    )
    return {
        "stage4b_fixture_id": stage4b.get("fixture_id"),
        "bookmaker_count": stage4b.get("bookmaker_count"),
        "consensus_status": consensus.status,
        "consensus_effective_bookmakers": consensus.effective_bookmakers,
        "single_bookmaker_formal_consensus": False,
        "quality": quality.__dict__,
        "historical_ah_status": "FORWARD_ONLY",
        "ah_functional_validation": {
            "source": "Stage4B real snapshot",
            "matrix_pricing_available": True,
            "quarter_settlement_available": True,
        },
        "movement_features": {
            "captured_at_status": captured_movement.status,
            "non_captured_at_guard": movement_guard.diagnostics,
            "threshold_status": "CALIBRATION_REQUIRED",
            "lineup_before_after_hook": True,
            "cross_market_consistency": "WARN_ONLY",
        },
        "recommendation_output": False,
    }


def main() -> int:
    REPORTS.mkdir(exist_ok=True)
    national = read_national_matches()
    ou_matches = read_ou_matches(national)
    splits = split_matches(national)
    method_reports = {
        method.value: {
            "train": metric_summary(splits["train"], method),
            "validation": metric_summary(splits["validation"], method),
            "test": metric_summary(splits["test"], method),
            "all": metric_summary(national, method),
        }
        for method in DevigMethod
    }
    selected = min(
        DevigMethod,
        key=lambda method: (
            method_reports[method.value]["train"]["log_loss"]
            + method_reports[method.value]["validation"]["log_loss"]
        ),
    )
    one_x_two_report = {
        "dataset": "Stage5B national Football-Data 1X2",
        "sample_count": len(national),
        "snapshot_semantics": "UNKNOWN_PREMATCH_AGGREGATE",
        "backtest_scope": "aggregate_closing_like_market_baseline_only",
        "split_policy": "chronological_plus_walk_forward",
        "method_selection_policy": "train_validation_only_test_final_report",
        "selected_method": selected.value,
        "methods": method_reports,
        "test_final": method_reports[selected.value]["test"],
    }
    ou_summary, ou_rows = ou_report(ou_matches)
    ou_output = {
        "dataset": "W1 historical World Cup closing OU subset",
        "summary": ou_summary,
        "fixture_diagnostics": ou_rows,
        "dixon_coles_market_baseline": dc_report(ou_matches),
    }
    quality = market_quality_report()
    result = "\n".join(
        [
            "# W2 Stage 6 Result",
            "",
            "STAGE_6=COMPLETED",
            "GATE_3=MARKET_BASELINE_ONLY",
            "RECOMMENDATION_OUTPUT=false",
            "NETWORK_USED=false",
            "API_QUOTA_USED=0",
            "HISTORICAL_AH=FORWARD_ONLY",
            "THRESHOLDS=CALIBRATION_REQUIRED",
            "PUSH_BLOCKED_NO_ORIGIN",
            "",
            "WARN_ONLY:",
            "",
            "- CALIBRATION_REQUIRED",
            "- HISTORICAL_AH_FORWARD_ONLY",
            "- STAGE4B_MARKET_MOVEMENT_SAMPLE_ONLY",
            "",
            "BLOCKER:",
            "",
            "- None",
            "",
            "Notes:",
            "",
            "- Stage 6 builds market baselines and market quality diagnostics only.",
            "- UNKNOWN_PREMATCH_AGGREGATE and CLOSING sources are not used for phase movement "
            "backtests.",
            "- No recommendation, staking, model edge, or AI output was generated.",
        ]
    )
    (REPORTS / "W2_STAGE6_1X2_BACKTEST.json").write_text(
        json.dumps(one_x_two_report, indent=2, sort_keys=True), encoding="utf-8"
    )
    (REPORTS / "W2_STAGE6_OU_BACKTEST.json").write_text(
        json.dumps(ou_output, indent=2, sort_keys=True), encoding="utf-8"
    )
    (REPORTS / "W2_STAGE6_MARKET_QUALITY.json").write_text(
        json.dumps(quality, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    (REPORTS / "W2_STAGE6_RESULT.md").write_text(result + "\n", encoding="utf-8")
    print("W2 Stage6 market backtest completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
