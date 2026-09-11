from __future__ import annotations

import json
import statistics
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from w2.domain.five_state_pricing import (
    SettlementDistribution,
    expected_value,
    validate_ev_inputs,
)
from w2.matchday.legacy_ev import adapt_legacy_value_row
from w2.matchday.temporal import TemporalStatus, parse_utc, temporal_context_from_manifest

RANKED_MARKETS = ("ONE_X_TWO", "ASIAN_HANDICAP", "TOTALS", "BTTS")


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def _q4(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _binary_distribution(probability: Decimal) -> dict[str, Decimal]:
    return {
        "full_win_probability": probability,
        "half_win_probability": Decimal("0"),
        "push_probability": Decimal("0"),
        "half_loss_probability": Decimal("0"),
        "full_loss_probability": Decimal("1") - probability,
    }


def _distribution_from_value_row(row: dict[str, Any]) -> dict[str, Decimal]:
    settlement = row.get("settlement_probabilities")
    keys = ("win", "half_win", "push", "half_loss", "loss")
    if not isinstance(settlement, dict) or set(settlement) != set(keys):
        raise ValueError("INVALID_PROBABILITY_KEYS")
    return dict(zip(
        SettlementDistribution.__dataclass_fields__,
        (_decimal(settlement[k]) for k in keys), strict=True,
    ))


def _fair_decimal(distribution: dict[str, Decimal]) -> Decimal | None:
    numerator = (
        distribution["full_loss_probability"]
        + Decimal("0.5") * distribution["half_loss_probability"]
    )
    denominator = (
        distribution["full_win_probability"]
        + Decimal("0.5") * distribution["half_win_probability"]
    )
    if denominator == 0:
        return None
    return (Decimal("1") + numerator / denominator).quantize(
        Decimal("0.0001"),
        rounding=ROUND_HALF_UP,
    )


def _expected_value(decimal_odds: Decimal, distribution: dict[str, Decimal]) -> Decimal:
    if set(distribution) != set(SettlementDistribution.__dataclass_fields__):
        raise ValueError("INVALID_PROBABILITY_KEYS")
    settlement = SettlementDistribution(**distribution)
    validate_ev_inputs(decimal_odds, settlement)
    return expected_value(decimal_odds, settlement)


def _grade(risk_ev: Decimal | None, *, data_quality: str, market_quality: str) -> tuple[str, str]:
    if risk_ev is None or data_quality == "BLOCKED" or market_quality == "BLOCKED":
        return ("X", "X")
    if risk_ev >= Decimal("0.05") and data_quality == "READY" and market_quality == "READY":
        raw = "A"
    elif risk_ev >= Decimal("0.025"):
        raw = "B"
    elif risk_ev > 0:
        raw = "C"
    else:
        raw = "D"
    return (raw, "C" if raw in {"A", "B"} else raw)


def _market_quality(
    rows: list[dict[str, Any]],
) -> tuple[str, list[str], Decimal | None, Decimal | None]:
    prices = [_decimal(row["odds_value"]) for row in rows if row.get("odds_value")]
    if len({row.get("bookmaker_name") for row in rows}) < 2:
        return ("BLOCKED", [], None, None)
    median = Decimal(str(statistics.median(float(price) for price in prices)))
    dispersion = (
        Decimal(str(statistics.pstdev(float(price) for price in prices)))
        if len(prices) > 1
        else Decimal("0")
    )
    devs = [abs(float(price - median)) for price in prices]
    mad = statistics.median(devs) if devs else 0.0
    outliers = []
    if mad:
        for row in rows:
            if abs(float(_decimal(row["odds_value"]) - median)) > 3 * mad:
                outliers.append(str(row.get("bookmaker_name")))
    return ("READY" if not outliers else "WATCH_ONLY", sorted(set(outliers)), median, dispersion)


def _low_correlation(primary: dict[str, Any], candidate: dict[str, Any]) -> bool:
    pair = {primary["market"], candidate["market"]}
    if pair == {"TOTALS", "BTTS"}:
        if {primary["selection"], candidate["selection"]} in [{"OVER", "YES"}, {"UNDER", "NO"}]:
            return False
    if pair == {"ONE_X_TWO", "ASIAN_HANDICAP"}:
        one_x_two = primary if primary["market"] == "ONE_X_TWO" else candidate
        ah = primary if primary["market"] == "ASIAN_HANDICAP" else candidate
        if one_x_two["selection"] in {"HOME", "ARGENTINA_WIN"} and ah["selection"] in {
            "HOME",
            "ARGENTINA",
        }:
            return False
    return True


@dataclass(frozen=True, kw_only=True)
class MatchdayFixtureCard:
    fixture_id: str
    fixture: dict[str, Any]
    card: dict[str, Any]
    market_ranking: list[dict[str, Any]]
    temporal: dict[str, Any]
    integrity: dict[str, Any]


class ResearchCardBuilder:
    def __init__(self, *, uncertainty_margin: Decimal = Decimal("0.035")) -> None:
        self.uncertainty_margin = uncertainty_margin

    def build_from_snapshot(
        self,
        snapshot_dir: Path,
        *,
        valuation_generated_at: datetime | None = None,
        integrity: dict[str, Any] | None = None,
    ) -> MatchdayFixtureCard:
        manifest = _load_json(snapshot_dir / "manifest.json", {})
        normalized = _load_json(snapshot_dir / "normalized_odds.json", {})
        model = _load_json(snapshot_dir / "model_output.json", {})
        quality = _load_json(snapshot_dir / "data_quality.json", {})
        raw_fixture = _load_json(snapshot_dir / "raw" / "01_fixture_detail.json", {})
        fixture_item = (raw_fixture.get("payload", {}).get("response") or [{}])[0]
        temporal = temporal_context_from_manifest(
            snapshot_id=snapshot_dir.name,
            manifest=manifest,
            valuation_generated_at=valuation_generated_at,
        )
        if temporal.temporal_status == TemporalStatus.INVALID_POST_KICKOFF_INPUT:
            data_quality = "BLOCKED"
        else:
            data_quality = str(quality.get("status", "WATCH_ONLY"))
        ranking = self._ranking(
            normalized_rows=normalized.get("rows", []),
            value_rows=model.get("value_rows", []),
            legacy_source=(
                str(snapshot_dir / "model_output.json")
                if "schema_version" not in model
                else None
            ),
            data_quality=data_quality,
        )
        positive = [row for row in ranking if row["action"] == "WATCH"]
        primary = positive[0] if positive else None
        secondary = next(
            (
                row
                for row in positive[1:]
                if primary is not None and _low_correlation(primary, row)
            ),
            None,
        )
        most_likely = max(
            (model.get("probabilities") or {}).items(),
            key=lambda item: float(item[1]),
            default=("UNKNOWN", 0),
        )[0]
        published = (
            primary["published_grade"]
            if primary
            else ("X" if data_quality == "BLOCKED" else "D")
        )
        action = "WATCH" if primary else ("BLOCKED" if published == "X" else "SKIP")
        card = {
            "fixture_id": str(manifest.get("fixture_id")),
            "most_likely_outcome": most_likely,
            "primary_market_direction": primary,
            "secondary_market_direction": secondary,
            "raw_research_grade": primary["raw_research_grade"] if primary else published,
            "published_grade": published,
            "action": action,
            "invalidation_conditions": [
                "source_captured_at_after_kickoff",
                "market_quality_blocked",
                "frozen_artifact_hash_mismatch",
                "formal_recommendation_disabled",
            ],
            "formal_recommendation": False,
            "candidate": False,
            "gate4_status": "PROVISIONAL_FORWARD_HOLDOUT_PENDING",
            "temporal_status": temporal.temporal_status.value,
            "postmatch_recompute_notice": (
                "基于赛前锁定数据的赛后重算，不代表赛前实时发布。"
                if temporal.recomputed_after_kickoff
                else None
            ),
        }
        fixture = {
            "fixture_id": str(manifest.get("fixture_id")),
            "competition_id": str(fixture_item.get("league", {}).get("id", "")),
            "competition_name": str(fixture_item.get("league", {}).get("name", "")),
            "stage": fixture_item.get("league", {}).get("round"),
            "kickoff_utc": temporal.kickoff_utc.isoformat(),
            "status": fixture_item.get("fixture", {}).get("status", {}).get("short", "UNKNOWN"),
            "home_team_id": str(fixture_item.get("teams", {}).get("home", {}).get("id", "")),
            "away_team_id": str(fixture_item.get("teams", {}).get("away", {}).get("id", "")),
            "home_team_name": fixture_item.get("teams", {}).get("home", {}).get("name"),
            "away_team_name": fixture_item.get("teams", {}).get("away", {}).get("name"),
            "venue": fixture_item.get("fixture", {}).get("venue", {}).get("name"),
            "published_grade": published,
            "primary_market": primary["market"] if primary else None,
            "primary_line": primary["line"] if primary else None,
            "primary_selection": primary["selection"] if primary else None,
            "primary_odds": primary["executable_decimal_odds"] if primary else None,
            "last_captured": temporal.source_captured_at.isoformat(),
            "data_health": data_quality,
        }
        return MatchdayFixtureCard(
            fixture_id=str(manifest.get("fixture_id")),
            fixture=fixture,
            card=card,
            market_ranking=ranking,
            temporal=temporal.as_dict(),
            integrity=integrity or {},
        )

    def _ranking(
        self,
        *,
        normalized_rows: list[dict[str, Any]],
        value_rows: list[dict[str, Any]],
        data_quality: str,
        legacy_source: str | None = None,
    ) -> list[dict[str, Any]]:
        ranking: list[dict[str, Any]] = []
        exact_risk: dict[int, Decimal] = {}
        for value in value_rows:
            if legacy_source is not None:
                value = adapt_legacy_value_row(value, source=legacy_source)
                if value["legacy_compatibility"]["status"] != "READY":
                    ranking.append({
                        "market": value.get("market"), "selection": value.get("selection"),
                        "line": value.get("line"), "raw_ev": None, "risk_adjusted_ev": None,
                        "status": "NOT_READY", "action": "BLOCKED", "published_grade": "X",
                        "formal_recommendation": False, "candidate": False,
                        "legacy_compatibility": value["legacy_compatibility"],
                    })
                    continue
            market = str(value.get("market"))
            selection = str(value.get("selection"))
            line = value.get("line")
            peer_rows = [
                row
                for row in normalized_rows
                if row.get("market_type") == market
                and row.get("canonical_selection") == selection
                and str(row.get("normalized_line")) == str(line)
                and not row.get("suspended")
                and not row.get("live")
            ]
            market_quality, outliers, median_price, dispersion = _market_quality(peer_rows)
            distribution = _distribution_from_value_row(value)
            executable = _decimal(value.get("executable_odds"))
            raw_ev = _expected_value(executable, distribution)
            risk_ev = raw_ev - self.uncertainty_margin
            fair = _fair_decimal(distribution)
            raw_grade, published_grade = _grade(
                risk_ev,
                data_quality=data_quality,
                market_quality=market_quality,
            )
            action = "WATCH" if published_grade in {"A", "B", "C"} else "SKIP"
            if published_grade == "X":
                action = "BLOCKED"
            exact_risk[len(ranking)] = risk_ev
            ranking.append(
                {
                    **(
                        {"legacy_compatibility": value["legacy_compatibility"]}
                        if legacy_source is not None
                        else {}
                    ),
                    "market": market,
                    "selection": selection,
                    "line": line,
                    "bookmaker": value.get("bookmaker_name") or value.get("bookmaker"),
                    "executable_decimal_odds": _q4(executable),
                    "hong_kong_odds": _q4(executable - Decimal("1")),
                    "model_fair_odds": str(fair) if fair else None,
                    "market_no_vig_odds": value.get("market_fair_odds"),
                    "settlement_distribution": {k: _q4(v) for k, v in distribution.items()},
                    "raw_ev": _q4(raw_ev),
                    "uncertainty_penalty": _q4(self.uncertainty_margin),
                    "risk_adjusted_ev": _q4(risk_ev),
                    "market_quality": market_quality,
                    "data_quality": data_quality,
                    "outlier_status": "OUTLIER" if outliers else "OK",
                    "outlier_bookmakers": outliers,
                    "freshness": "CAPTURED_AT",
                    "valid_bookmaker_count": len({row.get("bookmaker_name") for row in peer_rows}),
                    "consensus_median": str(median_price) if median_price else None,
                    "dispersion": str(dispersion) if dispersion is not None else None,
                    "raw_research_grade": raw_grade,
                    "published_grade": published_grade,
                    "action": action,
                    "formal_recommendation": False,
                    "candidate": False,
                }
            )
        ranked = [
            ranking[i] for i in sorted(exact_risk, key=exact_risk.__getitem__, reverse=True)
        ]
        return ranked + [row for i, row in enumerate(ranking) if i not in exact_risk]


class DailyFixtureDiscoveryService:
    def discover_from_snapshots(self, snapshot_root: Path, *, target_date: date) -> list[Path]:
        candidates = []
        for path in sorted(snapshot_root.glob("*/manifest.json")):
            manifest = _load_json(path, {})
            kickoff = parse_utc(str(manifest.get("kickoff_utc")))
            if kickoff.date() == target_date:
                candidates.append(path.parent)
        latest: dict[str, Path] = {}
        for snapshot in candidates:
            manifest = _load_json(snapshot / "manifest.json", {})
            fixture_id = str(manifest.get("fixture_id"))
            previous = latest.get(fixture_id)
            if previous is None:
                latest[fixture_id] = snapshot
                continue
            if str(manifest.get("captured_at_utc")) > str(
                _load_json(previous / "manifest.json", {}).get("captured_at_utc")
            ):
                latest[fixture_id] = snapshot
        return list(latest.values())


class MatchdayEligibilityService:
    def classify(self, *, kickoff_utc: datetime, now: datetime, has_prematch_snapshot: bool) -> str:
        if kickoff_utc <= now and not has_prematch_snapshot:
            return "MISSED_PREMATCH_WINDOW"
        if kickoff_utc <= now:
            return "SETTLEMENT_PENDING"
        if has_prematch_snapshot:
            return "PREMATCH_LOCKED"
        return "UPCOMING_ELIGIBLE"


class MatchdayPhasePlanner:
    def __init__(self, schedule_path: Path) -> None:
        self.schedule = _load_json(schedule_path, {})

    def plan(self, kickoff_utc: datetime) -> list[dict[str, str | bool]]:
        output = []
        for phase in self.schedule.get("phases", []):
            scheduled = kickoff_utc + timedelta(minutes=int(phase["offset_minutes"]))
            output.append(
                {
                    "phase": phase["phase"],
                    "scheduled_at": scheduled.isoformat(),
                    "prematch": bool(phase["prematch"]),
                }
            )
        return output
