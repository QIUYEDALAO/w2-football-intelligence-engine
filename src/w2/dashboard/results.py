from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

FINISHED_STATUSES = {"FT", "AET", "PEN", "FINISHED"}
OUTCOME_COLLECTION_DELAY = timedelta(hours=3)


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


def outcome_public_cause(
    *,
    status: Any,
    kickoff_utc: Any,
    as_of: Any,
    is_tracked: bool,
    is_recorded: bool,
) -> str | None:
    if status is None or not str(status).strip():
        return "UNASSESSED"
    normalized = normalize_match_status(status)
    if normalized == "FINISHED":
        return None if is_recorded else "AWAITING_COLLECTION" if is_tracked else "UNASSESSED"
    if normalized in {"POSTPONED", "CANCELLED", "UNKNOWN"}:
        return "UNASSESSED"
    kickoff = _parse_datetime(kickoff_utc)
    observed = _parse_datetime(as_of)
    if kickoff is None or observed is None:
        return "UNASSESSED"
    return (
        "NOT_YET_DUE"
        if observed < kickoff + OUTCOME_COLLECTION_DELAY
        else "AWAITING_COLLECTION"
    )


def selected_day_outcome_cause(
    finished: Sequence[bool], causes: Sequence[str | None]
) -> str | None:
    if not finished:
        return None
    if "AWAITING_COLLECTION" in causes:
        return "AWAITING_COLLECTION"
    if any(
        not done and cause == "UNASSESSED"
        for done, cause in zip(finished, causes, strict=True)
    ):
        return "UNASSESSED"
    return "NOT_YET_DUE" if not any(finished) else None


def selected_day_record_kind(finished: Sequence[bool]) -> str:
    if not finished:
        return "EMPTY"
    if all(finished):
        return "REPLAY"
    if not any(finished):
        return "FORWARD_RECORD"
    return "MIXED_RECORD"


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
