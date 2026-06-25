from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast

from w2.api import repository as api_repository
from w2.api.repository import ReadModelService

NOW = datetime(2026, 6, 25, 12, 0, tzinfo=UTC)
KICKOFF = NOW + timedelta(days=1)


class FakeReadRepository:
    def matchday_cards(self) -> list[dict[str, Any]]:
        return []

    def dashboard_fixture(self, fixture_id: str) -> dict[str, Any] | None:
        return None

    def fixture_payloads(self) -> list[dict[str, Any]]:
        return [
            {
                "fixture": {
                    "id": "1489410",
                    "date": KICKOFF.isoformat().replace("+00:00", "Z"),
                    "status": {"short": "NS"},
                },
                "league": {"id": 1, "name": "World Cup", "round": "Group Stage - 3"},
                "teams": {
                    "home": {"id": 10, "name": "Home"},
                    "away": {"id": 20, "name": "Away"},
                },
            }
        ]

    def future_market_observations(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for index, captured in enumerate((NOW - timedelta(hours=3), NOW - timedelta(hours=1))):
            for bookmaker_id, bookmaker_name, price in (
                ("1", "Pinnacle", "1.95"),
                ("2", "SoftBook", "2.04"),
            ):
                rows.append(
                    {
                        "fixture_id": "1489410",
                        "canonical_market": "ASIAN_HANDICAP",
                        "selection": "Home",
                        "line": "-0.75",
                        "decimal_odds": price if index == 0 else "1.80",
                        "bookmaker_id": bookmaker_id,
                        "bookmaker_name": bookmaker_name,
                        "provider_last_update": captured.isoformat().replace("+00:00", "Z"),
                        "captured_at": captured.isoformat().replace("+00:00", "Z"),
                        "suspended": False,
                        "live": False,
                    }
                )
                rows.append(
                    {
                        "fixture_id": "1489410",
                        "canonical_market": "TOTALS",
                        "selection": "Over",
                        "line": "2.5",
                        "decimal_odds": "1.90" if index == 0 else "1.72",
                        "bookmaker_id": bookmaker_id,
                        "bookmaker_name": bookmaker_name,
                        "provider_last_update": captured.isoformat().replace("+00:00", "Z"),
                        "captured_at": captured.isoformat().replace("+00:00", "Z"),
                        "suspended": False,
                        "live": False,
                    }
                )
        return rows


class FakeDbRepository:
    def team_xg_rolling_snapshots(
        self,
        *,
        fixture_id: str | None = None,
        team_id: str | None = None,
    ) -> list[dict[str, Any]]:
        assert fixture_id == "1489410"
        return [
            {
                "snapshot_id": "10:1489410",
                "team_id": "10",
                "as_of_fixture_id": "1489410",
                "as_of_time": (KICKOFF - timedelta(minutes=1)).isoformat(),
                "match_count": 5,
                "rolling_xg_for": 1.8,
                "rolling_xg_against": 0.7,
                "rolling_goals_for": 2.0,
                "rolling_goals_against": 0.8,
                "regression_index": 0.3,
            },
            {
                "snapshot_id": "20:1489410",
                "team_id": "20",
                "as_of_fixture_id": "1489410",
                "as_of_time": (KICKOFF - timedelta(minutes=1)).isoformat(),
                "match_count": 5,
                "rolling_xg_for": 0.9,
                "rolling_xg_against": 1.5,
                "rolling_goals_for": 0.8,
                "rolling_goals_against": 1.8,
                "regression_index": -0.2,
            },
        ]


def test_analysis_card_uses_materialized_xg_and_market_snapshots(monkeypatch) -> None:
    monkeypatch.setattr(api_repository, "future_refresh_db_repository", lambda: FakeDbRepository())
    service = ReadModelService(repository=cast(Any, FakeReadRepository()))

    card = service.analysis_card("1489410")

    assert card is not None
    assert card["decision"] == "ANALYSIS_PICK"
    assert card["candidate"] is False
    assert card["formal_recommendation"] is False
    decisions = {market["market"]: market["decision"] for market in card["markets"]}
    assert decisions["ASIAN_HANDICAP"] == "PICK"
    assert decisions["TOTALS"] == "PICK"
    assert decisions["FIRST_HALF_GOALS"] == "PICK"
    assert decisions["SCORE"] == "PICK"
    assert any(
        "F9_TRUE_XG:AS_OF_ROLLING_XG_DIFF" in reason
        for reason in card["markets"][0]["reasons"]
    )
    assert card["bookmaker_intent"]["intent"] in {"HOME_LEAN", "AWAY_LEAN"}
