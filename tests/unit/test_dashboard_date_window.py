from __future__ import annotations

from datetime import UTC, date, datetime

from w2.dashboard.date_window import (
    default_football_day,
    football_day_for_kickoff,
    football_day_window,
)


def test_football_day_window_uses_noon_beijing_cutoff() -> None:
    start, end = football_day_window(date(2026, 6, 30))

    assert start == datetime(2026, 6, 30, 4, tzinfo=UTC)
    assert end == datetime(2026, 7, 1, 4, tzinfo=UTC)


def test_default_football_day_before_noon_uses_previous_local_date() -> None:
    assert default_football_day(datetime(2026, 6, 30, 3, 59, tzinfo=UTC)) == date(
        2026,
        6,
        29,
    )
    assert default_football_day(datetime(2026, 6, 30, 4, 0, tzinfo=UTC)) == date(
        2026,
        6,
        30,
    )


def test_football_day_for_kickoff_assigns_morning_games_to_previous_day() -> None:
    assert football_day_for_kickoff(datetime(2026, 7, 1, 3, 30, tzinfo=UTC)) == date(
        2026,
        6,
        30,
    )
    assert football_day_for_kickoff(datetime(2026, 7, 1, 4, 0, tzinfo=UTC)) == date(
        2026,
        7,
        1,
    )
