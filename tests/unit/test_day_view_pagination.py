from __future__ import annotations

from dataclasses import replace

import pytest

from w2.dashboard.day_view_pagination import (
    InvalidDayViewCursor,
    StaleDayViewCursor,
    build_index_entries,
    decode_cursor,
    encode_cursor,
    make_snapshot_id,
    select_page,
    sort_entries,
    window_counts,
)


def _rows(count: int) -> list[dict[str, str]]:
    return [
        {
            "fixture_id": str(index),
            "kickoff_utc": f"2026-07-{16 + index // 24:02d}T{index % 24:02d}:00:00Z",
            "status": "NS",
        }
        for index in range(count)
    ]


def _snapshot(rows: list[dict[str, str]]) -> str:
    return make_snapshot_id(
        api_release_sha="sha",
        requested_date="2026-07-16",
        window="future",
        timezone="UTC",
        sort="BOSS_PRIORITY_KICKOFF",
        fixture_rows=rows,
        ledger_fingerprint="ledger",
        capture_projection_version="v1",
    )


def test_page_union_contains_every_fixture_once_for_500_rows() -> None:
    rows = _rows(500)
    entries = sort_entries(build_index_entries(rows, {}), "BOSS_PRIORITY_KICKOFF")
    snapshot = _snapshot(rows)
    seen: list[str] = []
    cursor = None
    while len(seen) < len(entries):
        page, _ = select_page(
            entries, snapshot_id=snapshot, sort="BOSS_PRIORITY_KICKOFF", page_size=20, cursor=cursor
        )
        seen.extend(item.fixture_id for item in page)
        cursor = encode_cursor(snapshot_id=snapshot, sort="BOSS_PRIORITY_KICKOFF", last=page[-1])
    assert len(seen) == 500
    assert len(set(seen)) == 500


def test_priority_sort_happens_before_pagination() -> None:
    rows = _rows(3)
    entries = build_index_entries(rows, {})
    entries[2] = replace(entries[2], priority=2, decision_tier="ANALYSIS_PICK")
    assert sort_entries(entries, "BOSS_PRIORITY_KICKOFF")[0].fixture_id == "2"


def test_window_counts_cover_all_entries() -> None:
    counts = window_counts(build_index_entries(_rows(53), {}))
    assert counts["total"] == 53
    assert counts["not_ready"] == 53


def test_cursor_stale_and_invalid_are_distinct() -> None:
    rows = _rows(2)
    entries = sort_entries(build_index_entries(rows, {}), "BOSS_PRIORITY_KICKOFF")
    cursor = encode_cursor(snapshot_id="old", sort="BOSS_PRIORITY_KICKOFF", last=entries[0])
    with pytest.raises(StaleDayViewCursor):
        select_page(
            entries, snapshot_id="new", sort="BOSS_PRIORITY_KICKOFF", page_size=1, cursor=cursor
        )
    with pytest.raises(InvalidDayViewCursor):
        decode_cursor("not-json")


def test_page_size_above_fifty_is_rejected() -> None:
    with pytest.raises(ValueError):
        select_page([], snapshot_id="x", sort="BOSS_PRIORITY_KICKOFF", page_size=51, cursor=None)
