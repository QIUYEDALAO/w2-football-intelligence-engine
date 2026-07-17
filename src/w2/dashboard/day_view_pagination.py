from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

DAY_VIEW_PAGE_SCHEMA_VERSION = "w2.day_view_page.v1"
DAY_VIEW_CURSOR_SCHEMA_VERSION = "w2.day_view_cursor.v1"
DAY_VIEW_SNAPSHOT_SCHEMA_VERSION = "w2.day_view_snapshot.v1"
DEFAULT_DAY_VIEW_PAGE_SIZE = 20
MAX_DAY_VIEW_PAGE_SIZE = 50
MAX_DAY_VIEW_PAGE_BYTES = 512 * 1024
MAX_DAY_VIEW_CARD_BYTES = 24 * 1024
MAX_DAY_VIEW_CURSOR_BYTES = 2048
DAY_VIEW_SORTS = {"BOSS_PRIORITY_KICKOFF", "KICKOFF_ONLY"}


class InvalidDayViewCursor(ValueError):
    pass


class StaleDayViewCursor(ValueError):
    pass


class DayViewPageTooLarge(ValueError):
    pass


@dataclass(frozen=True)
class DayViewIndexEntry:
    fixture_id: str
    kickoff_utc: str
    priority: int
    decision_tier: str
    data_status: str
    lifecycle_status: str
    lock_eligible: bool
    outcome_tracked: bool
    source: str


def make_snapshot_id(
    *,
    api_release_sha: str,
    requested_date: str,
    window: str,
    timezone: str,
    sort: str,
    fixture_rows: Sequence[Mapping[str, Any]],
    ledger_fingerprint: str,
    capture_projection_version: str,
) -> str:
    payload = {
        "schema_version": DAY_VIEW_SNAPSHOT_SCHEMA_VERSION,
        "api_release_sha": api_release_sha,
        "requested_date": requested_date,
        "window": window,
        "timezone": timezone,
        "sort": validate_sort(sort),
        "fixture_rows": [
            {
                "fixture_id": str(row.get("fixture_id") or ""),
                "kickoff_utc": str(row.get("kickoff_utc") or ""),
                "status": str(row.get("status") or ""),
            }
            for row in fixture_rows
        ],
        "ledger_fingerprint": ledger_fingerprint,
        "capture_projection_version": capture_projection_version,
    }
    digest = hashlib.sha256(_canonical(payload)).hexdigest()
    return f"dv_{digest}"


def build_index_entries(
    rows: Sequence[Mapping[str, Any]], summaries: Mapping[str, Any]
) -> list[DayViewIndexEntry]:
    result: list[DayViewIndexEntry] = []
    for row in rows:
        fixture_id = str(row.get("fixture_id") or "")
        if not fixture_id:
            continue
        summary = summaries.get(fixture_id)
        tier = str(_summary_value(summary, "decision_tier", "NOT_READY") or "NOT_READY")
        lock_eligible = _summary_value(summary, "lock_eligible", False) is True
        result.append(
            DayViewIndexEntry(
                fixture_id=fixture_id,
                kickoff_utc=str(row.get("kickoff_utc") or ""),
                priority=_priority(tier, lock_eligible),
                decision_tier=tier,
                data_status=str(_summary_value(summary, "data_status", "BLOCKED") or "BLOCKED"),
                lifecycle_status=str(
                    _summary_value(summary, "lifecycle_status", "DRAFT") or "DRAFT"
                ),
                lock_eligible=lock_eligible,
                outcome_tracked=_summary_value(summary, "outcome_tracked", False) is True,
                source=str(_summary_value(summary, "source", "unavailable") or "unavailable"),
            )
        )
    return result


def _summary_value(summary: Any, key: str, default: Any) -> Any:
    if isinstance(summary, Mapping):
        contract = summary.get("decision_contract")
        if isinstance(contract, Mapping) and contract.get(key) is not None:
            return contract[key]
        return summary.get(key, default)
    return getattr(summary, key, default)


def sort_entries(entries: Sequence[DayViewIndexEntry], sort: str) -> list[DayViewIndexEntry]:
    normalized = validate_sort(sort)
    if normalized == "KICKOFF_ONLY":
        return sorted(entries, key=lambda item: (item.kickoff_utc, item.fixture_id))
    return sorted(
        entries,
        key=lambda item: (item.priority, item.kickoff_utc, item.fixture_id),
    )


