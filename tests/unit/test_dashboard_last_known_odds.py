from __future__ import annotations

from typing import Any, cast

from w2.prematch.analysis_calculator import ReadModelService


def _totals_rows(fixture_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for bookmaker_id, over_price, under_price in (
        ("10", "1.91", "1.93"),
        ("20", "1.89", "1.95"),
    ):
        for selection, price in (("Over", over_price), ("Under", under_price)):
            rows.append(
                {
                    "observation_id": f"{fixture_id}-{bookmaker_id}-{selection}",
                    "fixture_id": fixture_id,
                    "canonical_market": "TOTALS",
                    "selection": selection,
                    "line": "2.75",
                    "decimal_odds": price,
                    "bookmaker_id": bookmaker_id,
                    "bookmaker_name": f"Book {bookmaker_id}",
                    "captured_at": "2026-07-17T14:48:45Z",
                    "suspended": False,
                    "live": False,
                }
            )
    return rows


class ScopedOddsRepository:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def future_market_observations_for_fixtures(
        self,
        fixture_ids: list[str],
    ) -> list[dict[str, Any]]:
        self.calls.append(list(fixture_ids))
        return [row for fixture_id in fixture_ids for row in _totals_rows(fixture_id)]


def test_dashboard_attaches_reference_only_odds_in_one_scoped_read() -> None:
    repository = ScopedOddsRepository()
    service = ReadModelService(repository=cast(Any, repository))
    cards = [{"fixture_id": "fixture-1"}, {"fixture_id": "fixture-2"}]

    service._attach_last_known_odds(cards)

    assert repository.calls == [["fixture-1", "fixture-2"]]
    for card in cards:
        snapshot = card["last_known_odds"]
        assert snapshot["status"] == "REFERENCE_ONLY"
        assert snapshot["executable"] is False
        assert snapshot["captured_at"] == "2026-07-17T14:48:45Z"
        assert snapshot["observation_count"] == 4
        assert snapshot["bookmaker_count"] == 2
        assert snapshot["markets"]["ou"]["line"] == "2.75"
        assert snapshot["markets"]["ou"]["over_price"] == 1.91
        assert snapshot["markets"]["ou"]["under_price"] == 1.93
        assert "candidate_lines" not in snapshot["markets"]["ou"]
        assert "rejected_lines" not in snapshot["markets"]["ou"]
        assert "selection_policy" not in snapshot["markets"]["ou"]


def test_dashboard_reference_odds_fail_closed_on_cross_fixture_rows() -> None:
    class CrossFixtureRepository(ScopedOddsRepository):
        def future_market_observations_for_fixtures(
            self,
            fixture_ids: list[str],
        ) -> list[dict[str, Any]]:
            return _totals_rows("not-requested")

    service = ReadModelService(repository=cast(Any, CrossFixtureRepository()))
    cards = [{"fixture_id": "fixture-1"}]

    service._attach_last_known_odds(cards)

    assert "last_known_odds" not in cards[0]


def test_complete_quote_audit_projects_reference_only_odds_with_source_time() -> None:
    card = {
        "quote_identity_audit": {
            "ah": {
                "identity_status": "COMPLETE",
                "freshness_status": "COMPLETE",
                "bookmaker_id": "32",
                "captured_at": "2026-08-02T16:03:15Z",
                "quotes": {
                    "home": {
                        "line": "-0.25",
                        "decimal_odds": "2.02",
                        "bookmaker_name": "Betano",
                    },
                    "away": {
                        "line": "0.25",
                        "decimal_odds": "1.83",
                        "bookmaker_name": "Betano",
                    },
                },
            }
        }
    }

    snapshot = ReadModelService._reference_odds_from_quote_audit(card)

    assert snapshot == {
        "status": "REFERENCE_ONLY",
        "executable": False,
        "captured_at": "2026-08-02T16:03:15Z",
        "bookmakers": ["Betano"],
        "markets": {
            "ah": {
                "line": "-0.25",
                "home_line": "-0.25",
                "away_line": "0.25",
                "home_price": "2.02",
                "away_price": "1.83",
                "bookmaker_id": "32",
                "bookmaker_name": "Betano",
                "captured_at": "2026-08-02T16:03:15Z",
                "freshness_status": "COMPLETE",
            }
        },
    }
