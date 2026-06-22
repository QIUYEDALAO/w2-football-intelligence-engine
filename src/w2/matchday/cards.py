from __future__ import annotations

import json
import statistics
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from w2.matchday.integrity import SnapshotHashVerifier
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
    settlement = row.get("settlement_probabilities") or {}
    if {"win", "half_win", "push", "half_loss", "loss"} & set(settlement):
        return {
            "full_win_probability": _decimal(settlement.get("win", 0)),
            "half_win_probability": _decimal(settlement.get("half_win", 0)),
            "push_probability": _decimal(settlement.get("push", 0)),
            "half_loss_probability": _decimal(settlement.get("half_loss", 0)),
            "full_loss_probability": _decimal(settlement.get("loss", 0)),
        }
    return _binary_distribution(_decimal(row.get("model_probability", 0)))


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
    hk = decimal_odds - Decimal("1")
    return (
        distribution["full_win_probability"] * hk
        + distribution["half_win_probability"] * Decimal("0.5") * hk
        - distribution["half_loss_probability"] * Decimal("0.5")
        - distribution["full_loss_probability"]
    )


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
    ) -> list[dict[str, Any]]:
        ranking: list[dict[str, Any]] = []
        for value in value_rows:
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
            ranking.append(
                {
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
        return sorted(
            ranking,
            key=lambda row: Decimal(row.get("risk_adjusted_ev") or "-999"),
            reverse=True,
        )


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


class DailyMatchdayCycle:
    def __init__(
        self,
        *,
        snapshot_root: Path,
        schedule_path: Path,
        reports_dir: Path,
        now: datetime | None = None,
    ) -> None:
        self.snapshot_root = snapshot_root
        self.schedule_path = schedule_path
        self.reports_dir = reports_dir
        self.now = now or datetime.now(UTC)
        self.builder = ResearchCardBuilder()
        self.verifier = SnapshotHashVerifier()
        self.discovery = DailyFixtureDiscoveryService()
        self.eligibility = MatchdayEligibilityService()
        self.planner = MatchdayPhasePlanner(schedule_path)

    def run(self, *, target_date: date, dry_run: bool = True) -> dict[str, Any]:
        snapshots = self.discovery.discover_from_snapshots(
            self.snapshot_root,
            target_date=target_date,
        )
        fixture_audit = []
        integrity_records = []
        cards = []
        for snapshot in snapshots:
            manifest = _load_json(snapshot / "manifest.json", {})
            kickoff = parse_utc(str(manifest["kickoff_utc"]))
            integrity = self.verifier.verify_snapshot(snapshot)
            card = self.builder.build_from_snapshot(
                snapshot,
                valuation_generated_at=self.now,
                integrity=integrity,
            )
            status = self.eligibility.classify(
                kickoff_utc=kickoff,
                now=self.now,
                has_prematch_snapshot=card.temporal["locked_before_kickoff"] is True,
            )
            fixture_audit.append(
                {
                    **card.fixture,
                    "matchday_status": status,
                    "phase_plan": self.planner.plan(kickoff),
                }
            )
            integrity_records.append(integrity)
            cards.append(
                {
                    "fixture": card.fixture,
                    "card": card.card,
                    "market_ranking": card.market_ranking,
                    "temporal": card.temporal,
                    "integrity": card.integrity,
                }
            )
        result = {
            "stage": "10C",
            "dry_run": dry_run,
            "target_date": target_date.isoformat(),
            "actual_fixture_count": len(fixture_audit),
            "fixture_audit": fixture_audit,
            "snapshot_integrity": integrity_records,
            "all_market_cards": cards,
            "blockers": [],
            "warn_only": [
                "SERVER_DEPLOYMENT_PAUSED",
                "PERSISTENT_SCHEDULER_WIRING_PENDING_DEPLOYMENT",
            ],
        }
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        (self.reports_dir / "W2_STAGE10C_DAILY_FIXTURE_AUDIT.json").write_text(
            json.dumps({"items": fixture_audit}, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        (self.reports_dir / "W2_STAGE10C_SNAPSHOT_INTEGRITY.json").write_text(
            json.dumps({"items": integrity_records}, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        (self.reports_dir / "W2_STAGE10C_ALL_MARKET_CARDS.json").write_text(
            json.dumps({"items": cards}, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        (self.reports_dir / "W2_STAGE10C_RESULT.md").write_text(
            "\n".join(
                [
                    "# W2 Stage10C Result",
                    "",
                    "STAGE_10C=COMPLETED_LOCAL",
                    "SERVER_DEPLOYMENT=PAUSED_PENDING_APPROVAL",
                    "FORMAL_RECOMMENDATION=false",
                    "CANDIDATE=false",
                    f"actual_fixture_count={len(fixture_audit)}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        return result
