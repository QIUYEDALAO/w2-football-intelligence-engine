from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from w2.tracking.forward_ledger_performance import (  # noqa: E402
    forward_ledger_performance,
    load_forward_ledger_records,
)

DEFAULT_CHECKPOINT_DATE = "2026-07-22"
DEFAULT_ENVIRONMENT = "staging"
DEFAULT_MIN_DOUBLE_SNAPSHOT_CARDS = 100
DEFAULT_RUNTIME_ROOT = Path("runtime")
CANDIDATE_LEAGUES = ("eliteserien", "allsvenskan", "chinese_super_league")


def build_checkpoint_report(
    runtime_root: Path,
    *,
    checkpoint_date: str = DEFAULT_CHECKPOINT_DATE,
    environment: str = DEFAULT_ENVIRONMENT,
    min_double_snapshot_cards: int = DEFAULT_MIN_DOUBLE_SNAPSHOT_CARDS,
) -> dict[str, Any]:
    ledger_root = _ledger_root(runtime_root)
    records = list(load_forward_ledger_records(ledger_root))
    filtered = [
        record
        for record in records
        if _text(record.get("environment") or environment) == environment
    ]
    captures = [
        record for record in filtered if _text(record.get("record_type") or "capture") == "capture"
    ]
    outcomes = [
        record for record in filtered if _text(record.get("record_type")) == "outcome"
    ]
    performance = forward_ledger_performance(ledger_root.parent, sample_target=200)
    clv_shadow = performance.get("clv_shadow")
    if not isinstance(clv_shadow, Mapping):
        clv_shadow = {}

    double_snapshot_card_count = _double_snapshot_card_count(captures)
    shadow_nonempty_rate = _rate(
        len([record for record in captures if isinstance(record.get("shadow_pick"), Mapping)]),
        len(captures),
    )
    clv_shadow_sample_count = int(clv_shadow.get("sample_count") or 0)
    clv_shadow_median = clv_shadow.get("median_decimal")
    if clv_shadow_sample_count == 0:
        clv_shadow_median = "ACCUMULATING"
    entry_window_met_rate = _rate(
        int(clv_shadow.get("entry_window_met_count") or 0),
        clv_shadow_sample_count,
    )
    if clv_shadow_sample_count == 0:
        entry_window_met_rate = "ACCUMULATING"

    readiness_status, blockers = _readiness_status(
        double_snapshot_card_count=double_snapshot_card_count,
        clv_shadow_sample_count=clv_shadow_sample_count,
        outcome_count=len(outcomes),
        min_double_snapshot_cards=min_double_snapshot_cards,
    )

    return {
        "checkpoint_date": checkpoint_date,
        "environment": environment,
        "double_snapshot_card_count": double_snapshot_card_count,
        "shadow_nonempty_rate": shadow_nonempty_rate,
        "clv_shadow_sample_count": clv_shadow_sample_count,
        "clv_shadow_median": clv_shadow_median,
        "entry_window_met_rate": entry_window_met_rate,
        "excluded_no_prematch_closing_count": int(
            clv_shadow.get("excluded_no_prematch_closing") or 0
        ),
        "unsettled_missing_fulltime_count": _unsettled_missing_fulltime_count(filtered),
        "outcome_count_ft": _outcome_count_by_status(outcomes, "FT"),
        "outcome_count_aet": _outcome_count_by_status(outcomes, "AET"),
        "outcome_count_pen": _outcome_count_by_status(outcomes, "PEN"),
        "provider_usage_curve_summary": _provider_usage_curve_summary(filtered),
        "model_family_distribution": _model_family_distribution(captures),
        "r4_1_artifact_provenance_distribution": _artifact_provenance_distribution(captures),
        "direction_allowed_candidate_leagues": _candidate_leagues(
            performance.get("by_league"),
            min_double_snapshot_cards=min_double_snapshot_cards,
        ),
        "readiness_status": readiness_status,
        "blockers": blockers,
        "provider_calls": 0,
        "db_reads": 0,
        "db_writes": 0,
        "lock_writes": 0,
        "settlement_writes": 0,
        "direction_allowed_changed": False,
        "ev_recommend_leg_changed": False,
        "runtime_root": str(runtime_root),
        "ledger_root": str(ledger_root),
        "record_count": len(filtered),
        "capture_count": len(captures),
        "outcome_count": len(outcomes),
    }


