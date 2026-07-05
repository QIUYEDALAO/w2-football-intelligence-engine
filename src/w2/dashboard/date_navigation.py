from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

SOURCE = "w2.dashboard.date_navigation.v1"


def build_date_navigation(
    football_day: str | date,
    *,
    as_of: str | datetime | None = None,
    has_checkpoint: bool = False,
    checkpoint_key: str | None = None,
    min_date: str | None = None,
    max_date: str | None = None,
) -> dict[str, Any]:
    current = _date(football_day)
    today = _today(as_of)
    previous = current - timedelta(days=1)
    next_day = current + timedelta(days=1)
    fallback_mode = "checkpoint" if has_checkpoint else "read_model"
    warning = None
    if current > today:
        fallback_mode = "future_day"
        warning = "未来日期可能没有完整数据"
    elif not has_checkpoint:
        warning = "未发现 day_view checkpoint，使用只读 read-model fallback"
    return {
        "current_date": current.isoformat(),
        "previous_date": previous.isoformat(),
        "next_date": next_day.isoformat(),
        "today_date": today.isoformat(),
        "is_today": current == today,
        "can_go_previous": _can_go_previous(current, min_date),
        "can_go_next": _can_go_next(current, max_date),
        "has_checkpoint": has_checkpoint,
        "checkpoint_key": checkpoint_key or f"dashboard:day_view:{current.isoformat()}",
        "source": SOURCE,
        "fallback_mode": fallback_mode,
        "warning": warning,
    }


def _date(value: str | date) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def _today(as_of: str | datetime | None) -> date:
    if isinstance(as_of, datetime):
        actual = as_of
    elif as_of:
        actual = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
    else:
        actual = datetime.now(UTC)
    if actual.tzinfo is None:
        actual = actual.replace(tzinfo=UTC)
    return actual.astimezone(UTC).date()


def _can_go_previous(current: date, min_date: str | None) -> bool:
    if not min_date:
        return True
    return current > date.fromisoformat(min_date)


def _can_go_next(current: date, max_date: str | None) -> bool:
    if not max_date:
        return True
    return current < date.fromisoformat(max_date)
