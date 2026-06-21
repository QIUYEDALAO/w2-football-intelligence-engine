from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from w2.models.forward_ops import (
    ForwardCycleLedger,
    ForwardDecision,
    ForwardResultEvent,
    gate4_from_power,
    preregistered_evaluation_plan,
)
from w2.models.independent import artifact_hash

NOW = datetime(2026, 6, 22, tzinfo=UTC)


def test_result_append_only_and_idempotent() -> None:
    ledger = ForwardCycleLedger()
    result = ForwardResultEvent(
        fixture_id="fixture",
        provider="api_football",
        confirmed_at=NOW,
        raw_payload_hash=artifact_hash({"fixture": "fixture"}),
        home_goals_90=1,
        away_goals_90=0,
        extra_time={"home": None, "away": None},
        penalties={"home": None, "away": None},
    )
    ledger.append_result(result)
    ledger.append_result(result)
    assert len(ledger.results) == 1


def test_unique_lock_and_kickoff_guard() -> None:
    ledger = ForwardCycleLedger()
    payload = {
        "kickoff_utc": (NOW + timedelta(hours=2)).isoformat(),
        "locked_at": NOW.isoformat(),
        "decision": ForwardDecision.WATCH.value,
    }
    ledger.lock_prediction("fixture", "T-1h", payload)
    ledger.lock_prediction("fixture", "T-1h", payload)
    assert len(ledger.locks) == 1
    with pytest.raises(ValueError):
        ledger.lock_prediction(
            "late",
            "T-1h",
            {
                "kickoff_utc": NOW.isoformat(),
                "locked_at": (NOW + timedelta(seconds=1)).isoformat(),
                "decision": ForwardDecision.WATCH.value,
            },
        )


def test_preregistered_plan_and_optional_stopping_guard() -> None:
    plan = preregistered_evaluation_plan()
    assert plan["minimum_settled_sample"] == 50
    assert "forbidden" in plan["optional_stopping"]
    gate = gate4_from_power(settled_n=5, comparable_n=2, target_n=50)
    assert gate["GATE_4_NATIONAL_1X2"] == "PROVISIONAL_FORWARD_HOLDOUT_PENDING"
