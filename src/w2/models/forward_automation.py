from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from w2.domain.time import require_utc
from w2.models.forward_ops import ForwardCycleLedger, ForwardResultEvent, gate4_from_power
from w2.models.independent import artifact_hash


class ForwardHoldoutFixtureState(StrEnum):
    DISCOVERED = "DISCOVERED"
    ELIGIBLE_T24 = "ELIGIBLE_T24"
    LOCKED_T24 = "LOCKED_T24"
    ELIGIBLE_T1 = "ELIGIBLE_T1"
    LOCKED_T1 = "LOCKED_T1"
    KICKED_OFF = "KICKED_OFF"
    RESULT_PENDING = "RESULT_PENDING"
    SETTLED = "SETTLED"
    EVALUATED = "EVALUATED"
    MARKET_NOT_COMPARABLE = "MARKET_NOT_COMPARABLE"
    VOID = "VOID"
    ERROR_RETRYABLE = "ERROR_RETRYABLE"
    ERROR_BLOCKED = "ERROR_BLOCKED"


LOCKED_STATES = {
    ForwardHoldoutFixtureState.LOCKED_T24,
    ForwardHoldoutFixtureState.LOCKED_T1,
}
TERMINAL_STATES = {
    ForwardHoldoutFixtureState.EVALUATED,
    ForwardHoldoutFixtureState.VOID,
    ForwardHoldoutFixtureState.ERROR_BLOCKED,
}

ALLOWED_TRANSITIONS: dict[ForwardHoldoutFixtureState, set[ForwardHoldoutFixtureState]] = {
    ForwardHoldoutFixtureState.DISCOVERED: {
        ForwardHoldoutFixtureState.ELIGIBLE_T24,
        ForwardHoldoutFixtureState.ELIGIBLE_T1,
        ForwardHoldoutFixtureState.KICKED_OFF,
        ForwardHoldoutFixtureState.VOID,
        ForwardHoldoutFixtureState.ERROR_RETRYABLE,
        ForwardHoldoutFixtureState.ERROR_BLOCKED,
    },
    ForwardHoldoutFixtureState.ELIGIBLE_T24: {
        ForwardHoldoutFixtureState.LOCKED_T24,
        ForwardHoldoutFixtureState.ERROR_RETRYABLE,
        ForwardHoldoutFixtureState.ERROR_BLOCKED,
    },
    ForwardHoldoutFixtureState.LOCKED_T24: {
        ForwardHoldoutFixtureState.ELIGIBLE_T1,
        ForwardHoldoutFixtureState.LOCKED_T1,
        ForwardHoldoutFixtureState.KICKED_OFF,
        ForwardHoldoutFixtureState.MARKET_NOT_COMPARABLE,
        ForwardHoldoutFixtureState.ERROR_RETRYABLE,
        ForwardHoldoutFixtureState.ERROR_BLOCKED,
    },
    ForwardHoldoutFixtureState.ELIGIBLE_T1: {
        ForwardHoldoutFixtureState.LOCKED_T1,
        ForwardHoldoutFixtureState.ERROR_RETRYABLE,
        ForwardHoldoutFixtureState.ERROR_BLOCKED,
    },
    ForwardHoldoutFixtureState.LOCKED_T1: {
        ForwardHoldoutFixtureState.KICKED_OFF,
        ForwardHoldoutFixtureState.MARKET_NOT_COMPARABLE,
        ForwardHoldoutFixtureState.ERROR_RETRYABLE,
        ForwardHoldoutFixtureState.ERROR_BLOCKED,
    },
    ForwardHoldoutFixtureState.KICKED_OFF: {
        ForwardHoldoutFixtureState.RESULT_PENDING,
        ForwardHoldoutFixtureState.VOID,
        ForwardHoldoutFixtureState.ERROR_RETRYABLE,
        ForwardHoldoutFixtureState.ERROR_BLOCKED,
    },
    ForwardHoldoutFixtureState.RESULT_PENDING: {
        ForwardHoldoutFixtureState.SETTLED,
        ForwardHoldoutFixtureState.ERROR_RETRYABLE,
        ForwardHoldoutFixtureState.ERROR_BLOCKED,
    },
    ForwardHoldoutFixtureState.SETTLED: {
        ForwardHoldoutFixtureState.EVALUATED,
        ForwardHoldoutFixtureState.MARKET_NOT_COMPARABLE,
    },
    ForwardHoldoutFixtureState.MARKET_NOT_COMPARABLE: {
        ForwardHoldoutFixtureState.EVALUATED,
    },
    ForwardHoldoutFixtureState.ERROR_RETRYABLE: {
        ForwardHoldoutFixtureState.DISCOVERED,
        ForwardHoldoutFixtureState.ERROR_BLOCKED,
    },
    ForwardHoldoutFixtureState.ERROR_BLOCKED: set(),
    ForwardHoldoutFixtureState.EVALUATED: set(),
    ForwardHoldoutFixtureState.VOID: set(),
}