def _ledger_root(runtime_root: Path) -> Path:
    if runtime_root.name == "forward_outcome_ledger":
        return runtime_root
    return runtime_root / "forward_outcome_ledger"


def _double_snapshot_card_count(captures: Sequence[Mapping[str, Any]]) -> int:
    grouped: dict[str, set[str]] = defaultdict(set)
    for record in captures:
        fixture_id = _text(record.get("fixture_id"))
        captured_at = _text(record.get("captured_at"))
        if fixture_id and captured_at:
            grouped[fixture_id].add(captured_at)
    return len([fixture_id for fixture_id, snapshots in grouped.items() if len(snapshots) >= 2])


def _readiness_status(
    *,
    double_snapshot_card_count: int,
    clv_shadow_sample_count: int,
    outcome_count: int,
    min_double_snapshot_cards: int,
) -> tuple[str, list[str]]:
    blockers: list[str] = []
    if outcome_count == 0:
        blockers.append("NO_SETTLEMENT_SAMPLES_ACCUMULATING")
    if double_snapshot_card_count < min_double_snapshot_cards:
        blockers.append("DOUBLE_SNAPSHOT_CARD_COUNT_BELOW_THRESHOLD")
    if clv_shadow_sample_count < min_double_snapshot_cards:
        blockers.append("CLV_SHADOW_SAMPLE_COUNT_BELOW_THRESHOLD")
    if outcome_count == 0:
        return ("ACCUMULATING", blockers)
    if blockers:
        return ("NOT_ENOUGH_SAMPLE", blockers)
    return ("READY_FOR_REVIEW", [])


