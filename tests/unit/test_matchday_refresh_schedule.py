from __future__ import annotations

from datetime import UTC, datetime, timedelta

from w2.refresh.matchday_schedule import (
    MatchdayRefreshPolicy,
    build_matchday_refresh_plan,
    estimate_refresh_tick_calls,
)

AS_OF = datetime(2026, 7, 4, 0, 0, tzinfo=UTC)
KICKOFF = AS_OF + timedelta(hours=30)


def _fixtures(count: int, kickoff: datetime = KICKOFF) -> list[dict[str, str]]:
    return [
        {
            "fixture_id": f"fixture-{index}",
            "competition_id": "allsvenskan",
            "kickoff_utc": kickoff.isoformat(),
        }
        for index in range(count)
    ]


def test_generates_kickoff_aware_controlled_ticks() -> None:
    ticks = build_matchday_refresh_plan(
        _fixtures(1),
        as_of=AS_OF,
        policy=MatchdayRefreshPolicy(competition_id="allsvenskan"),
    )

    assert [tick.label for tick in ticks] == [
        "T24_ODDS",
        "T12_ODDS",
        "T6_ODDS",
        "T3_ODDS",
        "T60_ODDS_LINEUPS",
        "T45_LINEUPS_RETRY",
        "T30_LINEUPS_RETRY",
        "T30_FINAL_PREMATCH",
    ]
    assert [tick.offset_seconds_before_kickoff for tick in ticks] == [
        24 * 60 * 60,
        12 * 60 * 60,
        6 * 60 * 60,
        3 * 60 * 60,
        60 * 60,
        45 * 60,
        30 * 60,
        30 * 60,
    ]
    assert all(tick.scheduled_at >= AS_OF for tick in ticks)


def test_no_sixty_second_loop_or_random_task_key() -> None:
    policy = MatchdayRefreshPolicy(competition_id="allsvenskan", min_interval_seconds=60)
    first = build_matchday_refresh_plan(_fixtures(2), as_of=AS_OF, policy=policy)
    second = build_matchday_refresh_plan(_fixtures(2), as_of=AS_OF, policy=policy)

    assert policy.effective_min_interval_seconds == 900
    assert [tick.task_key for tick in first] == [tick.task_key for tick in second]
    assert all("matchday-refresh:" in tick.task_key for tick in first)


def test_endpoint_allowlist_skips_unauthorized_endpoints() -> None:
    policy = MatchdayRefreshPolicy(
        competition_id="allsvenskan",
        allowed_endpoints=(
            "status",
            "fixtures",
            "odds",
            "lineups",
            "statistics",
            "injuries",
            "h2h",
            "history",
            "xg",
        ),
    )
    tick = build_matchday_refresh_plan(_fixtures(1), as_of=AS_OF, policy=policy)[0]

    assert tick.allowed_endpoints == ("status", "fixtures", "odds", "lineups")
    assert tick.skipped_endpoints == ("statistics", "injuries", "h2h", "history", "xg")
    assert "ENDPOINT_NOT_AUTHORIZED:statistics" in tick.blockers
    assert tick.projected_calls_by_endpoint == {
        "status": 1,
        "fixtures": 1,
        "odds": 1,
        "lineups": 1,
    }


def test_projected_calls_for_nine_fixtures_stays_under_default_cap() -> None:
    calls = estimate_refresh_tick_calls(
        [f"fixture-{index}" for index in range(9)],
        ("status", "fixtures", "odds", "lineups", "statistics"),
    )
    tick = build_matchday_refresh_plan(
        _fixtures(9),
        as_of=AS_OF,
        policy=MatchdayRefreshPolicy(competition_id="allsvenskan"),
    )[0]

    assert calls == {"status": 1, "fixtures": 1, "odds": 9, "lineups": 9}
    assert tick.projected_calls == 20
    assert tick.status == "PLANNED"


def test_projected_calls_above_hard_cap_blocks_with_zero_provider_calls() -> None:
    tick = build_matchday_refresh_plan(
        _fixtures(15),
        as_of=AS_OF,
        policy=MatchdayRefreshPolicy(competition_id="allsvenskan"),
    )[0]
    payload = tick.as_dict()

    assert tick.projected_calls == 32
    assert tick.status == "BLOCKED"
    assert "PROVIDER_REFRESH_BUDGET_TOO_HIGH" in tick.blockers
    assert payload["provider_calls"] == 0


def test_all_unauthorized_endpoints_blocks_without_projected_calls() -> None:
    tick = build_matchday_refresh_plan(
        _fixtures(3),
        as_of=AS_OF,
        policy=MatchdayRefreshPolicy(
            competition_id="allsvenskan",
            allowed_endpoints=("statistics", "injuries"),
        ),
    )[0]

    assert tick.allowed_endpoints == ()
    assert tick.projected_calls == 0
    assert tick.status == "BLOCKED"
    assert "NO_AUTHORIZED_ENDPOINTS" in tick.blockers
