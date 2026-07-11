from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

FINISHED_STATUSES = {"FT", "AET", "PEN"}


def normalized_finished_results(
    payload: Mapping[str, Any],
    *,
    provider: str,
    confirmed_at: datetime,
    raw_payload_hash: str,
) -> list[dict[str, Any]]:
    response = payload.get("response")
    if not isinstance(response, Sequence) or isinstance(response, str | bytes | bytearray):
        return []
    rows: list[dict[str, Any]] = []
    for item in response:
        if not isinstance(item, Mapping):
            continue
        fixture = item.get("fixture")
        score = item.get("score")
        if not isinstance(fixture, Mapping) or not isinstance(score, Mapping):
            continue
        status_payload = fixture.get("status")
        status = (
            str(status_payload.get("short") or "").upper()
            if isinstance(status_payload, Mapping)
            else str(status_payload or "").upper()
        )
        if status not in FINISHED_STATUSES:
            continue
        fixture_id = str(fixture.get("id") or "")
        if not fixture_id:
            continue
        fulltime = score.get("fulltime")
        home = fulltime.get("home") if isinstance(fulltime, Mapping) else None
        away = fulltime.get("away") if isinstance(fulltime, Mapping) else None
        rows.append(
            {
                "fixture_id": fixture_id,
                "provider": provider,
                "confirmed_at": confirmed_at.astimezone(UTC),
                "raw_payload_hash": raw_payload_hash,
                "result_payload": {
                    "fixture_id": fixture_id,
                    "status": status,
                    "score": {"fulltime": {"home": home, "away": away}},
                },
            }
        )
    return rows
