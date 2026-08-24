from __future__ import annotations

from datetime import UTC, datetime

from w2.prematch.expected_match_denominator import (
    classify_expected_match_rows,
    materialize_saved_fixture_observations,
)

NOW = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)


def _fixture(fixture_id: int, *, status: str = "FT") -> dict[str, object]:
    return {
        "fixture": {
            "id": fixture_id,
            "date": "2026-08-20T12:00:00Z",
            "status": {"short": status},
        },
        "league": {"id": 39, "season": 2026},
        "teams": {"home": {"id": 10}, "away": {"id": 20}},
        "goals": {"home": 2 if status == "FT" else None, "away": 1 if status == "FT" else None},
    }


def test_saved_raw_projection_uses_canonical_provider_fixture_identity() -> None:
    rows, rejected = materialize_saved_fixture_observations(
        raw_payload_sha256="a" * 64,
        raw_captured_at=NOW,
        raw_inserted_at=NOW,
        payload={"response": [_fixture(1234)]},
        materialized_at=NOW,
    )

    assert rejected == []
    assert len(rows) == 1
    assert rows[0]["provider_fixture_id"] == "1234"
    assert rows[0]["canonical_fixture_id"] == "api_football:1234"
    assert rows[0]["home_provider_team_id"] == "10"
    assert rows[0]["away_provider_team_id"] == "20"


def test_conflicting_duplicate_provider_fixture_identity_is_rejected() -> None:
    first = _fixture(1234)
    conflicting = _fixture(1234)
    conflicting["teams"] = {"home": {"id": 30}, "away": {"id": 40}}

    rows, rejected = materialize_saved_fixture_observations(
        raw_payload_sha256="a" * 64,
        raw_captured_at=NOW,
        raw_inserted_at=NOW,
        payload={"response": [first, conflicting]},
        materialized_at=NOW,
    )

    assert len(rows) == 1
    assert rejected == [
        {
            "reason": "CANONICAL_PROVIDER_FIXTURE_IDENTITY_CONFLICT",
            "sample": "1234",
        }
    ]


def test_unfinished_expected_match_is_fail_closed() -> None:
    rows = [
        {
            "canonical_fixture_id": f"api_football:{fixture_id}",
            "fixture_status": status,
            "home_goals": home,
            "away_goals": away,
        }
        for fixture_id, status, home, away in (
            (4, "NS", None, None),
            (3, "FT", 1, 0),
            (2, "FT", 2, 0),
            (1, "FT", 1, 1),
        )
    ]

    result = classify_expected_match_rows(rows, team_id="10")

    assert result["status"] == "UNAVAILABLE_FAIL_CLOSED"
    assert result["reason"] == "EXPECTED_MATCH_RESULT_NOT_VISIBLE_AT_AS_OF"
    assert result["high_confidence_allowed"] is False


def test_cancelled_fixture_is_not_a_missing_played_match() -> None:
    rows = [
        {
            "canonical_fixture_id": f"api_football:{fixture_id}",
            "fixture_status": status,
            "home_goals": home,
            "away_goals": away,
        }
        for fixture_id, status, home, away in (
            (4, "CANC", None, None),
            (3, "FT", 1, 0),
            (2, "FT", 2, 0),
            (1, "FT", 1, 1),
        )
    ]

    result = classify_expected_match_rows(rows, team_id="10")

    assert result["status"] == "AVAILABLE"
    assert result["expected_match_count"] == 3
