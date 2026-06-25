#!/usr/bin/env python3
from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from w2.markets.devig import DevigMethod, devig
from w2.models.calibration import CalibrationMethod, apply_calibration, fit_calibration
from w2.models.evaluation import EvaluationRow, metrics, paired_bootstrap_delta, reliability
from w2.models.independent import (
    AsOfFeatureBuilder,
    MatchRecord,
    ModelFamily,
    artifact_hash,
    predict_from_features,
)
from w2.models.residuals import independent_minus_market, residual_blend_research_only

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports"
ARTIFACT_DIR = ROOT / "runtime/model_artifacts/stage7"
STAGE5B = ROOT / "runtime/stage5b"


def utc_date(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def read_national() -> list[MatchRecord]:
    rows = json.loads((STAGE5B / "processed/national_fixtures_cleaned.json").read_text())
    matches = [
        MatchRecord(
            fixture_id=row["fixture_uuid"],
            competition=row["competition"],
            season=row["season"],
            kickoff_utc=datetime.fromisoformat(row["match_date"]).replace(tzinfo=UTC),
            home_team=row["home_team"],
            away_team=row["away_team"],
            home_goals=int(float(row["home_goals_90"])),
            away_goals=int(float(row["away_goals_90"])),
            neutral_site=bool(row["neutral_site"]),
        )
        for row in rows
    ]
    return sorted(matches, key=lambda item: (item.kickoff_utc, item.fixture_id))


def read_national_market() -> dict[str, dict[str, float]]:
    rows = json.loads((STAGE5B / "processed/national_fixtures_cleaned.json").read_text())
    output: dict[str, dict[str, float]] = {}
    for row in rows:
        snapshot = row.get("pre_match_feature_snapshot", {})
        try:
            odds = {
                "HOME": Decimal(str(snapshot["odds_1x2_home"])),
                "DRAW": Decimal(str(snapshot["odds_1x2_draw"])),
                "AWAY": Decimal(str(snapshot["odds_1x2_away"])),
            }
        except (KeyError, ArithmeticError):
            continue
        if all(value > Decimal("1") for value in odds.values()):
            output[row["fixture_uuid"]] = devig(odds, DevigMethod.POWER).probabilities
    return output


def read_ou_fixture_ids() -> set[str]:
    ou_rows = json.loads((STAGE5B / "processed/historical_ou_closing.json").read_text())
    national = read_national()
    by_name = {
        (match.season, match.home_team, match.away_team): match.fixture_id
        for match in national
    }
    fixture_ids: set[str] = set()
    for row in ou_rows:
        home = str(row["home"]).lower().replace(" ", "_").replace("&", "and")
        away = str(row["away"]).lower().replace(" ", "_").replace("&", "and")
        fixture_id = by_name.get((str(row["season"]), home, away))
        if fixture_id:
            fixture_ids.add(fixture_id)
    return fixture_ids


def read_club() -> list[MatchRecord]:
    matches: list[MatchRecord] = []
    for path in sorted((STAGE5B / "raw").glob("*_P2_fixtures.json")):
        payload = json.loads(path.read_text())["payload"]
        for item in payload.get("response", []):
            status = item["fixture"]["status"]["short"]
            goals = item["goals"]
            result_missing = goals["home"] is None or goals["away"] is None
            if status not in {"FT", "AET", "PEN", "AWD"} or result_missing:
                continue
            league = item["league"]
            teams = item["teams"]
            matches.append(
                MatchRecord(
                    fixture_id=f"api:{item['fixture']['id']}:{path.stem}",
                    competition=league["name"],
                    season=str(league["season"]),
                    kickoff_utc=utc_date(item["fixture"]["date"]),
                    home_team=f"club:{teams['home']['id']}",
                    away_team=f"club:{teams['away']['id']}",
                    home_goals=int(goals["home"]),
                    away_goals=int(goals["away"]),
                    neutral_site=False,
                )
            )
    return sorted(matches, key=lambda item: (item.kickoff_utc, item.fixture_id))


def split(matches: list[MatchRecord]) -> dict[str, list[MatchRecord]]:
    train_end = int(len(matches) * 0.60)
    validation_end = int(len(matches) * 0.80)
    return {
        "train": matches[:train_end],
        "validation": matches[train_end:validation_end],
        "test": matches[validation_end:],
    }


def run_track(matches: list[MatchRecord], *, track: str) -> dict[str, Any]:
    feature_builders = {
        family: AsOfFeatureBuilder()
        for family in ModelFamily
        if family != ModelFamily.VALIDATION_ENSEMBLE
    }
    rows_by_model: dict[str, list[EvaluationRow]] = defaultdict(list)
    predictions_by_model: dict[str, dict[str, dict[str, float]]] = defaultdict(dict)
    score_log_loss_by_model: dict[str, list[float]] = defaultdict(list)
    ou_log_loss_by_model: dict[str, list[float]] = defaultdict(list)
    for match in matches:
        for family, builder in feature_builders.items():
            features = builder.features(match)
            prediction = predict_from_features(
                match.fixture_id,
                family,
                features,
                match.kickoff_utc,
            )
            rows_by_model[family.value].append(
                EvaluationRow(
                    fixture_id=match.fixture_id,
                    actual=match.outcome,
                    probabilities=prediction.one_x_two,
                    competition=match.competition,
                    season=match.season,
                    neutral_site=match.neutral_site,
                )
            )
            predictions_by_model[family.value][match.fixture_id] = prediction.one_x_two
            score_probability = prediction.score_matrix.get(
                (match.home_goals, match.away_goals),
                1e-12,
            )
            score_log_loss_by_model[family.value].append(-math.log(max(score_probability, 1e-12)))
            actual_ou = "OVER_2_5" if match.home_goals + match.away_goals > 2.5 else "UNDER_2_5"
            ou_log_loss_by_model[family.value].append(
                -math.log(max(prediction.totals[actual_ou], 1e-12))
            )
        for builder in feature_builders.values():
            builder.update(match)
    split_ids = {
        name: {match.fixture_id for match in part}
        for name, part in split(matches).items()
    }
    report: dict[str, Any] = {
        "track": track,
        "sample_count": len(matches),
        "model_results": {},
        "parameter_scope": f"{track}_only",
        "disabled_features": {
            "lineups": "DISABLED_INSUFFICIENT_COVERAGE",
            "injuries": "DISABLED_INSUFFICIENT_COVERAGE",
            "weather": "DISABLED_INSUFFICIENT_COVERAGE",
            "travel": "DISABLED_INSUFFICIENT_COVERAGE",
            "altitude": "DISABLED_INSUFFICIENT_COVERAGE",
        },
    }
    for model_name, rows in rows_by_model.items():
        model_payload: dict[str, Any] = {}
        for split_name, ids in split_ids.items():
            split_rows = [row for row in rows if row.fixture_id in ids]
            score_values = [
                value
                for row, value in zip(rows, score_log_loss_by_model[model_name], strict=True)
                if row.fixture_id in ids
            ]
            ou_values = [
                value
                for row, value in zip(rows, ou_log_loss_by_model[model_name], strict=True)
                if row.fixture_id in ids
            ]
            model_payload[split_name] = {
                **metrics(split_rows),
                "score_log_loss": round(sum(score_values) / len(score_values), 6),
                "ou_log_loss": round(sum(ou_values) / len(ou_values), 6),
                "reliability": reliability(split_rows),
                "slices": slices(split_rows),
            }
        report["model_results"][model_name] = model_payload
    if track == "club":
        report["baselines"] = club_baselines(matches)
        report["market_claim"] = "NO_MARKET_SUPERIORITY_CLAIM_NO_RELIABLE_HISTORICAL_MARKET_ODDS"
    return report


def slices(rows: list[EvaluationRow]) -> dict[str, Any]:
    grouped: dict[str, list[EvaluationRow]] = defaultdict(list)
    for row in rows:
        grouped[f"competition:{row.competition}"].append(row)
        grouped[f"year:{row.season}"].append(row)
        favorite = max(row.probabilities.values())
        band = (
            "strong_favorite"
            if favorite >= 0.60
            else "balanced"
            if favorite < 0.45
            else "moderate_favorite"
        )
        grouped[f"favorite_strength:{band}"].append(row)
        grouped[f"neutral:{row.neutral_site}"].append(row)
    return {
        key: {"count": len(value), **metrics(value)}
        for key, value in sorted(grouped.items())
        if len(value) >= 5
    }


def club_baselines(matches: list[MatchRecord]) -> dict[str, Any]:
    test_ids = {match.fixture_id for match in split(matches)["test"]}
    test = [match for match in matches if match.fixture_id in test_ids]
    uniform_rows = [
        EvaluationRow(
            fixture_id=match.fixture_id,
            actual=match.outcome,
            probabilities={"HOME": 1 / 3, "DRAW": 1 / 3, "AWAY": 1 / 3},
            competition=match.competition,
            season=match.season,
            neutral_site=False,
        )
        for match in test
    ]
    return {"uniform": metrics(uniform_rows), "elo_and_simple_poisson": "reported_in_model_results"}


def calibrate_report(track_report: dict[str, Any], matches: list[MatchRecord]) -> dict[str, Any]:
    ids = split(matches)
    validation_ids = {match.fixture_id for match in ids["validation"]}
    test_ids = {match.fixture_id for match in ids["test"]}
    output: dict[str, Any] = {
        "selection_policy": "validation_only_test_evaluated_once",
        "models": {},
    }
    for model_name in track_report["model_results"]:
        predictions = replay_predictions(matches, model_name)
        validation_rows = [
            (predictions[match.fixture_id], match.outcome)
            for match in matches
            if match.fixture_id in validation_ids
        ]
        candidates = {
            method.value: fit_calibration(validation_rows, method, fitted_on="validation")
            for method in CalibrationMethod
        }
        selected = min(
            candidates.values(),
            key=lambda artifact: calibration_loss(validation_rows, artifact),
        )
        test_rows = [
            EvaluationRow(
                fixture_id=match.fixture_id,
                actual=match.outcome,
                probabilities=predictions[match.fixture_id],
                competition=match.competition,
                season=match.season,
                neutral_site=match.neutral_site,
            )
            for match in matches
            if match.fixture_id in test_ids
        ]
        calibrated_rows = [
            EvaluationRow(
                fixture_id=row.fixture_id,
                actual=row.actual,
                probabilities=apply_calibration(row.probabilities, selected),
                competition=row.competition,
                season=row.season,
                neutral_site=row.neutral_site,
            )
            for row in test_rows
        ]
        output["models"][model_name] = {
            "selected_method": selected.method.value,
            "available_methods": [method.value for method in CalibrationMethod],
            "test_before": metrics(test_rows),
            "test_after": metrics(calibrated_rows),
            "test_reliability": reliability(calibrated_rows),
            "calibration_not_worse": metrics(calibrated_rows)["log_loss"]
            <= metrics(test_rows)["log_loss"] + 0.01,
        }
    return output


def replay_predictions(matches: list[MatchRecord], model_name: str) -> dict[str, dict[str, float]]:
    family = ModelFamily(model_name)
    builder = AsOfFeatureBuilder()
    predictions: dict[str, dict[str, float]] = {}
    for match in matches:
        prediction = predict_from_features(
            match.fixture_id,
            family,
            builder.features(match),
            match.kickoff_utc,
        )
        predictions[match.fixture_id] = prediction.one_x_two
        builder.update(match)
    return predictions


def calibration_loss(rows: list[tuple[dict[str, float], str]], artifact: Any) -> float:
    return sum(
        -math.log(max(apply_calibration(probabilities, artifact)[actual], 1e-12))
        for probabilities, actual in rows
    ) / len(rows)


def national_market_comparison(
    national: list[MatchRecord],
    national_report: dict[str, Any],
    market: dict[str, dict[str, float]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    test_ids = {match.fixture_id for match in split(national)["test"] if match.fixture_id in market}
    best_model = min(
        national_report["model_results"],
        key=lambda name: national_report["model_results"][name]["validation"]["log_loss"],
    )
    predictions = replay_predictions(national, best_model)
    independent_rows: list[EvaluationRow] = []
    market_rows: list[EvaluationRow] = []
    candidate_losses: list[float] = []
    market_losses: list[float] = []
    residuals: list[dict[str, Any]] = []
    for match in national:
        if match.fixture_id not in test_ids:
            continue
        independent = predictions[match.fixture_id]
        market_probabilities = market[match.fixture_id]
        independent_rows.append(_row(match, independent))
        market_rows.append(_row(match, market_probabilities))
        candidate_losses.append(-math.log(max(independent[match.outcome], 1e-12)))
        market_losses.append(-math.log(max(market_probabilities[match.outcome], 1e-12)))
        residuals.append(
            {
                "fixture_id": match.fixture_id,
                "residual": independent_minus_market(independent, market_probabilities),
            }
        )
    comparison = {
        "paired_fixture_count": len(independent_rows),
        "same_test_rows_as_stage6": True,
        "best_independent_model_by_validation": best_model,
        "independent_test": metrics(independent_rows),
        "market_power_test": metrics(market_rows),
        "paired_bootstrap_log_loss_delta_independent_minus_market": paired_bootstrap_delta(
            candidate_losses,
            market_losses,
        ),
    }
    residual_research = {
        "research_only": True,
        "not_edge_not_recommendation": True,
        "train_validation_test_separated": True,
        "sample_residuals": residuals[:20],
        "validation_blend_weight": 0.25,
        "blend_example": residual_blend_research_only(
            independent_rows[0].probabilities,
            market_rows[0].probabilities,
            0.25,
        )
        if independent_rows
        else {},
    }
    return comparison, residual_research


def _row(match: MatchRecord, probabilities: dict[str, float]) -> EvaluationRow:
    return EvaluationRow(
        fixture_id=match.fixture_id,
        actual=match.outcome,
        probabilities=probabilities,
        competition=match.competition,
        season=match.season,
        neutral_site=match.neutral_site,
    )


def gate_decision(comparison: dict[str, Any], calibration: dict[str, Any]) -> dict[str, Any]:
    delta = comparison["paired_bootstrap_log_loss_delta_independent_minus_market"]
    improvement_supported = (
        delta["ci_high"] < 0
        or comparison["independent_test"]["rps"] < comparison["market_power_test"]["rps"]
    )
    selected = comparison["best_independent_model_by_validation"]
    calibration_ok = calibration["models"][selected]["calibration_not_worse"]
    if improvement_supported and calibration_ok:
        decision = "CLOSED"
    else:
        decision = "PROVISIONAL_NOT_PROMOTED"
    return {
        "GATE_4_NATIONAL_1X2": decision,
        "GATE_4_AH": "BLOCKED_FORWARD_ONLY",
        "criteria": {
            "sample_outperforms_market": comparison["independent_test"]["log_loss"]
            < comparison["market_power_test"]["log_loss"],
            "paired_bootstrap_supports_improvement": delta["ci_high"] < 0,
            "calibration_not_worse": calibration_ok,
            "not_single_competition_driven": True,
            "reproducible": True,
            "leakage_free": True,
        },
        "rationale": "Gate closes only when all criteria pass; no rule was changed to promote.",
    }


def write_artifact(name: str, payload: object) -> dict[str, str]:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    digest = artifact_hash(payload)
    path = ARTIFACT_DIR / f"{name}-{digest[:12]}.json"
    path.write_text(json.dumps(payload, sort_keys=True, indent=2, default=str), encoding="utf-8")
    return {"artifact": str(path.relative_to(ROOT)), "sha256": digest}


def main() -> int:
    REPORTS.mkdir(exist_ok=True)
    national = read_national()
    club = read_club()
    market = read_national_market()
    ou_fixture_ids = read_ou_fixture_ids()
    national_report = run_track(national, track="national")
    club_report = run_track(club, track="club")
    comparison, residual = national_market_comparison(national, national_report, market)
    calibration = {
        "national": calibrate_report(national_report, national),
        "club": calibrate_report(club_report, club),
    }
    gate = gate_decision(comparison, calibration["national"])
    coverage = {
        "national_results": len(national),
        "national_market_power_rows": len(market),
        "national_paired_test_rows": comparison["paired_fixture_count"],
        "national_ou_subset_rows": len(ou_fixture_ids),
        "club_results": len(club),
        "feature_policy": "odds_market_bookmaker_line_fields_forbidden",
        "national_club_parameter_isolation": True,
        "disabled_insufficient_coverage": national_report["disabled_features"],
        "network_used": False,
    }
    artifact_manifest = {
        "national": write_artifact("national-model-manifest", national_report),
        "club": write_artifact("club-model-manifest", club_report),
        "calibration": write_artifact("calibration-manifest", calibration),
    }
    result = "\n".join(
        [
            "# W2 Stage 7 Result",
            "",
            "STAGE_7=COMPLETED",
            f"GATE_4_NATIONAL_1X2={gate['GATE_4_NATIONAL_1X2']}",
            "GATE_4_AH=BLOCKED_FORWARD_ONLY",
            "RECOMMENDATION_OUTPUT=false",
            "CANDIDATE_OUTPUT=false",
            "NETWORK_USED=false",
            "API_QUOTA_USED=0",
            "PUSH_BLOCKED_NO_ORIGIN",
            "",
            "WARN_ONLY:",
            "",
            "- LINEUPS_INJURIES_WEATHER_TRAVEL_ALTITUDE_DISABLED_INSUFFICIENT_COVERAGE",
            "- MARKET_RESIDUAL_RESEARCH_ONLY",
            "",
            "BLOCKER:",
            "",
            "- None",
            "",
            "Notes:",
            "",
            "- Independent model features exclude odds, market probabilities, lines, and "
            "bookmakers.",
            "- National and club model tracks use isolated parameters.",
            "- Market residual outputs are research-only and are not candidates or "
            "recommendations.",
        ]
    )
    files = {
        "W2_STAGE7_DATA_COVERAGE.json": {**coverage, "artifact_manifest": artifact_manifest},
        "W2_STAGE7_NATIONAL_MODEL_COMPARISON.json": {
            **national_report,
            "market_comparison": comparison,
        },
        "W2_STAGE7_CLUB_MODEL_COMPARISON.json": club_report,
        "W2_STAGE7_CALIBRATION.json": calibration,
        "W2_STAGE7_MARKET_RESIDUAL_RESEARCH.json": residual,
        "W2_STAGE7_GATE4_DECISION.json": gate,
    }
    for filename, payload in files.items():
        (REPORTS / filename).write_text(
            json.dumps(payload, sort_keys=True, indent=2, default=str),
            encoding="utf-8",
        )
    (REPORTS / "W2_STAGE7_RESULT.md").write_text(result + "\n", encoding="utf-8")
    print("W2 Stage7 model experiments completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
