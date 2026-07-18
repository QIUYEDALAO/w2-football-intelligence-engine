from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from w2.ingestion.checkpoint_refresh import (
    checkpoint_plan_for_fixture,
    line_jump_confirmation_plan,
    lineups_retry_plans,
    projected_calls_for_checkpoint_batch,
    saturday_budget_projection,
    select_checkpoint_batch,
    trickle_backfill_plan,
    world_cup_matchday_budget_projection,
)

NOW = datetime(2026, 7, 4, 0, 0, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[2]


def test_checkpoint_plan_generation_is_kickoff_based_and_idempotent_shape() -> None:
    kickoff = datetime(2026, 7, 5, 0, 0, tzinfo=UTC)

    plans = checkpoint_plan_for_fixture(
        fixture_id="fixture-1",
        kickoff_utc=kickoff,
        generated_at_utc=NOW,
    )

    assert [plan.checkpoint for plan in plans] == [
        "OPEN",
        "T6_ODDS",
        "T1_LINEUPS",
        "T15M_CLOSE",
    ]
    assert plans[0].due_at_utc == NOW
    assert plans[1].due_at_utc == kickoff - timedelta(hours=6)
    assert plans[2].due_at_utc == kickoff - timedelta(hours=1)
    assert plans[2].endpoints == ("odds", "lineups")
    assert [plan.plan_id for plan in plans].count("fixture-1:T1_LINEUPS") == 1


def test_checkpoint_plan_generation_normalizes_timezone_aware_kickoff() -> None:
    kickoff_tokyo = datetime.fromisoformat("2026-07-05T09:00:00+09:00")

    plans = checkpoint_plan_for_fixture(
        fixture_id="fixture-tz",
        kickoff_utc=kickoff_tokyo,
        generated_at_utc=NOW,
    )

    assert plans[0].kickoff_utc == datetime(2026, 7, 5, 0, 0, tzinfo=UTC)
    assert plans[1].due_at_utc == datetime(2026, 7, 4, 18, 0, tzinfo=UTC)
    assert plans[2].due_at_utc == datetime(2026, 7, 4, 23, 0, tzinfo=UTC)
    assert plans[3].checkpoint == "T15M_CLOSE"
    assert plans[3].due_at_utc == datetime(2026, 7, 4, 23, 45, tzinfo=UTC)


def test_line_jump_confirmation_triggers_after_half_ball_move() -> None:
    kickoff = datetime(2026, 7, 5, 0, 0, tzinfo=UTC)

    plan = line_jump_confirmation_plan(
        fixture_id="fixture-1",
        kickoff_utc=kickoff,
        previous_line=-1.25,
        current_line=-1.75,
        observed_at_utc=NOW,
    )

    assert plan is not None
    assert plan.checkpoint == "LINE_JUMP_CONFIRMATION"
    assert plan.due_at_utc == NOW + timedelta(minutes=10)
    assert plan.endpoints == ("odds",)


def test_line_jump_confirmation_ignores_small_moves() -> None:
    assert (
        line_jump_confirmation_plan(
            fixture_id="fixture-1",
            kickoff_utc=NOW + timedelta(hours=6),
            previous_line=-1.25,
            current_line=-1.5,
            observed_at_utc=NOW,
        )
        is None
    )


def test_lineups_provider_empty_schedules_t45_and_t30_retries_at_due_windows() -> None:
    kickoff = NOW + timedelta(hours=1)

    t45_plans = lineups_retry_plans(
        fixture_id="fixture-lineups",
        kickoff_utc=kickoff,
        now=NOW + timedelta(minutes=20),
        lineups_status="PROVIDER_EMPTY",
    )
    t30_plans = lineups_retry_plans(
        fixture_id="fixture-lineups",
        kickoff_utc=kickoff,
        now=NOW + timedelta(minutes=30),
        lineups_status="PROVIDER_EMPTY",
    )

    assert [plan.checkpoint for plan in t45_plans] == ["T45_LINEUPS_RETRY"]
    assert [plan.checkpoint for plan in t30_plans] == [
        "T45_LINEUPS_RETRY",
        "T30_LINEUPS_RETRY",
    ]
    plans = [*t45_plans, *t30_plans]
    assert all(plan.endpoints == ("lineups",) for plan in plans)
    assert all(plan.source == "lineups_retry" for plan in plans)


def test_checkpoint_batch_respects_hard_cap() -> None:
    plans = [
        *checkpoint_plan_for_fixture(
            fixture_id="a",
            kickoff_utc=NOW + timedelta(hours=1),
            generated_at_utc=NOW,
        )[:2],
        *checkpoint_plan_for_fixture(
            fixture_id="b",
            kickoff_utc=NOW + timedelta(hours=1),
            generated_at_utc=NOW,
        )[:2],
    ]

    selected, projected = select_checkpoint_batch(plans, hard_cap=4)

    assert len(selected) == 3
    assert projected == projected_calls_for_checkpoint_batch(selected)
    assert projected <= 4


def test_world_cup_five_fixture_budget_stays_under_100_including_retries() -> None:
    projection = world_cup_matchday_budget_projection(fixture_count=5, include_retries=True)

    assert projection["within_daily_budget"] is True
    assert projection["projected_calls"] <= 100
    assert projection["trickle_backfill_budget"] == 0


def test_saturday_30_fixture_budget_no_longer_fits_world_cup_100_call_mode() -> None:
    projection = saturday_budget_projection(fixture_count=30, include_retries=True)

    assert projection["within_budget"] is False
    assert projection["projected_calls"] > 100


def test_trickle_backfill_plan_never_steals_matchday_reserve() -> None:
    quiet_day = trickle_backfill_plan(
        matchday_projected_calls=40,
        requested_backfill_calls=12,
    )
    busy_day = trickle_backfill_plan(
        matchday_projected_calls=78,
        requested_backfill_calls=12,
    )

    assert quiet_day["allowed_calls"] == 0
    assert quiet_day["allowed"] is False
    assert quiet_day["blocker"] == "TRICKLE_BACKFILL_BUDGET_EXHAUSTED"
    assert busy_day["allowed_calls"] == 0
    assert busy_day["allowed"] is False


def test_world_cup_policy_disables_trickle_backfill_until_final_hibernation() -> None:
    payload = json.loads(
        (ROOT / "config/policies/future_fixture_refresh.v1.json").read_text(encoding="utf-8")
    )
    policy = next(
        item
        for item in payload["competitions"]
        if item["competition_id"] == "world_cup_2026"
    )

    assert policy["daily_hard_cap"] == 120
    assert policy["daily_reserve"] == 0
    assert policy["request_budget"] == 30
    assert policy["checkpoint_mode"] == "world_cup_three_checkpoint"
    assert policy["trickle_backfill_daily_budget"] == 0


def test_hibernate_workorder_records_post_final_trickle_switch_to_60_40() -> None:
    text = (ROOT / "docs/W2_HIBERNATE_WAKEUP_A160_WORKORDER.md").read_text(
        encoding="utf-8"
    )

    assert "trickle_backfill_daily_budget=60" in text
    assert "daily_reserve=40" in text
