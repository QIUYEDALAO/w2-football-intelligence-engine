from __future__ import annotations

from datetime import UTC, datetime, timedelta

from w2.ingestion.checkpoint_refresh import (
    checkpoint_plan_for_fixture,
    line_jump_confirmation_plan,
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
