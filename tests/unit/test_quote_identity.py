from __future__ import annotations

from typing import Any

from w2.markets.quote_identity import project_quote_identity


def quote(
    *,
    observation_id: str,
    market: str,
    selection: str,
    line: str,
    captured_at: str = "2026-07-18T01:00:00Z",
    bookmaker_id: str = "book-1",
) -> dict[str, Any]:
    return {
        "observation_id": observation_id,
        "fixture_id": "fixture-1",
        "provider": "api-football",
        "bookmaker_id": bookmaker_id,
        "bookmaker_name": "Book One" if bookmaker_id == "book-1" else "Book Two",
        "capture_id": "capture-1",
        "canonical_market": market,
        "selection": selection,
        "line": line,
        "decimal_odds": "1.91",
        "captured_at": captured_at,
        "raw_payload_sha256": "a" * 64,
        "source_revision": "future-refresh.v1",
    }


def test_complete_ah_quote_identity_uses_two_authoritative_observations() -> None:
    payload = project_quote_identity(
        market="ASIAN_HANDICAP",
        selected_line="-0.5",
        authoritative_rows={
            "home": quote(
                observation_id="home-id",
                market="ASIAN_HANDICAP",
                selection="Home -0.5",
                line="-0.5",
            ),
            "away": quote(
                observation_id="away-id",
                market="ASIAN_HANDICAP",
                selection="Away +0.5",
                line="0.5",
            ),
        },
    )

    assert payload["identity_status"] == "COMPLETE"
    assert payload["blockers"] == []
    assert payload["observation_ids"] == {"away": "away-id", "home": "home-id"}
    assert payload["bookmaker_id"] == "book-1"
    assert payload["capture_id"] == "capture-1"
    assert payload["captured_at"] == "2026-07-18T01:00:00Z"
    assert payload["source_revision"] == "future-refresh.v1"
    assert payload["raw_payload_sha256"] == "a" * 64
    assert payload["fixture_id"] == "fixture-1"
    assert payload["quote_identity_hash"]


def test_old_but_complete_quote_is_observed_without_freshness_policy() -> None:
    payload = project_quote_identity(
        market="TOTALS",
        selected_line="2.5",
        authoritative_rows={
            "over": quote(
                observation_id="over-id",
                market="TOTALS",
                selection="Over",
                line="2.5",
                captured_at="2026-07-01T01:00:00Z",
            ),
            "under": quote(
                observation_id="under-id",
                market="TOTALS",
                selection="Under",
                line="2.5",
                captured_at="2026-07-01T01:00:00Z",
            ),
        },
    )

    assert payload["identity_status"] == "COMPLETE"
    assert "freshness_status" not in payload


def test_capture_or_bookmaker_mismatch_is_conflict() -> None:
    payload = project_quote_identity(
        market="TOTALS",
        selected_line="2.5",
        authoritative_rows={
            "over": quote(
                observation_id="over-id",
                market="TOTALS",
                selection="Over",
                line="2.5",
            ),
            "under": quote(
                observation_id="under-id",
                market="TOTALS",
                selection="Under",
                line="2.5",
                captured_at="2026-07-18T01:01:00Z",
                bookmaker_id="book-2",
            ),
        },
    )

    assert payload["identity_status"] == "CONFLICT"
    assert payload["blockers"] == ["BOOKMAKER_MISMATCH", "CAPTURE_TIME_MISMATCH"]


def test_missing_authoritative_fields_is_incomplete_not_synthesized() -> None:
    payload = project_quote_identity(
        market="ASIAN_HANDICAP",
        selected_line="0.5",
        authoritative_rows={
            "home": {"fixture_id": "fixture-1", "selection": "Home -0.5", "line": "-0.5"},
            "away": {"fixture_id": "fixture-1", "selection": "Away +0.5", "line": "0.5"},
        },
    )

    assert payload["identity_status"] == "INCOMPLETE"
    assert "HOME_MISSING_OBSERVATION_ID" in payload["blockers"]
    assert "AWAY_MISSING_CAPTURED_AT" in payload["blockers"]
    assert payload["observation_ids"] == {}


def test_ah_selected_line_must_equal_home_quote_line_not_only_magnitude() -> None:
    payload = project_quote_identity(
        market="ASIAN_HANDICAP",
        selected_line="0.75",
        authoritative_rows={
            "home": quote(
                observation_id="home-id",
                market="ASIAN_HANDICAP",
                selection="Home -0.75",
                line="-0.75",
            ),
            "away": quote(
                observation_id="away-id",
                market="ASIAN_HANDICAP",
                selection="Away +0.75",
                line="0.75",
            ),
        },
    )

    assert payload["identity_status"] == "CONFLICT"
    assert payload["blockers"] == ["LINE_MISMATCH"]