@dataclass(frozen=True, kw_only=True)
class ForwardStateTransition:
    fixture_id: str
    from_state: ForwardHoldoutFixtureState
    to_state: ForwardHoldoutFixtureState
    event_time: datetime
    reason: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_time", require_utc(self.event_time, "event_time"))


class ForwardHoldoutStateMachine:
    def validate(
        self,
        current: ForwardHoldoutFixtureState,
        target: ForwardHoldoutFixtureState,
    ) -> None:
        if target == current:
            return
        if current in TERMINAL_STATES:
            raise ValueError("terminal forward holdout state cannot transition")
        if current in LOCKED_STATES and target in {
            ForwardHoldoutFixtureState.DISCOVERED,
            ForwardHoldoutFixtureState.ELIGIBLE_T24,
        }:
            raise ValueError("locked forward holdout state cannot move backward")
        if target not in ALLOWED_TRANSITIONS[current]:
            raise ValueError(f"illegal transition {current}->{target}")

    def transition(
        self,
        fixture_id: str,
        current: ForwardHoldoutFixtureState,
        target: ForwardHoldoutFixtureState,
        *,
        event_time: datetime,
        reason: str,
    ) -> ForwardStateTransition:
        self.validate(current, target)
        return ForwardStateTransition(
            fixture_id=fixture_id,
            from_state=current,
            to_state=target,
            event_time=event_time,
            reason=reason,
        )


@dataclass(frozen=True, kw_only=True)
class RequestQuotaPolicy:
    daily_hard_budget: int
    minimum_reserve: int = 2500
    per_cycle_cap: int = 100
    emergency_stop: bool = False

    def allowed_requests(self, remaining_quota: int | None) -> int:
        if self.emergency_stop:
            return 0
        if remaining_quota is None:
            return 0
        if remaining_quota <= self.minimum_reserve:
            return 0
        available = remaining_quota - self.minimum_reserve
        return min(self.per_cycle_cap, self.daily_hard_budget, available)


class ForwardCircuitBreaker:
    def __init__(self) -> None:
        self.open_reason: str | None = None

    @property
    def is_open(self) -> bool:
        return self.open_reason is not None

    def record_status(self, status_code: int, remaining_quota: int | None) -> None:
        if status_code in {401, 403, 429}:
            self.open_reason = f"HTTP_{status_code}"
        elif remaining_quota is None:
            self.open_reason = "REMAINING_QUOTA_UNKNOWN"


@dataclass(kw_only=True)
class ForwardCycleCheckpoint:
    cycle_id: str
    step: str
    payload_hash: str
    created_at: datetime

    def __post_init__(self) -> None:
        self.created_at = require_utc(self.created_at, "created_at")


@dataclass(kw_only=True)
class ForwardAutomationMetrics:
    discovered_fixtures: int = 0
    lock_success: int = 0
    lock_failure: int = 0
    duplicate_lock_prevented: int = 0
    settlement_lag_seconds: int = 0
    market_snapshot_coverage: float = 0.0
    api_usage: int = 0
    quota_reserve: int = 2500
    immutable_hash_failures: int = 0
    current_sample_count: int = 0
    target_sample_count: int = 50
    gate4_state: str = "PROVISIONAL_FORWARD_HOLDOUT_PENDING"


