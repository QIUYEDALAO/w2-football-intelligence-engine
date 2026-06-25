from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from archive.scripts.extract_w2_gate3_baselight_limited_ah import (
    build_odds_date_window_sql,
    combine_odds_with_matches,
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
                "status": "NO_DATA",
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

    assert next_date_window_end(state, "2026-06-24") == datetime(2026, 6, 20, tzinfo=UTC)


def test_processed_date_window_keys_include_completed_and_repeated_failed_windows() -> None:
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
                "window_start_utc": "2026-06-21T00:00:00Z",
                "window_end_utc": "2026-06-22T00:00:00Z",
                "status": "PENDING_OR_FAILED",
            },
            {
                "window_start_utc": "2026-06-20T00:00:00Z",
                "window_end_utc": "2026-06-21T00:00:00Z",
                "status": "NO_DATA",
            },
            {
                "window_start_utc": "2026-06-19T00:00:00Z",
                "window_end_utc": "2026-06-20T00:00:00Z",
                "status": "PENDING_OR_FAILED",
            },
            {"status": "IGNORED_MISSING_RANGE"},
        ]
    }

    assert processed_date_window_keys(state) == {
        ("2026-06-22T00:00:00Z", "2026-06-23T00:00:00Z"),
        ("2026-06-21T00:00:00Z", "2026-06-22T00:00:00Z"),
        ("2026-06-20T00:00:00Z", "2026-06-21T00:00:00Z"),
    }


def test_processed_date_window_keys_do_not_complete_http_rate_limit_failures() -> None:
    state = {
        "date_windows": [
            {
                "window_start_utc": "2026-06-21T00:00:00Z",
                "window_end_utc": "2026-06-22T00:00:00Z",
                "status": "PENDING_OR_FAILED",
                "reason": "MCP_HTTP_429:429",
            },
            {
                "window_start_utc": "2026-06-21T00:00:00Z",
                "window_end_utc": "2026-06-22T00:00:00Z",
                "status": "PENDING_OR_FAILED",
                "reason": "MCP_HTTP_429:429",
            },
            {
                "window_start_utc": "2026-06-20T00:00:00Z",
                "window_end_utc": "2026-06-21T00:00:00Z",
                "status": "RATE_LIMITED",
                "reason": "MCP_HTTP_429:429",
            },
        ]
    }

    assert processed_date_window_keys(state) == set()


def test_existing_jsonl_rows_are_not_removed_by_combination() -> None:
    existing = {
        (
            "existing-match",
            "Book",
            "Asian Handicap",
            "Home -0.5",
            "2026-06-01",
        )
    }
    odds_rows = [
        {
            "match_id": "new-match",
            "bookmaker": "Book",
            "market": "Asian Handicap",
            "outcome": "Home -0.5",
            "odds": 1.9,
            "odds_type": "pre_match",
            "collected_at": "2026-06-01",
        }
    ]
    match_rows = [
        {
            "match_id": "new-match",
            "competition": "League",
            "season": "2026",
            "kickoff_utc": "2026-06-02T00:00:00Z",
            "home_score": 1,
            "away_score": 0,
        }
    ]

    combined, fixtures = combine_odds_with_matches(odds_rows, match_rows, existing)

    assert len(combined) == 1
    assert fixtures == {"new-match"}
    assert (
        "existing-match",
        "Book",
        "Asian Handicap",
        "Home -0.5",
        "2026-06-01",
    ) in existing


def test_odds_date_window_sql_uses_bounded_window_without_slow_patterns() -> None:
    sql = build_odds_date_window_sql(
        datetime(2026, 6, 1, tzinfo=UTC),
        datetime(2026, 6, 2, tzinfo=UTC),
        5000,
    )

    assert "collected_at >=" in sql
    assert "collected_at <" in sql
    assert "JOIN" not in sql.upper()
    assert "regexp" not in sql.lower()
    assert "match_id IN" not in sql
    assert "ORDER BY" not in sql.upper()


def test_resume_extractor_source_does_not_use_match_id_odds_in_date_strategy() -> None:
    source = Path("archive/scripts/extract_w2_gate3_baselight_limited_ah.py").read_text()
    strategy = source.split("def run_odds_date_window_strategy", 1)[1].split(
        "def build_odds_sql",
        1,
    )[0]

    assert "build_odds_sql" not in strategy
    assert "build_odds_date_window_sql" in strategy
