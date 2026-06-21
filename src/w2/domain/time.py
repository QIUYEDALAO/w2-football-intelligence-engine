from __future__ import annotations

from datetime import UTC, datetime


def require_utc(value: datetime, field_name: str = "datetime") -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)

