from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

FOOTBALL_DAY_TZ = ZoneInfo("Asia/Shanghai")
FOOTBALL_DAY_CUTOFF_HOUR = 12


def default_football_day(now_utc: datetime) -> date:
    if now_utc.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")
    local = now_utc.astimezone(FOOTBALL_DAY_TZ)
    if local.hour >= FOOTBALL_DAY_CUTOFF_HOUR:
        return local.date()
    return local.date() - timedelta(days=1)


def football_day_for_kickoff(kickoff_utc: datetime) -> date:
    if kickoff_utc.tzinfo is None:
        raise ValueError("kickoff_utc must be timezone-aware")
    local = kickoff_utc.astimezone(FOOTBALL_DAY_TZ)
    if local.hour >= FOOTBALL_DAY_CUTOFF_HOUR:
        return local.date()
    return local.date() - timedelta(days=1)


def football_day_window(selected_date: date) -> tuple[datetime, datetime]:
    start_local = datetime.combine(
        selected_date,
        time(FOOTBALL_DAY_CUTOFF_HOUR, 0, 0),
        tzinfo=FOOTBALL_DAY_TZ,
    )
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)
