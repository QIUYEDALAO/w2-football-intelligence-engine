from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from w2.models.forward_automation import (
    DemoFixture,
    ForwardCircuitBreaker,
    ForwardHoldoutCycleService,
    ForwardHoldoutFixtureState,
    ForwardHoldoutStateMachine,
    NoOverlapLock,
    RequestQuotaPolicy,
)


def test_state_machine_allows_and_rejects_expected_transitions() -> None:
    machine = ForwardHoldoutStateMachine()
    now = datetime(2026, 6, 22, tzinfo=UTC)
    transition = machine.transition(
        "fixture-1",
        ForwardHoldoutFixtureState.DISCOVERED,
        ForwardHoldoutFixtureState.ELIGIBLE_T24,
        event_time=now,
        reason="window_open",
    )
    assert transition.to_state == ForwardHoldoutFixtureState.ELIGIBLE_T24
    with pytest.raises(ValueError, match="locked"):
        machine.transition(
            "fixture-1",
            ForwardHoldoutFixtureState.LOCKED_T24,
            ForwardHoldoutFixtureState.DISCOVERED,
            event_time=now,
            reason="bad",
        )
    with pytest.raises(ValueError, match="terminal"):
        machine.transition(
            "fixture-1",
            ForwardHoldoutFixtureState.EVALUATED,
            ForwardHoldoutFixtureState.SETTLED,
            event_time=now,
            reason="bad",
        )


def test_quota_policy_and_circuit_breaker_are_conservative() -> None:
    policy = RequestQuotaPolicy(daily_hard_budget=500, minimum_reserve=2500, per_cycle_cap=100)
    assert policy.allowed_requests(None) == 0
    assert policy.allowed_requests(2500) == 0
    assert policy.allowed_requests(2600) == 100
    breaker = ForwardCircuitBreaker()
    breaker.record_status(429, 7000)
    assert breaker.is_open
    assert breaker.open_reason == "HTTP_429"


def test_cycle_dry_run_idempotent_locks_checkpoint_and_gate_pending() -> None:
    now = datetime(2026, 6, 22, 4, 0, tzinfo=UTC)
    service = ForwardHoldoutCycleService(
        quota_policy=RequestQuotaPolicy(
            daily_hard_budget=500,
            minimum_reserve=2500,
            per_cycle_cap=100,
        )
    )
    fixtures = [
        DemoFixture(fixture_id="demo-a", kickoff_utc=now + timedelta(hours=23)),
        DemoFixture(fixture_id="demo-b", kickoff_utc=now + timedelta(minutes=45), settled=False),
        DemoFixture(fixture_id="demo-c", kickoff_utc=now - timedelta(hours=1), settled=True),
    ]
    result = service.run(
        fixtures=fixtures,
        now=now,
        remaining_quota=3000,
        dry_run=True,
        network_enabled=False,
        autorun_enabled=False,
    )
    assert result.dry_run is True
    assert result.network_enabled is False
    assert result.metrics.duplicate_lock_prevented >= 1
    assert result.gate["GATE_4_NATIONAL_1X2"] == "PROVISIONAL_FORWARD_HOLDOUT_PENDING"
    resumed = service.run(
        fixtures=[],
        now=now + timedelta(minutes=1),
        remaining_quota=3000,
        resume_from=result.checkpoints,
    )
    assert resumed.gate["GATE_4_NATIONAL_1X2"] == result.gate["GATE_4_NATIONAL_1X2"]


def test_no_overlap_lock_blocks_concurrent_cycle() -> None:
    lock = NoOverlapLock()
    assert lock.acquire() is True
    assert lock.acquire() is False
    lock.release()
    assert lock.acquire() is True


def test_scheduler_policy_defaults_disabled() -> None:
    path = Path("config/policies/forward_holdout_schedule.v1.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["defaults"]["W2_FORWARD_HOLDOUT_AUTORUN"] is False
    assert data["defaults"]["W2_FORWARD_HOLDOUT_NETWORK"] is False
    assert all(entry["enabled"] is False for entry in data["celery_beat"]["entries"])


def test_cycle_rejects_network_or_autorun() -> None:
    now = datetime(2026, 6, 22, 4, 0, tzinfo=UTC)
    service = ForwardHoldoutCycleService(
        quota_policy=RequestQuotaPolicy(
            daily_hard_budget=500,
            minimum_reserve=2500,
            per_cycle_cap=100,
        )
    )
    with pytest.raises(ValueError, match="network"):
        service.run(fixtures=[], now=now, remaining_quota=3000, network_enabled=True)
    with pytest.raises(ValueError, match="autorun"):
        service.run(fixtures=[], now=now, remaining_quota=3000, autorun_enabled=True)
