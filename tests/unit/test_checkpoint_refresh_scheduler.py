from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from w2.ingestion.checkpoint_refresh import (
    ACTIVE_ODDS_CHECKPOINT_PREFIX,
    active_odds_checkpoint_plan,
    checkpoint_plan_for_fixture,
    dedupe_active_odds_plans,
    line_jump_confirmation_plan,
    lineups_retry_plans,
    prioritize_checkpoint_plans,
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
    assert plans[1].endpoints == ("odds",)
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


def test_missed_t6_checkpoint_is_not_backfilled() -> None:
    plans = checkpoint_plan_for_fixture(
        fixture_id="fixture-missed-t6",
        kickoff_utc=NOW + timedelta(hours=5),
        generated_at_utc=NOW,
    )

    t6 = next(plan for plan in plans if plan.checkpoint == "T6_ODDS")

    assert t6.due_at_utc == NOW - timedelta(hours=1)
    assert t6.status == "MISSED"


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
        *[plan for plan in checkpoint_plan_for_fixture(
            fixture_id="a",
            kickoff_utc=NOW + timedelta(hours=1),
            generated_at_utc=NOW,
        ) if plan.checkpoint in {"OPEN", "T1_LINEUPS"}],
        *[plan for plan in checkpoint_plan_for_fixture(
            fixture_id="b",
            kickoff_utc=NOW + timedelta(hours=1),
            generated_at_utc=NOW,
        ) if plan.checkpoint in {"OPEN", "T1_LINEUPS"}],
    ]

    selected, projected = select_checkpoint_batch(plans, hard_cap=5)

    assert len(selected) == 2
    assert projected == projected_calls_for_checkpoint_batch(selected)
    assert projected <= 5


def test_active_odds_plan_starts_inside_t6_without_backfilling_t6() -> None:
    kickoff = NOW + timedelta(hours=5)

    plan = active_odds_checkpoint_plan(
        fixture_id="active-stale",
        kickoff_utc=kickoff,
        now=NOW,
        latest_quote_at_utc=NOW - timedelta(hours=2),
    )

    assert plan is not None
    assert plan.checkpoint.startswith(ACTIVE_ODDS_CHECKPOINT_PREFIX)
    assert plan.checkpoint != "T6_ODDS"
    assert plan.due_at_utc == NOW
    assert plan.endpoints == ("odds",)


def test_active_odds_plan_waits_thirty_minutes_from_latest_quote_or_attempt() -> None:
    kickoff = NOW + timedelta(hours=5)

    from_quote = active_odds_checkpoint_plan(
        fixture_id="active-fresh",
        kickoff_utc=kickoff,
        now=NOW,
        latest_quote_at_utc=NOW - timedelta(minutes=10),
    )
    from_attempt = active_odds_checkpoint_plan(
        fixture_id="active-empty",
        kickoff_utc=kickoff,
        now=NOW,
        latest_quote_at_utc=NOW - timedelta(hours=2),
        latest_attempt_at_utc=NOW - timedelta(minutes=5),
    )

    assert from_quote is not None
    assert from_quote.due_at_utc == NOW + timedelta(minutes=20)
    assert from_attempt is not None
    assert from_attempt.due_at_utc == NOW + timedelta(minutes=25)


def test_active_odds_plan_stops_at_t15_and_named_due_checkpoint_wins() -> None:
    kickoff = NOW + timedelta(minutes=15)
    assert (
        active_odds_checkpoint_plan(
            fixture_id="too-late",
            kickoff_utc=kickoff,
            now=NOW,
        )
        is None
    )

    kickoff = NOW + timedelta(hours=1)
    named = next(
        plan
        for plan in checkpoint_plan_for_fixture(
            fixture_id="dedupe",
            kickoff_utc=kickoff,
            generated_at_utc=NOW,
        )
        if plan.checkpoint == "T1_LINEUPS"
    )
    active = active_odds_checkpoint_plan(
        fixture_id="dedupe",
        kickoff_utc=kickoff,
        now=NOW,
        latest_quote_at_utc=NOW - timedelta(hours=2),
    )

    assert active is not None
    assert dedupe_active_odds_plans([active, named]) == [named]


def test_checkpoint_priority_prefers_today_nearest_kickoff() -> None:
    future = checkpoint_plan_for_fixture(
        fixture_id="future",
        kickoff_utc=NOW + timedelta(days=1, hours=1),
        generated_at_utc=NOW,
    )[0]
    later_today = checkpoint_plan_for_fixture(
        fixture_id="later-today",
        kickoff_utc=NOW + timedelta(hours=8),
        generated_at_utc=NOW,
    )[0]
    nearer_today = checkpoint_plan_for_fixture(
        fixture_id="nearer-today",
        kickoff_utc=NOW + timedelta(hours=2),
        generated_at_utc=NOW,
    )[0]

    prioritized = prioritize_checkpoint_plans(
        [future, later_today, nearer_today],
        now=NOW,
    )

    assert [plan.fixture_id for plan in prioritized] == [
        "nearer-today",
        "later-today",
        "future",
    ]


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


def test_world_cup_is_absent_from_live_refresh_policy_after_archive() -> None:
    payload = json.loads(
        (ROOT / "config/policies/future_fixture_refresh.v1.json").read_text(encoding="utf-8")
    )
    assert "world_cup_2026" not in {
        item["competition_id"] for item in payload["competitions"]
    }


def test_hibernate_workorder_records_post_final_trickle_switch_to_60_40() -> None:
    text = (ROOT / "docs/W2_HIBERNATE_WAKEUP_A160_WORKORDER.md").read_text(
        encoding="utf-8"
    )

    assert "trickle_backfill_daily_budget=60" in text
    assert "daily_reserve=40" in text
