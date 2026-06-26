from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

FINISHED_STATUSES = {"FT", "AET", "PEN", "FINISHED"}


def normalize_match_status(status: Any) -> str:
    raw = str(status or "").upper()
    if raw in FINISHED_STATUSES:
        return "FINISHED"
    if raw in {"1H", "2H", "HT", "ET", "BT", "P", "LIVE", "IN_PLAY"}:
        return "LIVE"
    if raw in {"PST", "POSTPONED"}:
        return "POSTPONED"
    if raw in {"CANC", "CANCELLED"}:
        return "CANCELLED"
    if raw in {"NS", "TBD", "UPCOMING", ""}:
        return "UPCOMING"
    return "UNKNOWN"


def result_from_provider_fixture(item: dict[str, Any]) -> dict[str, Any] | None:
    fixture = _record(item.get("fixture"))
    status = _record(fixture.get("status")).get("short")
    if str(status or "").upper() not in FINISHED_STATUSES:
        return None
    goals = _record(item.get("goals"))
    home_goals = _int_or_none(goals.get("home"))
    away_goals = _int_or_none(goals.get("away"))
    if home_goals is None or away_goals is None:
        fulltime = _record(_record(item.get("score")).get("fulltime"))
        home_goals = _int_or_none(fulltime.get("home"))
        away_goals = _int_or_none(fulltime.get("away"))
    if home_goals is None or away_goals is None:
        return None
    settled_at = _parse_datetime(fixture.get("date")) or datetime.now(UTC)
    return {
        "status": "FINISHED",
        "home_goals": home_goals,
        "away_goals": away_goals,
        "final_score": f"{home_goals}-{away_goals}",
        "total_goals": home_goals + away_goals,
        "result_source": "provider_fixture_payload",
        "settled_at": settled_at,
    }


def result_from_dashboard_row(row: dict[str, Any]) -> dict[str, Any] | None:
    embedded = row.get("_result")
    if isinstance(embedded, dict):
        return embedded
    home_goals = _int_or_none(row.get("home_goals"))
    away_goals = _int_or_none(row.get("away_goals"))
    if home_goals is None or away_goals is None:
        return None
    return {
        "status": "FINISHED",
        "home_goals": home_goals,
        "away_goals": away_goals,
        "final_score": f"{home_goals}-{away_goals}",
        "total_goals": home_goals + away_goals,
        "result_source": str(row.get("result_source") or "dashboard_row"),
        "settled_at": row.get("settled_at"),
    }


def _record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None

