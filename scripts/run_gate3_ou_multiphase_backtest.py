#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from w2.domain.enums import MarketType
from w2.domain.odds import settle_total_goals
from w2.markets.historical_dataset import (
    MarketObservation,
    normalize_w1_local_odds,
    normalize_w1_snapshot_jsonl,
    parse_utc,
)

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "W2_GATE3_OU_MULTIPHASE_BACKTEST.json"
LOCAL_ODDS = ROOT / "tests" / "fixtures" / "gate3" / "w1_local_odds_sample.csv"
SNAPSHOT = ROOT / "tests" / "fixtures" / "gate3" / "w1_snapshot_sample.jsonl"

PHASE_TARGETS: dict[str, timedelta] = {
    "T-72h": timedelta(hours=72),
    "T-48h": timedelta(hours=48),
    "T-24h": timedelta(hours=24),
    "T-12h": timedelta(hours=12),
    "T-6h": timedelta(hours=6),
    "T-3h": timedelta(hours=3),
    "T-1h": timedelta(hours=1),
    "T-30m": timedelta(minutes=30),
    "T-10m": timedelta(minutes=10),
}


@dataclass(frozen=True)
class PhaseBucket:
    phase: str
    snapshot_semantics: str
    eligible_observation_count: int
    settled_observation_count: int
    settled_fixture_count: int
    line_count: int
    line_set: list[str]
    status: str
    blocker: str | None


def phase_for(observation: MarketObservation) -> str | None:
    if observation.snapshot_semantics == "CLOSING":
        return "Closing"
    if observation.snapshot_semantics != "CAPTURED_AT":
        return None
    captured = parse_utc(observation.captured_at)
    kickoff = parse_utc(observation.kickoff_utc)
    if captured is None or kickoff is None or captured > kickoff:
        return None
    lead_time = kickoff - captured
    closest_phase = min(PHASE_TARGETS, key=lambda phase: abs(PHASE_TARGETS[phase] - lead_time))
    return closest_phase


def has_settlement(observation: MarketObservation) -> bool:
    if observation.result is None:
        return False
    home = observation.result.get("home")
    away = observation.result.get("away")
    if home is None or away is None or observation.line is None:
        return False
    settle_total_goals(
        int(home) + int(away),
        observation.canonical_selection,
        Decimal(str(observation.line)),
    )
    return True


def bucket_observations(observations: list[MarketObservation]) -> list[PhaseBucket]:
    phases: dict[str, list[MarketObservation]] = defaultdict(list)
    for observation in observations:
        if observation.market != MarketType.TOTALS.value:
            continue
        phase = phase_for(observation)
        if phase is None:
            continue
        phases[phase].append(observation)

    output: list[PhaseBucket] = []
    for phase in (*PHASE_TARGETS.keys(), "Closing"):
        rows = phases.get(phase, [])
        settled = [row for row in rows if has_settlement(row)]
        semantics = "CLOSING" if phase == "Closing" else "CAPTURED_AT"
        status = "SETTLED_DATA_AVAILABLE" if settled else "NO_SETTLED_DATA"
        blocker = None if settled else "NO_OU_SETTLED_ROWS_FOR_PHASE"
        output.append(
            PhaseBucket(
                phase=phase,
                snapshot_semantics=semantics,
                eligible_observation_count=len(rows),
                settled_observation_count=len(settled),
                settled_fixture_count=len({row.fixture_source_id for row in settled}),
                line_count=len({row.line for row in rows if row.line is not None}),
                line_set=sorted({row.line for row in rows if row.line is not None}, key=Decimal),
                status=status,
                blocker=blocker,
            )
        )
    return output


def leakage_check(buckets: list[PhaseBucket]) -> dict[str, Any]:
    early_closing_rows = sum(
        bucket.eligible_observation_count
        for bucket in buckets
        if bucket.phase != "Closing" and bucket.snapshot_semantics == "CLOSING"
    )
    return {
        "status": "PASS" if early_closing_rows == 0 else "FAIL",
        "closing_rows_in_non_closing_phases": early_closing_rows,
        "retrospective_forward_claim": False,
    }


def build_report() -> dict[str, Any]:
    observations = [
        *normalize_w1_snapshot_jsonl(SNAPSHOT, source_system="W2_INTERNAL_GATE3_FIXTURE"),
        *normalize_w1_local_odds(LOCAL_ODDS, source_system="W2_INTERNAL_GATE3_FIXTURE"),
    ]
    buckets = bucket_observations(observations)
    settled_count = sum(bucket.settled_observation_count for bucket in buckets)
    non_closing_count = sum(
        bucket.eligible_observation_count for bucket in buckets if bucket.phase != "Closing"
    )
    blockers = []
    if settled_count == 0:
        blockers.append("NO_SETTLED_OU_ROWS")
    if non_closing_count == 0:
        blockers.append("NO_NON_CLOSING_OU_OBSERVATIONS")
    return {
        "schema_version": "W2_GATE3_OU_MULTIPHASE_BACKTEST_V1",
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "source_paths": [
            str(SNAPSHOT.relative_to(ROOT)),
            str(LOCAL_ODDS.relative_to(ROOT)),
        ],
        "market": MarketType.TOTALS.value,
        "gate3_status": "READY_FOR_REVIEW" if not blockers else "PARTIAL",
        "blockers": blockers,
        "candidate": False,
        "formal_recommendation": False,
        "phases": [asdict(bucket) for bucket in buckets],
        "summary": {
            "phase_count": len(buckets),
            "non_closing_phase_count": len(
                [bucket for bucket in buckets if bucket.phase != "Closing"]
            ),
            "eligible_observation_count": sum(
                bucket.eligible_observation_count for bucket in buckets
            ),
            "settled_observation_count": settled_count,
            "settled_fixture_count": sum(bucket.settled_fixture_count for bucket in buckets),
        },
        "leakage_check": leakage_check(buckets),
    }


def main() -> int:
    report = build_report()
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"WROTE {REPORT.relative_to(ROOT)}")
    print(f"GATE3_STATUS={report['gate3_status']}")
    print(f"BLOCKERS={','.join(report['blockers']) or 'NONE'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
