from __future__ import annotations

from datetime import UTC, datetime

from scripts.extract_w2_gate3_baselight_limited_ah import (
    next_date_window_end,
    processed_date_window_keys,
)


def test_odds_date_window_resume_uses_earliest_processed_start() -> None:
    state = {
        "date_windows": [
            {
                "window_start_utc": "2026-06-22T00:00:00Z",
                "window_end_utc": "2026-06-23T00:00:00Z",
                "status": "APPENDED",
            },
            {
                "window_start_utc": "2026-06-21T00:00:00Z",
                "window_end_utc": "2026-06-22T00:00:00Z",
                "status": "PENDING_OR_FAILED",
            },
            {
                "window_start_utc": "2026-06-20T00:00:00Z",
                "window_end_utc": "2026-06-21T00:00:00Z",
                "status": "APPENDED",
            },
            {
                "window_start_utc": "2026-06-19T00:00:00Z",
                "window_end_utc": "2026-06-20T00:00:00Z",
                "status": "STARTED",
            },
        ]
    }

    assert next_date_window_end(state, "2026-06-24") == datetime(2026, 6, 19, tzinfo=UTC)


def test_processed_date_window_keys_include_completed_and_failed_windows() -> None:
    state = {
        "date_windows": [
            {
                "window_start_utc": "2026-06-22T00:00:00Z",
                "window_end_utc": "2026-06-23T00:00:00Z",
                "status": "APPENDED",
            },
            {
                "window_start_utc": "2026-06-21T00:00:00Z",
                "window_end_utc": "2026-06-22T00:00:00Z",
                "status": "PENDING_OR_FAILED",
            },
            {"status": "IGNORED_MISSING_RANGE"},
        ]
    }

    assert processed_date_window_keys(state) == {
        ("2026-06-22T00:00:00Z", "2026-06-23T00:00:00Z"),
        ("2026-06-21T00:00:00Z", "2026-06-22T00:00:00Z"),
    }