@dataclass(kw_only=True)
class ForwardCycleResult:
    cycle_id: str
    cycle_hash: str
    dry_run: bool
    network_enabled: bool
    autorun_enabled: bool
    checkpoints: list[ForwardCycleCheckpoint]
    transitions: list[ForwardStateTransition]
    metrics: ForwardAutomationMetrics
    gate: dict[str, Any]
    audit: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class DemoFixture:
    fixture_id: str
    kickoff_utc: datetime
    has_market_snapshot: bool = False
    settled: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "kickoff_utc", require_utc(self.kickoff_utc, "kickoff_utc"))


class NoOverlapLock:
    def __init__(self) -> None:
        self._locked = False

    def acquire(self) -> bool:
        if self._locked:
            return False
        self._locked = True
        return True

    def release(self) -> None:
        self._locked = False


class ForwardHoldoutCycleService:
    def __init__(
        self,
        *,
        quota_policy: RequestQuotaPolicy,
        state_machine: ForwardHoldoutStateMachine | None = None,
        overlap_lock: NoOverlapLock | None = None,
    ) -> None:
        self.quota_policy = quota_policy
        self.state_machine = state_machine or ForwardHoldoutStateMachine()
        self.overlap_lock = overlap_lock or NoOverlapLock()
        self.ledger = ForwardCycleLedger()
        self.checkpoints: list[ForwardCycleCheckpoint] = []
        self.transitions: list[ForwardStateTransition] = []
        self.audit: list[dict[str, Any]] = []

    def run(
        self,
        *,
        fixtures: list[DemoFixture],
        now: datetime,
        remaining_quota: int | None,
        dry_run: bool = True,
        network_enabled: bool = False,
        autorun_enabled: bool = False,
        resume_from: list[ForwardCycleCheckpoint] | None = None,
    ) -> ForwardCycleResult:
        now = require_utc(now, "now")
        if network_enabled:
            raise ValueError("Stage7D dry cycle must not enable network")
        if autorun_enabled:
            raise ValueError("Stage7D autorun must remain disabled")
        if not self.overlap_lock.acquire():
            raise RuntimeError("FORWARD_CYCLE_OVERLAP_BLOCKED")
        try:
            if resume_from:
                self.checkpoints.extend(resume_from)
            allowed = self.quota_policy.allowed_requests(remaining_quota)
            breaker = ForwardCircuitBreaker()
            if allowed == 0:
                breaker.record_status(200, remaining_quota)
            self._checkpoint("discover", fixtures)
            locks = self._lock_eligible_phases(fixtures, now)
            self._checkpoint("lock", locks)
            market_count = self._capture_market_snapshots(fixtures, locks)
            self._checkpoint("market", {"market_count": market_count})
            settled = self._settle_results(fixtures, now)
            self._checkpoint("settle", {"settled": settled})
            target_n = 50
            gate = gate4_from_power(settled, 0, target_n)
            metrics = ForwardAutomationMetrics(
                discovered_fixtures=len(fixtures),
                lock_success=len(locks),
                duplicate_lock_prevented=self.audit_count("duplicate_lock_prevented"),
                market_snapshot_coverage=market_count / len(locks) if locks else 0.0,
                api_usage=0 if dry_run else allowed,
                quota_reserve=self.quota_policy.minimum_reserve,
                current_sample_count=settled,
                target_sample_count=target_n,
                gate4_state=gate["GATE_4_NATIONAL_1X2"],
            )
            self._checkpoint("gate", gate)
            cycle_id = f"stage7d-{now.strftime('%Y%m%dT%H%M%SZ')}"
            payload = {
                "cycle_id": cycle_id,
                "checkpoints": [checkpoint.__dict__ for checkpoint in self.checkpoints],
                "transitions": [transition.__dict__ for transition in self.transitions],
                "metrics": metrics.__dict__,
                "gate": gate,
                "breaker_open": breaker.is_open,
            }
            return ForwardCycleResult(
                cycle_id=cycle_id,
                cycle_hash=artifact_hash(payload),
                dry_run=dry_run,
                network_enabled=network_enabled,
                autorun_enabled=autorun_enabled,
                checkpoints=list(self.checkpoints),
                transitions=list(self.transitions),
                metrics=metrics,
                gate=gate,
                audit=list(self.audit),
            )
        finally:
            self.overlap_lock.release()

    def audit_count(self, event: str) -> int:
        return sum(1 for item in self.audit if item.get("event") == event)

    def _checkpoint(self, step: str, payload: object) -> None:
        payload_hash = artifact_hash(payload)
        self.checkpoints.append(
            ForwardCycleCheckpoint(
                cycle_id="stage7d-dry",
                step=step,
                payload_hash=payload_hash,
                created_at=datetime.now(UTC),
            )
        )

    def _transition(
        self,
        fixture_id: str,
        current: ForwardHoldoutFixtureState,
        target: ForwardHoldoutFixtureState,
        now: datetime,
        reason: str,
    ) -> ForwardHoldoutFixtureState:
        transition = self.state_machine.transition(
            fixture_id,
            current,
            target,
            event_time=now,
            reason=reason,
        )
        self.transitions.append(transition)
        return target

    def _lock_eligible_phases(
        self,
        fixtures: list[DemoFixture],
        now: datetime,
    ) -> list[dict[str, Any]]:
        locks: list[dict[str, Any]] = []
        for fixture in fixtures:
            state = ForwardHoldoutFixtureState.DISCOVERED
            for phase, offset, target in (
                ("T-24h", timedelta(hours=24), ForwardHoldoutFixtureState.LOCKED_T24),
                ("T-1h", timedelta(hours=1), ForwardHoldoutFixtureState.LOCKED_T1),
            ):
                as_of_time = fixture.kickoff_utc - offset
                if now < as_of_time:
                    continue
                if now >= fixture.kickoff_utc:
                    self.audit.append(
                        {"event": "kickoff_lock_rejected", "fixture_id": fixture.fixture_id}
                    )
                    continue
                eligible = (
                    ForwardHoldoutFixtureState.ELIGIBLE_T24
                    if phase == "T-24h"
                    else ForwardHoldoutFixtureState.ELIGIBLE_T1
                )
                state = self._transition(
                    fixture.fixture_id,
                    state,
                    eligible,
                    now,
                    f"{phase}_eligible",
                )
                payload = {
                    "fixture_id": fixture.fixture_id,
                    "phase": phase,
                    "kickoff_utc": fixture.kickoff_utc.isoformat(),
                    "locked_at": now.isoformat(),
                    "as_of_time": as_of_time.isoformat(),
                    "data_cutoff": as_of_time.isoformat(),
                    "decision": "WATCH",
                }
                before = len(self.ledger.locks)
                self.ledger.lock_prediction(fixture.fixture_id, phase, payload)
                self.ledger.lock_prediction(fixture.fixture_id, phase, payload)
                if len(self.ledger.locks) == before + 1:
                    self.audit.append(
                        {
                            "event": "duplicate_lock_prevented",
                            "fixture_id": fixture.fixture_id,
                            "phase": phase,
                        }
                    )
                locks.append(payload)
                state = self._transition(fixture.fixture_id, state, target, now, f"{phase}_locked")
        return locks

    def _capture_market_snapshots(
        self,
        fixtures: list[DemoFixture],
        locks: list[dict[str, Any]],
    ) -> int:
        fixture_market = {fixture.fixture_id: fixture.has_market_snapshot for fixture in fixtures}
        market_count = sum(1 for lock in locks if fixture_market.get(lock["fixture_id"], False))
        for lock in locks:
            if not fixture_market.get(lock["fixture_id"], False):
                self.audit.append(
                    {
                        "event": "market_not_comparable",
                        "fixture_id": lock["fixture_id"],
                        "phase": lock["phase"],
                    }
                )
        return market_count

    def _settle_results(self, fixtures: list[DemoFixture], now: datetime) -> int:
        settled = 0
        for fixture in fixtures:
            if not fixture.settled:
                continue
            result = ForwardResultEvent(
                fixture_id=fixture.fixture_id,
                provider="stage7d_demo",
                confirmed_at=now,
                raw_payload_hash=artifact_hash({"fixture_id": fixture.fixture_id, "settled": True}),
                home_goals_90=1,
                away_goals_90=0,
                extra_time={},
                penalties={},
            )
            before = len(self.ledger.results)
            self.ledger.append_result(result)
            self.ledger.append_result(result)
            if len(self.ledger.results) == before + 1:
                settled += 1
        return settled
