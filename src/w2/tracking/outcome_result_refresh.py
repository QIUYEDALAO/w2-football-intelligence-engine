from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from w2.ingestion.future_refresh_repository import FutureRefreshDbRepository
from w2.providers.api_football import ApiFootballClient, LiveApiFootballResponse
from w2.providers.control import env_int
from w2.tracking.forward_outcome_ledger import (
    VOID_STATUSES,
    backfill_outcomes,
    pending_outcome_entries,
)

REFRESH_SCHEMA_VERSION = "w2.outcome_result_refresh.v1"
STATE_FILE = "forward_outcome_result_refresh_state.json"
CHECKPOINT_HOURS = (3, 6, 12, 24, 48)


class FixtureResultClient(Protocol):
    def request_live(self, endpoint: str, params: dict[str, str]) -> LiveApiFootballResponse: ...


def runtime_root_from_env() -> Path:
    return Path(os.environ.get("W2_FORWARD_OUTCOME_RUNTIME_ROOT", "/app/runtime"))


def run_outcome_result_refresh(
    *,
    runtime_root: Path,
    client: FixtureResultClient | None = None,
    repository: FutureRefreshDbRepository | None = None,
    now: datetime | None = None,
    dry_run: bool = True,
    write_artifacts: bool = False,
    max_fixtures: int = 20,
) -> dict[str, Any]:
    resolved_now = (now or datetime.now(UTC)).astimezone(UTC)
    pending = pending_outcome_entries(runtime_root, now=resolved_now)
    state_path = runtime_root / STATE_FILE
    state = _load_state(state_path)
    fixtures = _due_fixtures(pending, state=state, now=resolved_now)
    selected = fixtures[: max(0, min(max_fixtures, 20))]
    if not selected:
        return _result(
            status="NO_DUE_WORK",
            pending=pending,
            selected=[],
            provider_calls=0,
            db_writes=0,
            settlement=None,
        )

    repo = repository or FutureRefreshDbRepository()
    day_start = resolved_now.replace(hour=0, minute=0, second=0, microsecond=0)
    daily_cap = max(env_int("W2_PROVIDER_DAILY_HARD_CAP", default=120), 0)
    calls_today = repo.request_count_since(day_start)
    remaining = max(daily_cap - calls_today, 0)
    if remaining <= 0:
        return _result(
            status="PARTIAL",
            pending=pending,
            selected=[],
            provider_calls=0,
            db_writes=0,
            settlement=None,
            blockers=["PROVIDER_DAILY_HARD_CAP_REACHED"],
        )
    selected = selected[:remaining]
    resolved_client = client or ApiFootballClient(
        allow_live=True,
        allowed_live_endpoints=frozenset({"fixtures"}),
    )
    provider_calls = 0
    db_writes = 0
    result_items: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []
    blockers: list[str] = []
    for fixture in selected:
        fixture_id = str(fixture["fixture_id"])
        checked_at = resolved_now.isoformat().replace("+00:00", "Z")
        try:
            response = resolved_client.request_live("fixtures", {"id": fixture_id})
            provider_calls += 1
            payload = response.payload
            if write_artifacts and not dry_run:
                sha256 = hashlib.sha256(
                    json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest()
                repo.save_raw_payload(
                    sha256=sha256,
                    endpoint="fixtures",
                    captured_at=response.captured_at,
                    payload=payload,
                )
                db_writes += 1
            item = _single_fixture(payload, fixture_id)
            normalized = _normalize_result(item, fixture=fixture, now=resolved_now)
            if normalized is not None:
                result_items.append(normalized)
            checks.append(
                {
                    "fixture_id": fixture_id,
                    "checked_at_utc": checked_at,
                    "status": _provider_status(item) or "RESULT_MISSING",
                    "next_check_at_utc": _next_check_at(fixture, resolved_now, item),
                }
            )
        except Exception as exc:  # provider failures are reported, never converted to VOID
            blockers.append(f"{fixture_id}:{type(exc).__name__}")
            checks.append(
                {
                    "fixture_id": fixture_id,
                    "checked_at_utc": checked_at,
                    "status": "RESULT_MISSING",
                    "next_check_at_utc": (resolved_now + timedelta(hours=1))
                    .isoformat()
                    .replace("+00:00", "Z"),
                }
            )

    settlement = backfill_outcomes(
        runtime_root,
        {"results": result_items},
        dry_run=dry_run,
        write_artifacts=write_artifacts,
        settled_at=resolved_now,
    )
    if write_artifacts and not dry_run:
        _save_state(state_path, state, checks)
    unresolved = int(settlement.get("unresolved_count") or 0)
    status = "PASS" if not blockers and unresolved == 0 else "PARTIAL"
    return _result(
        status=status,
        pending=pending,
        selected=checks,
        provider_calls=provider_calls,
        db_writes=db_writes,
        settlement=settlement,
        blockers=blockers,
        results=result_items,
    )


def _due_fixtures(
    pending: list[dict[str, Any]],
    *,
    state: Mapping[str, Any],
    now: datetime,
) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    fixture_state = state.get("fixtures") if isinstance(state.get("fixtures"), Mapping) else {}
    for row in pending:
        fixture_id = str(row.get("fixture_id") or "")
        if not fixture_id or not row.get("due"):
            continue
        saved = fixture_state.get(fixture_id) if isinstance(fixture_state, Mapping) else None
        next_check = (
            _parse_time(saved.get("next_check_at_utc")) if isinstance(saved, Mapping) else None
        )
        if next_check is not None and now < next_check:
            continue
        unique.setdefault(fixture_id, row)
    return sorted(
        unique.values(), key=lambda row: (str(row.get("kickoff_utc")), str(row["fixture_id"]))
    )


def _single_fixture(payload: Mapping[str, Any], fixture_id: str) -> Mapping[str, Any] | None:
    response = payload.get("response")
    if not isinstance(response, list):
        return None
    matches = [
        item
        for item in response
        if isinstance(item, Mapping)
        and str(
            (item.get("fixture") or {}).get("id")
            if isinstance(item.get("fixture"), Mapping)
            else ""
        )
        == fixture_id
    ]
    return matches[0] if len(matches) == 1 else None


def _normalize_result(
    item: Mapping[str, Any] | None,
    *,
    fixture: Mapping[str, Any],
    now: datetime,
) -> dict[str, Any] | None:
    if item is None:
        return None
    fixture_id = str(fixture["fixture_id"])
    status = _provider_status(item)
    original_kickoff = _parse_time(fixture.get("kickoff_utc"))
    fixture_value = item.get("fixture")
    provider_fixture: Mapping[str, Any] = (
        fixture_value if isinstance(fixture_value, Mapping) else {}
    )
    revised_kickoff = _parse_time(provider_fixture.get("date"))
    if status in VOID_STATUSES:
        return {"fixture_id": fixture_id, "status": status}
    postponed_over_48h = (
        status == "PST"
        and original_kickoff is not None
        and now >= original_kickoff + timedelta(hours=48)
    )
    rescheduled_over_48h = (
        status == "NS"
        and original_kickoff is not None
        and revised_kickoff is not None
        and revised_kickoff > original_kickoff + timedelta(hours=48)
    )
    if postponed_over_48h or rescheduled_over_48h:
        return {
            "fixture_id": fixture_id,
            "status": status,
            "void_reason": "VOID_POSTPONED_OVER_48H",
            "revised_kickoff_utc": revised_kickoff.isoformat().replace("+00:00", "Z")
            if revised_kickoff
            else None,
        }
    if status not in {"FT", "AET", "PEN"}:
        return None
    score_value = item.get("score")
    score: Mapping[str, Any] = score_value if isinstance(score_value, Mapping) else {}
    fulltime_value = score.get("fulltime")
    fulltime: Mapping[str, Any] = fulltime_value if isinstance(fulltime_value, Mapping) else {}
    home = _int(fulltime.get("home"))
    away = _int(fulltime.get("away"))
    if home is None or away is None:
        return None
    return {
        "fixture_id": fixture_id,
        "status": status,
        "score": {"fulltime": {"home": home, "away": away}},
        "revised_kickoff_utc": revised_kickoff.isoformat().replace("+00:00", "Z")
        if revised_kickoff
        else None,
    }


def _next_check_at(
    fixture: Mapping[str, Any], now: datetime, item: Mapping[str, Any] | None
) -> str | None:
    status = _provider_status(item)
    if status in {"FT", "AET", "PEN", *VOID_STATUSES}:
        return None
    kickoff = _parse_time(fixture.get("kickoff_utc"))
    if kickoff is None:
        next_check = now + timedelta(days=1)
    else:
        elapsed = (now - kickoff).total_seconds() / 3600
        future = [hours for hours in CHECKPOINT_HOURS if hours > elapsed]
        next_check = kickoff + timedelta(hours=future[0]) if future else now + timedelta(days=1)
    return next_check.isoformat().replace("+00:00", "Z")


def _provider_status(item: Mapping[str, Any] | None) -> str:
    if item is None:
        return ""
    fixture_value = item.get("fixture")
    fixture: Mapping[str, Any] = fixture_value if isinstance(fixture_value, Mapping) else {}
    status_value = fixture.get("status")
    status: Mapping[str, Any] = status_value if isinstance(status_value, Mapping) else {}
    return str(status.get("short") or "").upper()


def _load_state(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schema_version": REFRESH_SCHEMA_VERSION, "fixtures": {}}
    return (
        payload
        if isinstance(payload, dict)
        else {"schema_version": REFRESH_SCHEMA_VERSION, "fixtures": {}}
    )


def _save_state(path: Path, state: dict[str, Any], checks: list[dict[str, Any]]) -> None:
    fixtures = state.setdefault("fixtures", {})
    if not isinstance(fixtures, dict):
        fixtures = {}
        state["fixtures"] = fixtures
    for check in checks:
        fixtures[str(check["fixture_id"])] = check
    state["schema_version"] = REFRESH_SCHEMA_VERSION
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(state, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _result(
    *,
    status: str,
    pending: list[dict[str, Any]],
    selected: list[dict[str, Any]],
    provider_calls: int,
    db_writes: int,
    settlement: Mapping[str, Any] | None,
    blockers: list[str] | None = None,
    results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": REFRESH_SCHEMA_VERSION,
        "status": status,
        "pending_count": len(pending),
        "due_fixture_count": len({str(row["fixture_id"]) for row in pending if row.get("due")}),
        "selected_fixture_count": len(selected),
        "provider_calls": provider_calls,
        "db_writes": db_writes,
        "settlement_write": False,
        "selected": selected,
        "results": results or [],
        "settlement": dict(settlement) if settlement is not None else None,
        "blockers": blockers or [],
    }


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _int(value: Any) -> int | None:
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
