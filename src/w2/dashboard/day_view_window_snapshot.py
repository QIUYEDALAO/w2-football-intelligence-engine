from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from w2.dashboard.day_view_pagination import DayViewIndexEntry
from w2.tracking.day_view_capture_index import DayViewCaptureIndex

DAY_VIEW_WINDOW_SNAPSHOT_SCHEMA_VERSION = "w2.day_view_window_snapshot.v1"
DAY_VIEW_SOURCE_FINGERPRINT_SCHEMA_VERSION = "w2.day_view_source_fingerprint.v1"


@dataclass(frozen=True)
class DayViewWindowSnapshot:
    schema_version: str
    snapshot_id: str
    requested_date: str
    window: str
    timezone: str
    sort: str
    release_sha: str
    source_fingerprint: str
    fixture_rows: tuple[Mapping[str, Any], ...]
    sorted_entries: tuple[DayViewIndexEntry, ...]
    counts: Mapping[str, Any]
    capture_index: DayViewCaptureIndex
    materialized_cards: Mapping[str, Mapping[str, Any]]
    materialized_preferred_fixture_ids: frozenset[str]
    next_evaluations: Mapping[str, str]
    market_availability: Mapping[str, bool]
    performance_summary: Mapping[str, Any]
    generated_at: str
    source_status: str


def make_day_view_source_fingerprint(
    *,
    release_sha: str,
    source_watermarks: Mapping[str, Any],
    ledger_fingerprint: str,
    capture_projection_version: str,
) -> str:
    payload = {
        "schema_version": DAY_VIEW_SOURCE_FINGERPRINT_SCHEMA_VERSION,
        "release_sha": release_sha,
        "source_watermarks": dict(source_watermarks),
        "ledger_fingerprint": ledger_fingerprint,
        "capture_projection_version": capture_projection_version,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()
