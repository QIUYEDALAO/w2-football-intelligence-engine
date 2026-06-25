#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from w2.domain.enums import MarketType
from w2.domain.odds import settle_asian_handicap, settle_total_goals
from w2.markets.historical_dataset import (
    PHASE_OFFSETS,
    MarketObservation,
    normalize_source,
    parse_utc,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/gate3"
REPORT = ROOT / "reports/W2_GATE3_PHASE_SETTLED_BACKTEST.json"


def settled_outcome(observation: MarketObservation) -> str | None:
    if observation.result is None:
        return None
    home = observation.result["home_goals"]
    away = observation.result["away_goals"]
    if observation.market == MarketType.ONE_X_TWO.value:
        actual = "HOME" if home > away else "AWAY" if away > home else "DRAW"
        return "WIN" if observation.canonical_selection == actual else "LOSS"
    if observation.market == MarketType.ASIAN_HANDICAP.value and observation.line is not None:
        return settle_asian_handicap(
            home,
            away,
            observation.canonical_selection,
            Decimal(observation.line),
        ).value
    if observation.market == MarketType.TOTALS.value and observation.line is not None:
        return settle_total_goals(
            home + away,
            observation.canonical_selection,
            Decimal(observation.line),
        ).value
    if observation.market == MarketType.BTTS.value:
        actual = "YES" if home > 0 and away > 0 else "NO"
        return "WIN" if observation.canonical_selection == actual else "LOSS"
    return None


def phase_allows(observation: MarketObservation, phase: str) -> bool:
    kickoff = parse_utc(observation.kickoff_utc)
    captured_at = parse_utc(observation.captured_at)
    if kickoff is None or captured_at is None or observation.snapshot_semantics != "CAPTURED_AT":
        return False
    if phase == "Closing":
        return captured_at < kickoff
    return captured_at <= kickoff - PHASE_OFFSETS[phase]


def build_report(paths: list[Path]) -> dict[str, Any]:
    observations: list[MarketObservation] = []
    for path in paths:
        observations.extend(normalize_source(path, source_system="INTERNAL_TEST_FIXTURE"))
    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    by_phase: dict[str, dict[str, Any]] = {}
    leakage_count = 0
    for phase in PHASE_OFFSETS:
        eligible = [obs for obs in observations if phase_allows(obs, phase)]
        settled = Counter(
            outcome for obs in eligible if (outcome := settled_outcome(obs)) is not None
        )
        fixture_count = len({obs.fixture_source_id for obs in eligible})
        status = "SETTLED_DATA_AVAILABLE" if settled else "NO_SETTLED_DATA"
        by_phase[phase] = {
            "status": status,
            "eligible_observation_count": len(eligible),
            "settled_observation_count": sum(settled.values()),
            "fixture_count": fixture_count,
            "settlement_distribution": dict(sorted(settled.items())),
        }
        if phase != "Closing":
            leakage_count += sum(1 for obs in eligible if obs.snapshot_semantics == "CLOSING")
    return {
        "schema_version": "W2_GATE3_PHASE_SETTLED_BACKTEST_V1",
        "generated_at_utc": generated_at,
        "source_paths": [str(path.relative_to(ROOT)) for path in paths],
        "phase_count": len(by_phase),
        "phases": by_phase,
        "leakage_check": {
            "status": "PASS" if leakage_count == 0 else "FAIL",
            "closing_rows_used_in_early_phase": leakage_count,
        },
        "candidate": False,
        "formal_recommendation": False,
        "gate3_status": "PARTIAL",
        "blockers": (
            ["NO_SETTLED_CAPTURED_AT_ROWS"]
            if not any(phase["settled_observation_count"] for phase in by_phase.values())
            else []
        ),
    }


def main() -> int:
    paths = [
        FIXTURES / "w1_snapshot_sample.jsonl",
        FIXTURES / "w1_local_odds_sample.csv",
    ]
    report = build_report(paths)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "W2 Gate3 phase settled backtest "
        f"{report['gate3_status']} phases={report['phase_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
