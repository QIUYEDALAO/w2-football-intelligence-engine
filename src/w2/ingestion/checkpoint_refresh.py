from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from w2.ingestion.future_refresh import parse_utc

CHECKPOINT_REFRESH_CONTRACT = "w2.checkpoint_refresh.v1"

CHECKPOINT_OFFSETS: tuple[tuple[str, timedelta, tuple[str, ...]], ...] = (
    ("OPEN", timedelta(hours=-48), ("odds",)),
    ("T24", timedelta(hours=-24), ("odds",)),
    ("T12", timedelta(hours=-12), ("odds",)),
    ("T6", timedelta(hours=-6), ("odds",)),
    ("T3", timedelta(hours=-3), ("odds",)),
    ("T1_LINEUPS", timedelta(hours=-1), ("odds", "lineups")),
    ("T15M_CLOSE", timedelta(minutes=-15), ("odds",)),
    ("RESULT_POLL", timedelta(hours=2), ("fixtures",)),
)

LINEUPS_RETRY_CHECKPOINTS: tuple[tuple[str, timedelta], ...] = (
    ("T45_LINEUPS_RETRY", timedelta(minutes=-45)),
    ("T30_LINEUPS_RETRY", timedelta(minutes=-30)),
)

JUMP_CONFIRMATION_CHECKPOINT = "LINE_JUMP_CONFIRMATION"


@dataclass(frozen=True)
class FixtureCheckpointPlan:
    fixture_id: str
    checkpoint: str
    kickoff_utc: datetime
    due_at_utc: datetime
    endpoints: tuple[str, ...]
    source: str = "scheduled"
    status: str = "PENDING"

    @property
    def plan_id(self) -> str:
        return f"{self.fixture_id}:{self.checkpoint}"

    @property
    def needs_lineups(self) -> bool:
        return "lineups" in self.endpoints

    @property
    def needs_odds(self) -> bool:
        return "odds" in self.endpoints


def normalize_utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)


def checkpoint_plan_for_fixture(
    *,
    fixture_id: str,
    kickoff_utc: datetime,
    generated_at_utc: datetime,
) -> list[FixtureCheckpointPlan]:
    kickoff = normalize_utc(kickoff_utc)
    generated_at = normalize_utc(generated_at_utc)
    if kickoff < generated_at - timedelta(hours=3):
        return []
    plans: list[FixtureCheckpointPlan] = []
    for checkpoint, offset, endpoints in CHECKPOINT_OFFSETS:
        due_at = kickoff + offset
        if checkpoint == "OPEN" and due_at < generated_at:
            due_at = generated_at
        plans.append(
            FixtureCheckpointPlan(
                fixture_id=str(fixture_id),
                checkpoint=checkpoint,
                kickoff_utc=kickoff,
                due_at_utc=due_at,
                endpoints=endpoints,
            )
        )
    return plans


def checkpoint_plans_from_fixture_payloads(
    fixtures: list[dict[str, Any]],
    *,
    now: datetime,
    horizon: timedelta = timedelta(hours=48),
) -> list[FixtureCheckpointPlan]:
    current = normalize_utc(now)
    plans: list[FixtureCheckpointPlan] = []
    for item in fixtures:
        fixture = item.get("fixture", {}) if isinstance(item, dict) else {}
        status = fixture.get("status", {}) if isinstance(fixture, dict) else {}
        if not isinstance(status, dict) or status.get("short") != "NS":
            continue
        fixture_id = str(fixture.get("id") or "")
        kickoff = parse_utc(fixture.get("date")) if isinstance(fixture, dict) else None
        if not fixture_id or kickoff is None:
            continue
        if kickoff < current or kickoff > current + horizon:
            continue
        plans.extend(
            checkpoint_plan_for_fixture(
                fixture_id=fixture_id,
                kickoff_utc=kickoff,
                generated_at_utc=current,
            )
        )
    return plans


def lineups_retry_plans(
    *,
    fixture_id: str,
    kickoff_utc: datetime,
    now: datetime,
    lineups_status: str,
) -> list[FixtureCheckpointPlan]:
    status = lineups_status.upper()
    if status not in {"PROVIDER_EMPTY", "MISSING_LINEUPS", "NOT_READY"}:
        return []
    kickoff = normalize_utc(kickoff_utc)
    current = normalize_utc(now)
    plans: list[FixtureCheckpointPlan] = []
    for checkpoint, offset in LINEUPS_RETRY_CHECKPOINTS:
        due_at = kickoff + offset
        if current <= kickoff and current >= due_at - timedelta(minutes=5):
            plans.append(
                FixtureCheckpointPlan(
                    fixture_id=str(fixture_id),
                    checkpoint=checkpoint,
                    kickoff_utc=kickoff,
                    due_at_utc=due_at,
                    endpoints=("lineups",),
                    source="lineups_retry",
                )
            )
    return plans


def line_jump_confirmation_plan(
    *,
    fixture_id: str,
    kickoff_utc: datetime,
    previous_line: float | None,
    current_line: float | None,
    observed_at_utc: datetime,
) -> FixtureCheckpointPlan | None:
    if previous_line is None or current_line is None:
        return None
    if abs(float(current_line) - float(previous_line)) < 0.5:
        return None
    observed_at = normalize_utc(observed_at_utc)
    return FixtureCheckpointPlan(
        fixture_id=str(fixture_id),
        checkpoint=JUMP_CONFIRMATION_CHECKPOINT,
        kickoff_utc=normalize_utc(kickoff_utc),
        due_at_utc=observed_at + timedelta(minutes=10),
        endpoints=("odds",),
        source="line_jump",
    )


def projected_calls_for_checkpoint_batch(plans: list[FixtureCheckpointPlan]) -> int:
    if not plans:
        return 0
    calls = 0
    if any("status" in plan.endpoints for plan in plans):
        calls += 1
    if any("fixtures" in plan.endpoints for plan in plans) or any(
        endpoint in {"odds", "lineups"} for plan in plans for endpoint in plan.endpoints
    ):
        calls += 1
    calls += sum(1 for plan in plans if plan.needs_odds)
    calls += sum(1 for plan in plans if plan.needs_lineups)
    return calls


def select_checkpoint_batch(
    due_plans: list[FixtureCheckpointPlan],
    *,
    hard_cap: int,
) -> tuple[list[FixtureCheckpointPlan], int]:
    selected: list[FixtureCheckpointPlan] = []
    for plan in due_plans:
        candidate = [*selected, plan]
        projected = projected_calls_for_checkpoint_batch(candidate)
        if projected > hard_cap:
            break
        selected = candidate
    return selected, projected_calls_for_checkpoint_batch(selected)


def saturday_budget_projection(
    *,
    fixture_count: int = 30,
    include_retries: bool = True,
    http_retry_multiplier: int = 2,
) -> dict[str, int | bool]:
    base_per_fixture = 7  # OPEN, T24, T12, T6, T3, T1 odds, T15 close.
    lineups_per_fixture = 1
    result_per_fixture = 1
    retry_per_fixture = 2 if include_retries else 0
    fixture_calls = fixture_count * (
        base_per_fixture + lineups_per_fixture + result_per_fixture + retry_per_fixture
    )
    status_fixture_overhead = 16  # Conservative day-level polling overhead.
    projected = (fixture_calls + status_fixture_overhead) * max(http_retry_multiplier, 1)
    return {
        "fixture_count": fixture_count,
        "projected_calls": projected,
        "budget_cap": 800,
        "within_budget": projected <= 800,
    }
