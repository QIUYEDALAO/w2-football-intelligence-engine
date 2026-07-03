from __future__ import annotations

from datetime import UTC, datetime, timedelta

from w2.ingestion.checkpoint_refresh import (
    checkpoint_plan_for_fixture,
    line_jump_confirmation_plan,
    lineups_retry_plans,
    projected_calls_for_checkpoint_batch,
    saturday_budget_projection,
    select_checkpoint_batch,
)

NOW = datetime(2026, 7, 4, 0, 0, tzinfo=UTC)


def test_checkpoint_plan_generation_is_kickoff_based_and_idempotent_shape() -> None:
    kickoff = datetime(2026, 7, 5, 0, 0, tzinfo=UTC)

    plans = checkpoint_plan_for_fixture(
        fixture_id="fixture-1",
        kickoff_utc=kickoff,
        generated_at_utc=NOW,
    )

    assert [plan.checkpoint for plan in plans] == [
        "OPEN",
        "T24",
        "T12",
        "T6",
        "T3",
        "T1_LINEUPS",
        "T15M_CLOSE",
        "RESULT_POLL",
    ]
    assert plans[0].due_at_utc == NOW
    assert plans[1].due_at_utc == kickoff - timedelta(hours=24)
    assert plans[5].endpoints == ("odds", "lineups")
    assert [plan.plan_id for plan in plans].count("fixture-1:T24") == 1


def test_checkpoint_plan_generation_normalizes_timezone_aware_kickoff() -> None:
    kickoff_tokyo = datetime.fromisoformat("2026-07-05T09:00:00+09:00")

    plans = checkpoint_plan_for_fixture(
        fixture_id="fixture-tz",
        kickoff_utc=kickoff_tokyo,
        generated_at_utc=NOW,
    )

    assert plans[0].kickoff_utc == datetime(2026, 7, 5, 0, 0, tzinfo=UTC)
    assert plans[1].due_at_utc == datetime(2026, 7, 4, 0, 0, tzinfo=UTC)
    assert plans[6].checkpoint == "T15M_CLOSE"
    assert plans[6].due_at_utc == datetime(2026, 7, 4, 23, 45, tzinfo=UTC)


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


def test_saturday_30_fixture_budget_stays_under_800_including_retries() -> None:
    projection = saturday_budget_projection(fixture_count=30, include_retries=True)

    assert projection["within_budget"] is True
    assert projection["projected_calls"] <= 800
