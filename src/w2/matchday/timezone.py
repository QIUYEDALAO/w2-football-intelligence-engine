from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from w2.dashboard.date_window import (
    FOOTBALL_DAY_CUTOFF_HOUR,
    default_football_day,
    football_day_for_kickoff,
    football_day_window,
)

BEIJING_TZ = "Asia/Shanghai"
STORAGE_TZ = "UTC"
WINDOW_SEMANTICS = "LEFT_CLOSED_RIGHT_OPEN"


@dataclass(frozen=True)
class OperationalDayWindow:
    local_date: date
    start_local: datetime
    end_local: datetime
    start_utc: datetime
    end_utc: datetime
    window_semantics: str
    operational_day_key: str

    def contains(self, kickoff_utc: datetime) -> bool:
        if kickoff_utc.tzinfo is None:
            raise ValueError("kickoff_utc must be timezone-aware")
        normalized = kickoff_utc.astimezone(UTC)
        return self.start_utc <= normalized < self.end_utc

    def as_dict(self) -> dict[str, str]:
        return {
            "local_date": self.local_date.isoformat(),
            "start_local": self.start_local.isoformat(),
            "end_local": self.end_local.isoformat(),
            "start_utc": self.start_utc.isoformat().replace("+00:00", "Z"),
            "end_utc": self.end_utc.isoformat().replace("+00:00", "Z"),
            "window_semantics": self.window_semantics,
            "operational_day_key": self.operational_day_key,
        }


class BeijingOperationalDayPolicy:
    def __init__(self, *, operations_timezone: str = BEIJING_TZ) -> None:
        if operations_timezone != BEIJING_TZ:
            raise ValueError("Stage10D supports only Asia/Shanghai operations timezone")
        self.timezone = ZoneInfo(operations_timezone)

    @classmethod
    def from_config(cls, path: Path) -> BeijingOperationalDayPolicy:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("display_timezone") != BEIJING_TZ:
            raise ValueError("display timezone must be Asia/Shanghai")
        if payload.get("operations_timezone") != BEIJING_TZ:
            raise ValueError("operations timezone must be Asia/Shanghai")
        if payload.get("storage_timezone") != STORAGE_TZ:
            raise ValueError("storage timezone must be UTC")
        if payload.get("window_semantics") != WINDOW_SEMANTICS:
            raise ValueError("window semantics must be LEFT_CLOSED_RIGHT_OPEN")
        return cls(operations_timezone=payload["operations_timezone"])

    def window_for_date(self, local_date: date) -> OperationalDayWindow:
        start_utc, end_utc = football_day_window(local_date)
        start_local = start_utc.astimezone(self.timezone)
        end_local = end_utc.astimezone(self.timezone)
        return OperationalDayWindow(
            local_date=local_date,
            start_local=start_local,
            end_local=end_local,
            start_utc=start_utc,
            end_utc=end_utc,
            window_semantics=WINDOW_SEMANTICS,
            operational_day_key=local_date.isoformat(),
        )

    def current_window(self, *, now_utc: datetime | None = None) -> OperationalDayWindow:
        now = now_utc or datetime.now(UTC)
        if now.tzinfo is None:
            raise ValueError("now_utc must be timezone-aware")
        return self.window_for_date(default_football_day(now))

    def provider_utc_dates_for_window(self, window: OperationalDayWindow) -> list[str]:
        cursor = window.start_utc.date()
        end_date = (window.end_utc - timedelta(microseconds=1)).date()
        dates: list[str] = []
        while cursor <= end_date:
            dates.append(cursor.isoformat())
            cursor += timedelta(days=1)
        return dates


class FixtureOperationalDateResolver:
    def __init__(self, *, operations_timezone: str = BEIJING_TZ) -> None:
        if operations_timezone != BEIJING_TZ:
            raise ValueError("Stage10D supports only Asia/Shanghai operations timezone")
        self.timezone = ZoneInfo(operations_timezone)

    def kickoff_beijing(self, kickoff_utc: datetime) -> datetime:
        if kickoff_utc.tzinfo is None:
            raise ValueError("kickoff_utc must be timezone-aware")
        return kickoff_utc.astimezone(self.timezone)

    def operational_date(self, kickoff_utc: datetime) -> date:
        return football_day_for_kickoff(kickoff_utc)

    def annotate(self, kickoff_utc: datetime) -> dict[str, str]:
        beijing = self.kickoff_beijing(kickoff_utc)
        return {
            "kickoff_beijing": beijing.isoformat(),
            "operational_date_beijing": self.operational_date(kickoff_utc).isoformat(),
            "operational_day_cutoff_beijing": f"{FOOTBALL_DAY_CUTOFF_HOUR:02d}:00",
        }


def next_36_hours_window(now_utc: datetime | None = None) -> tuple[datetime, datetime]:
    now = now_utc or datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")
    start = now.astimezone(UTC)
    return start, start + timedelta(hours=36)
