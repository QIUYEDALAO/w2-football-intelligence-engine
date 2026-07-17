from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from w2.ingestion.future_refresh import parse_utc

CHECKPOINT_REFRESH_CONTRACT = "w2.checkpoint_refresh.v1"
WORLD_CUP_DAILY_PROVIDER_BUDGET = 100
WORLD_CUP_MATCHDAY_PROVIDER_BUDGET = 80
WORLD_CUP_TRICKLE_BACKFILL_DAILY_BUDGET = 0
WORLD_CUP_BUDGET_RESERVE = 20

CHECKPOINT_OFFSETS: tuple[tuple[str, timedelta, tuple[str, ...]], ...] = (
    ("OPEN", timedelta(hours=-48), ("odds",)),
    ("T6_ODDS", timedelta(hours=-6), ("odds",)),
    ("T1_LINEUPS", timedelta(hours=-1), ("odds", "lineups")),
    ("T15M_CLOSE", timedelta(minutes=-15), ("odds",)),
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
        status = "MISSED" if checkpoint == "T6_ODDS" and due_at < generated_at else "PENDING"
        plans.append(
            FixtureCheckpointPlan(
                fixture_id=str(fixture_id),
                checkpoint=checkpoint,
                kickoff_utc=kickoff,
                due_at_utc=due_at,
                endpoints=endpoints,
                status=status,
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


def prioritize_checkpoint_plans(
    plans: list[FixtureCheckpointPlan],
    *,
    now: datetime,
) -> list[FixtureCheckpointPlan]:
    """Spend a constrained tick on today's nearest kickoffs before future fixtures."""
    current = normalize_utc(now)
    return sorted(
        plans,
        key=lambda plan: (
            normalize_utc(plan.kickoff_utc).date() != current.date(),
            normalize_utc(plan.kickoff_utc),
            normalize_utc(plan.due_at_utc),
            str(plan.fixture_id),
            str(plan.checkpoint),
        ),
    )


def world_cup_matchday_budget_projection(
    *,
    fixture_count: int = 5,
    include_retries: bool = True,
    include_status_fixture_overhead: bool = True,
    daily_budget: int = WORLD_CUP_DAILY_PROVIDER_BUDGET,
    matchday_budget: int = WORLD_CUP_MATCHDAY_PROVIDER_BUDGET,
    trickle_backfill_budget: int = WORLD_CUP_TRICKLE_BACKFILL_DAILY_BUDGET,
) -> dict[str, int | bool]:
    base_per_fixture = 4  # OPEN, T6 odds, T1 odds, T15 close.
    lineups_per_fixture = 1
    retry_per_fixture = 2 if include_retries else 0
    fixture_calls = fixture_count * (
        base_per_fixture + lineups_per_fixture + retry_per_fixture
    )
    status_fixture_overhead = 2 if include_status_fixture_overhead and fixture_count > 0 else 0
    projected = fixture_calls + status_fixture_overhead
    return {
        "fixture_count": fixture_count,
        "projected_calls": projected,
        "daily_budget": daily_budget,
        "matchday_budget": matchday_budget,
        "trickle_backfill_budget": trickle_backfill_budget,
        "reserve": WORLD_CUP_BUDGET_RESERVE,
        "within_matchday_budget": projected <= matchday_budget,
        "within_daily_budget": projected + trickle_backfill_budget <= daily_budget,
    }


def trickle_backfill_plan(
    *,
    daily_budget: int = WORLD_CUP_DAILY_PROVIDER_BUDGET,
    matchday_projected_calls: int,
    requested_backfill_calls: int,
    reserve: int = WORLD_CUP_BUDGET_RESERVE,
    trickle_cap: int = WORLD_CUP_TRICKLE_BACKFILL_DAILY_BUDGET,
) -> dict[str, int | bool | str | None]:
    remaining_after_matchday = daily_budget - matchday_projected_calls - reserve
    allowed_calls = max(min(requested_backfill_calls, trickle_cap, remaining_after_matchday), 0)
    blocker = None if allowed_calls > 0 else "TRICKLE_BACKFILL_BUDGET_EXHAUSTED"
    return {
        "daily_budget": daily_budget,
        "matchday_projected_calls": matchday_projected_calls,
        "requested_backfill_calls": requested_backfill_calls,
        "reserve": reserve,
        "trickle_cap": trickle_cap,
        "allowed_calls": allowed_calls,
        "allowed": allowed_calls > 0,
        "blocker": blocker,
    }


def saturday_budget_projection(
    *,
    fixture_count: int = 30,
    include_retries: bool = True,
    http_retry_multiplier: int = 1,
) -> dict[str, int | bool]:
    projection = world_cup_matchday_budget_projection(
        fixture_count=fixture_count,
        include_retries=include_retries,
    )
    projected = int(projection["projected_calls"]) * max(http_retry_multiplier, 1)
    return {
        "fixture_count": fixture_count,
        "projected_calls": projected,
        "budget_cap": WORLD_CUP_DAILY_PROVIDER_BUDGET,
        "within_budget": projected <= WORLD_CUP_DAILY_PROVIDER_BUDGET,
    }
