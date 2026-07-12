from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from w2.config import Environment

APPROVED_FIXTURE_IDS = frozenset(
    {"1494207", "1494692", "1494699", "1523196", "1523197", "1523198", "1523200"}
)
MAX_PROVIDER_CALLS = 7
FINISHED_STATUSES = {"FT", "AET", "PEN"}


class ResultClient(Protocol):
    def request_live(self, endpoint: str, params: dict[str, str]) -> Any: ...


class ResultRepository(Protocol):
    def persist_result_backfill_payload(
        self, *, payload: dict[str, Any], captured_at: datetime, provider: str = ...
    ) -> dict[str, Any]: ...


def discover_missing_validation_results(
    runtime_root: Path,
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    cutoff = (now or datetime.now(UTC)).astimezone(UTC) - timedelta(hours=3)
    captures: dict[str, dict[str, Any]] = {}
    settled: set[str] = set()
    ledger_root = runtime_root / "forward_outcome_ledger"
    for path in sorted(ledger_root.glob("*.jsonl")) if ledger_root.exists() else []:
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            fixture_id = str(row.get("fixture_id") or "")
            if not fixture_id:
                continue
            if row.get("record_type") == "outcome" and row.get("settled_side") == "pick":
                settled.add(fixture_id)
                continue
            if str(row.get("record_type") or "capture") != "capture":
                continue
            if str(row.get("decision_tier") or "").upper() != "ANALYSIS_PICK":
                continue
            kickoff = _parse_time(row.get("kickoff_utc"))
            captured_at = _parse_time(row.get("captured_at"))
            if kickoff is None or kickoff > cutoff or captured_at is None or captured_at >= kickoff:
                continue
            current = captures.get(fixture_id)
            current_time = (
                _parse_time(current.get("captured_at"))
                if current is not None
                else None
            )
            if current is None or captured_at > (
                current_time or datetime.min.replace(tzinfo=UTC)
            ):
                captures[fixture_id] = row
    return [
        {
            "fixture_id": fixture_id,
            "kickoff_utc": row.get("kickoff_utc"),
            "captured_at": row.get("captured_at"),
            "competition_id": row.get("competition_id"),
            "home_team_name": row.get("home_team_name"),
            "away_team_name": row.get("away_team_name"),
            "pick": row.get("pick"),
        }
        for fixture_id, row in sorted(captures.items())
        if fixture_id not in settled
    ]


def run_restricted_result_backfill(
    fixture_ids: Sequence[str],
    *,
    environment: Environment | str,
    client: ResultClient,
    repository: ResultRepository | None,
    apply: bool = False,
) -> dict[str, Any]:
    env = environment.value if isinstance(environment, Environment) else str(environment)
    if env != Environment.STAGING.value:
        raise ValueError("RESULT_BACKFILL_STAGING_ONLY")
    requested = list(dict.fromkeys(str(value) for value in fixture_ids))
    if len(requested) > MAX_PROVIDER_CALLS:
        raise ValueError("RESULT_BACKFILL_CALL_CAP_EXCEEDED")
    if not requested or not set(requested).issubset(APPROVED_FIXTURE_IDS):
        raise ValueError("RESULT_BACKFILL_FIXTURE_NOT_APPROVED")
    if apply and repository is None:
        raise ValueError("RESULT_BACKFILL_REPOSITORY_REQUIRED")

    rows: list[dict[str, Any]] = []
    writes = 0
    for fixture_id in requested:
        response = client.request_live("fixtures", {"id": fixture_id})
        payload = response.payload
        items = payload.get("response") if isinstance(payload, Mapping) else None
        if not isinstance(items, list) or len(items) != 1:
            raise ValueError(f"RESULT_BACKFILL_RESPONSE_CARDINALITY:{fixture_id}")
        item = items[0]
        if not isinstance(item, Mapping):
            raise ValueError(f"RESULT_BACKFILL_INVALID_RESPONSE:{fixture_id}")
        fixture = item.get("fixture")
        score = item.get("score")
        returned_id = str(fixture.get("id") or "") if isinstance(fixture, Mapping) else ""
        if returned_id != fixture_id:
            raise ValueError(f"RESULT_BACKFILL_FIXTURE_MISMATCH:{fixture_id}")
        status_payload = fixture.get("status") if isinstance(fixture, Mapping) else None
        status = (
            str(status_payload.get("short") or "").upper()
            if isinstance(status_payload, Mapping)
            else ""
        )
        fulltime = score.get("fulltime") if isinstance(score, Mapping) else None
        home = fulltime.get("home") if isinstance(fulltime, Mapping) else None
        away = fulltime.get("away") if isinstance(fulltime, Mapping) else None
        ready = status in FINISHED_STATUSES and isinstance(home, int) and isinstance(away, int)
        persisted: dict[str, Any] | None = None
        if apply and ready and repository is not None:
            persisted = repository.persist_result_backfill_payload(
                payload=dict(payload), captured_at=response.captured_at
            )
            writes += int(persisted.get("events_inserted") or 0)
        state = (
            "READY_TO_APPLY"
            if ready and not apply
            else "APPLIED"
            if ready
            else "PENDING_RESULT"
        )
        rows.append(
            {
                "fixture_id": fixture_id,
                "status": status,
                "fulltime": {"home": home, "away": away},
                "state": state,
                "persisted": persisted,
            }
        )
    return {
        "status": "PASS",
        "environment": env,
        "dry_run": not apply,
        "provider_calls": len(requested),
        "db_writes": writes,
        "fixtures": rows,
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