def window_counts(entries: Sequence[DayViewIndexEntry]) -> dict[str, Any]:
    tiers = {key: 0 for key in ("RECOMMEND", "ANALYSIS_PICK", "WATCH", "NOT_READY", "SKIP")}
    data = {key: 0 for key in ("READY", "PARTIAL", "STALE", "BLOCKED")}
    lifecycle = {key: 0 for key in ("DRAFT", "VALIDATED", "LOCKED", "SETTLED")}
    for item in entries:
        tiers[item.decision_tier] = tiers.get(item.decision_tier, 0) + 1
        data[item.data_status] = data.get(item.data_status, 0) + 1
        lifecycle[item.lifecycle_status] = lifecycle.get(item.lifecycle_status, 0) + 1
    return {
        "total": len(entries),
        "lock_eligible": sum(item.lock_eligible for item in entries),
        "outcome_tracked": sum(item.outcome_tracked for item in entries),
        "legacy_fallback": sum(item.source == "legacy_fallback" for item in entries),
        "analysis_pick": tiers.get("ANALYSIS_PICK", 0),
        "recommend": tiers.get("RECOMMEND", 0),
        "watch": tiers.get("WATCH", 0),
        "not_ready": tiers.get("NOT_READY", 0),
        "skip": tiers.get("SKIP", 0),
        "ready": data.get("READY", 0),
        "partial": data.get("PARTIAL", 0),
        "stale": data.get("STALE", 0),
        "blocked": data.get("BLOCKED", 0),
        "by_decision_tier": tiers,
        "by_data_status": data,
        "by_lifecycle_status": lifecycle,
    }


def select_page(
    entries: Sequence[DayViewIndexEntry],
    *,
    snapshot_id: str,
    sort: str,
    page_size: int,
    cursor: str | None,
) -> tuple[list[DayViewIndexEntry], int]:
    if not 1 <= page_size <= MAX_DAY_VIEW_PAGE_SIZE:
        raise ValueError("page_size must be between 1 and 50")
    start = 0
    if cursor:
        decoded = decode_cursor(cursor)
        if decoded["snapshot_id"] != snapshot_id or decoded["sort"] != sort:
            raise StaleDayViewCursor("DAYVIEW_CURSOR_STALE")
        identity = (
            int(decoded["last_priority"]),
            str(decoded["last_kickoff_utc"]),
            str(decoded["last_fixture_id"]),
        )
        matches = [
            index
            for index, item in enumerate(entries)
            if (item.priority, item.kickoff_utc, item.fixture_id) == identity
        ]
        if len(matches) != 1:
            raise StaleDayViewCursor("DAYVIEW_CURSOR_STALE")
        start = matches[0] + 1
    return list(entries[start : start + page_size]), start


def encode_cursor(*, snapshot_id: str, sort: str, last: DayViewIndexEntry) -> str:
    payload = {
        "schema_version": DAY_VIEW_CURSOR_SCHEMA_VERSION,
        "snapshot_id": snapshot_id,
        "sort": sort,
        "last_priority": last.priority,
        "last_kickoff_utc": last.kickoff_utc,
        "last_fixture_id": last.fixture_id,
    }
    return base64.urlsafe_b64encode(_canonical(payload)).decode().rstrip("=")


def decode_cursor(cursor: str) -> dict[str, Any]:
    if not cursor or len(cursor.encode()) > MAX_DAY_VIEW_CURSOR_BYTES:
        raise InvalidDayViewCursor("invalid day-view cursor")
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        value = json.loads(base64.urlsafe_b64decode(padded.encode()))
    except (ValueError, json.JSONDecodeError) as error:
        raise InvalidDayViewCursor("invalid day-view cursor") from error
    required = {
        "schema_version",
        "snapshot_id",
        "sort",
        "last_priority",
        "last_kickoff_utc",
        "last_fixture_id",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise InvalidDayViewCursor("invalid day-view cursor")
    if value.get("schema_version") != DAY_VIEW_CURSOR_SCHEMA_VERSION:
        raise InvalidDayViewCursor("invalid day-view cursor")
    if not isinstance(value.get("last_priority"), int):
        raise InvalidDayViewCursor("invalid day-view cursor")
    for key in ("snapshot_id", "sort", "last_kickoff_utc", "last_fixture_id"):
        if not isinstance(value.get(key), str) or not value[key]:
            raise InvalidDayViewCursor("invalid day-view cursor")
    validate_sort(value["sort"])
    return value


def validate_sort(sort: str) -> str:
    if sort not in DAY_VIEW_SORTS:
        raise ValueError("unsupported day-view sort")
    return sort


def pagination_envelope(
    *,
    snapshot_id: str,
    sort: str,
    total_count: int,
    page_size: int,
    returned: Sequence[DayViewIndexEntry],
    start: int,
    truncated_by_byte_budget: bool,
) -> dict[str, Any]:
    consumed = start + len(returned)
    has_more = consumed < total_count
    return {
        "schema_version": DAY_VIEW_PAGE_SCHEMA_VERSION,
        "snapshot_id": snapshot_id,
        "sort": sort,
        "total_count": total_count,
        "returned_count": len(returned),
        "page_size": page_size,
        "has_more": has_more,
        "next_cursor": encode_cursor(snapshot_id=snapshot_id, sort=sort, last=returned[-1])
        if has_more and returned
        else None,
        "truncated_by_byte_budget": truncated_by_byte_budget,
    }


def _priority(tier: str, lock_eligible: bool) -> int:
    if tier == "RECOMMEND" and lock_eligible:
        return 0
    return {"RECOMMEND": 1, "ANALYSIS_PICK": 2, "WATCH": 3, "NOT_READY": 4, "SKIP": 5}.get(tier, 6)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
