from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from w2.markets.quote_identity import (
    QUOTE_IDENTITY_SCHEMA_VERSION,
    evaluate_quote_freshness,
)

NOW = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)


def _identity(*, captured_at: object, identity_status: str = "COMPLETE") -> dict[str, object]:
    return {
        "schema_version": QUOTE_IDENTITY_SCHEMA_VERSION,
        "market": "TOTALS",
        "identity_status": identity_status,
        "captured_at": captured_at,
        "quotes": {},
    }


def test_fresh_authoritative_quote_is_complete() -> None:
    result = evaluate_quote_freshness(
        _identity(captured_at=NOW - timedelta(minutes=29)),
        evaluated_at=NOW,
    )

    assert result["freshness_status"] == "COMPLETE"
    assert result["age_seconds"] == 29 * 60
    assert result["freshness_blockers"] == []


def test_quote_older_than_thirty_minutes_is_stale() -> None:
    result = evaluate_quote_freshness(
        _identity(captured_at=NOW - timedelta(minutes=30, microseconds=1)),
        evaluated_at=NOW,
    )

    assert result["freshness_status"] == "STALE"
    assert result["freshness_blockers"] == ["QUOTE_OLDER_THAN_30_MINUTES"]


@pytest.mark.parametrize(
    ("captured_at", "blocker"),
    [
        (None, "MISSING_AUTHORITATIVE_CAPTURED_AT"),
        ("not-a-time", "INVALID_AUTHORITATIVE_CAPTURED_AT"),
    ],
)
def test_missing_or_invalid_authoritative_time_is_incomplete(
    captured_at: object,
    blocker: str,
) -> None:
    result = evaluate_quote_freshness(
        _identity(captured_at=captured_at),
        evaluated_at=NOW,
    )

    assert result["freshness_status"] == "INCOMPLETE"
    assert blocker in result["freshness_blockers"]


def test_identity_conflict_is_incomplete_even_with_fresh_time() -> None:
    result = evaluate_quote_freshness(
        _identity(
            captured_at=NOW - timedelta(minutes=1),
            identity_status="CONFLICT",
        ),
        evaluated_at=NOW,
    )

    assert result["freshness_status"] == "INCOMPLETE"
    assert result["freshness_blockers"] == ["QUOTE_IDENTITY_NOT_COMPLETE"]


def test_legacy_ready_does_not_synthesize_new_identity() -> None:
    result = evaluate_quote_freshness(
        {
            "schema_version": "w2.quote_identity.legacy",
            "readiness_status": "READY",
            "captured_at": (NOW - timedelta(minutes=1)).isoformat(),
        },
        evaluated_at=NOW,
    )

    assert result["freshness_status"] == "INCOMPLETE"
    assert "identity_status" not in result
    assert result["freshness_blockers"] == [
        "QUOTE_IDENTITY_NOT_COMPLETE",
        "UNSUPPORTED_QUOTE_IDENTITY_SCHEMA",
    ]


def test_generated_at_is_not_used_as_quote_capture_time() -> None:
    result = evaluate_quote_freshness(
        {
            **_identity(captured_at=None),
            "generated_at": (NOW - timedelta(minutes=1)).isoformat(),
            "as_of": NOW.isoformat(),
        },
        evaluated_at=NOW,
    )

    assert result["freshness_status"] == "INCOMPLETE"
    assert result["age_seconds"] is None
    assert "MISSING_AUTHORITATIVE_CAPTURED_AT" in result["freshness_blockers"]