def _provider_usage_curve_summary(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_day: Counter[str] = Counter()
    for record in records:
        calls = _int(record.get("provider_calls")) or 0
        if calls <= 0:
            continue
        day = _text(record.get("football_day")) or _day_from_timestamp(record.get("captured_at"))
        by_day[day or "unknown"] += calls
    return {
        "source": "runtime/forward_outcome_ledger",
        "status": "LOCAL_LEDGER_ONLY",
        "provider_calls": 0,
        "daily_provider_calls": dict(sorted(by_day.items())),
        "hard_cap_per_day": 120,
    }


def _model_family_distribution(captures: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for record in captures:
        family = _model_family(record)
        if family:
            counts[family] += 1
    return dict(sorted(counts.items()))


def _artifact_provenance_distribution(captures: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for record in captures:
        provenance = _artifact_provenance(record)
        if provenance:
            counts[provenance] += 1
    return dict(sorted(counts.items()))


def _candidate_leagues(
    by_league: Any,
    *,
    min_double_snapshot_cards: int,
) -> list[dict[str, Any]]:
    rows = by_league if isinstance(by_league, Sequence) and not isinstance(by_league, str) else []
    rows_by_league = {
        _normalize_league(_text(row.get("league"))): row
        for row in rows
        if isinstance(row, Mapping)
    }
    candidates: list[dict[str, Any]] = []
    for league in CANDIDATE_LEAGUES:
        row = rows_by_league.get(league, {})
        sample_count = (
            int(row.get("clv_shadow_sample_count") or 0)
            if isinstance(row, Mapping)
            else 0
        )
        median_value = row.get("clv_shadow_median_decimal") if isinstance(row, Mapping) else None
        candidates.append(
            {
                "competition_id": league,
                "status": "READY_FOR_REVIEW"
                if sample_count >= min_double_snapshot_cards and _positive(median_value)
                else "NOT_ENOUGH_SAMPLE",
                "clv_shadow_sample_count": sample_count,
                "clv_shadow_median": median_value
                if sample_count > 0
                else "ACCUMULATING",
                "direction_allowed_changed": False,
            }
        )
    candidates.append(
        {
            "competition_id": "brasileirao_serie_a",
            "status": "DISABLED_BY_PRE_REGISTERED_GUARD",
            "reason": "R4.1 worsened Brazil gap; not a direction_allowed candidate",
            "direction_allowed_changed": False,
        }
    )
    return candidates


def _outcome_count_by_status(outcomes: Sequence[Mapping[str, Any]], status: str) -> int:
    return len(
        [
            record
            for record in outcomes
            if _text(_nested(record, ("final_score", "status"))).upper() == status
        ]
    )


def _unsettled_missing_fulltime_count(records: Sequence[Mapping[str, Any]]) -> int:
    return len(
        [
            record
            for record in records
            if _text(record.get("void_reason")).upper() == "UNSETTLED_MISSING_FULLTIME"
            or _text(record.get("blocker")).upper() == "UNSETTLED_MISSING_FULLTIME"
        ]
    )


def _model_family(record: Mapping[str, Any]) -> str:
    for path in (
        ("model_market_divergence", "model_family"),
        ("pricing_shadow", "model_family"),
        ("shadow_pick", "model_family"),
        ("pick", "model_family"),
    ):
        value = _text(_nested(record, path))
        if value:
            return value
    return ""


def _artifact_provenance(record: Mapping[str, Any]) -> str:
    for path in (
        ("model_market_divergence",),
        ("pricing_shadow",),
        ("shadow_pick",),
        ("pick",),
    ):
        payload = _nested(record, path)
        if not isinstance(payload, Mapping):
            continue
        artifact_hash = _text(payload.get("artifact_hash"))
        artifact_version = _text(payload.get("artifact_version"))
        train_cutoff = _text(payload.get("train_cutoff"))
        if artifact_hash or artifact_version or train_cutoff:
            return "|".join(
                [
                    artifact_version or "unknown_version",
                    artifact_hash or "unknown_hash",
                    train_cutoff or "unknown_train_cutoff",
                ]
            )
    return ""


def _nested(record: Mapping[str, Any], path: Sequence[str]) -> Any:
    value: Any = record
    for key in path:
        if not isinstance(value, Mapping):
            return None
        value = value.get(key)
    return value


def _rate(numerator: int, denominator: int) -> float | str:
    if denominator <= 0:
        return "ACCUMULATING"
    return round(numerator / denominator, 6)


def _positive(value: Any) -> bool:
    if isinstance(value, int | float):
        return value > 0
    return False


def _normalize_league(value: str) -> str:
    normalized = value.lower().strip().replace(" ", "_").replace("-", "_")
    aliases = {
        "super_league": "chinese_super_league",
        "chinese_super_league": "chinese_super_league",
        "allsvenskan": "allsvenskan",
        "eliteserien": "eliteserien",
    }
    return aliases.get(normalized, normalized)


def _day_from_timestamp(value: Any) -> str:
    parsed = _parse_time(value)
    if parsed is None:
        return ""
    return parsed.date().isoformat()


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only R1.1 checkpoint dry-run for W2 forward ledger accrual."
    )
    parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME_ROOT)
    parser.add_argument("--checkpoint-date", default=DEFAULT_CHECKPOINT_DATE)
    parser.add_argument("--environment", default=DEFAULT_ENVIRONMENT)
    parser.add_argument(
        "--min-double-snapshot-cards",
        type=int,
        default=DEFAULT_MIN_DOUBLE_SNAPSHOT_CARDS,
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    payload = build_checkpoint_report(
        args.runtime_root,
        checkpoint_date=args.checkpoint_date,
        environment=args.environment,
        min_double_snapshot_cards=args.min_double_snapshot_cards,
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(
            "status={status} double_snapshot_cards={cards} clv_shadow_samples={samples}".format(
                status=payload["readiness_status"],
                cards=payload["double_snapshot_card_count"],
                samples=payload["clv_shadow_sample_count"],
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
