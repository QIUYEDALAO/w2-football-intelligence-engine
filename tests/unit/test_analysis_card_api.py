from __future__ import annotations

from typing import Any, cast

from w2.api import repository as api_repository
from w2.api.repository import ReadModelRepository, ReadModelService


class FakeRepository:
    def __init__(self, *, dashboard: dict[str, Any] | None = None) -> None:
        self.dashboard = dashboard

    def matchday_cards(self) -> list[dict[str, Any]]:
        return []

    def dashboard_fixture(self, fixture_id: str) -> dict[str, Any] | None:
        if self.dashboard is None:
            return None
        return self.dashboard if self.dashboard.get("fixture_id") == fixture_id else None

    def fixture_payloads(self) -> list[dict[str, Any]]:
        return []

    def future_market_observations(self) -> list[dict[str, Any]]:
        return []


def test_analysis_card_fallback_contains_four_markets_and_intent() -> None:
    repository = FakeRepository(
        dashboard={
            "fixture_id": "1489404",
            "market_coverage": {"ASIAN_HANDICAP": True, "TOTALS": False},
        }
    )
    service = ReadModelService(
        repository=cast(Any, repository),
    )

    card = service.analysis_card("1489404")

    assert card is not None
    assert card["decision"] == "SKIP"
    assert {market["market"] for market in card["markets"]} == {
        "ASIAN_HANDICAP",
        "TOTALS",
        "FIRST_HALF_GOALS",
        "SCORE",
    }
    assert card["bookmaker_intent"]["intent"] == "INSUFFICIENT_DATA"
    assert card["bookmaker_intent"]["label_cn"] == "数据不足"
    assert card["disclaimer"] == "分析参考·非稳赢"
    assert card["disclaimer_cn"] == "分析参考·非稳赢"
    assert card["watch_level"] == 0
    assert card["competition_cn"] == "世界杯"
    assert card["competition_name"] == "世界杯"
    assert card["home_cn"] == "主队"
    assert card["away_cn"] == "客队"
    assert card["home_name"] == "主队"
    assert card["away_name"] == "客队"
    assert card["data_readiness"] == {
        "bookmakers": 0,
        "odds_snapshots": 0,
        "xg": False,
        "h2h": False,
        "lineups": False,
    }
    assert card["candidate"] is False
    assert card["formal_recommendation"] is False
    assert all(market["decision"] == "SKIP" for market in card["markets"])
    assert all(market["label_cn"] for market in card["markets"])
    assert all("reason_cn" in market for market in card["markets"])
    assert all("reason" in market for market in card["markets"])


def test_embedded_analysis_card_is_normalized_to_false_flags() -> None:
    repository = FakeRepository(
        dashboard={
            "fixture_id": "1489404",
            "analysis_card": {
                "decision": "ANALYSIS_PICK",
                "candidate": True,
                "formal_recommendation": True,
                "markets": [
                    {
                        "market": "TOTALS",
                        "decision": "ANALYSIS_PICK",
                        "tendency": "OVER",
                        "confidence": 0.55,
                        "reasons": ["大小球意图: OVER_LEAN"],
                        "risks": ["阵容变化"],
                        "invalidation_conditions": ["盘口跳线"],
                        "candidate": True,
                        "formal_recommendation": True,
                    }
                ],
            },
        }
    )
    service = ReadModelService(
        repository=cast(Any, repository),
    )

    card = service.analysis_card("1489404")

    assert card is not None
    assert card["candidate"] is False
    assert card["formal_recommendation"] is False
    assert card["markets"][0]["candidate"] is False
    assert card["markets"][0]["formal_recommendation"] is False
    assert card["markets"][0]["decision"] == "PICK"
    assert card["markets"][0]["analysis_decision"] == "ANALYSIS_PICK"
    assert card["markets"][0]["label_cn"] == "大小球"
    assert card["markets"][0]["lean"] == "大球"
    assert card["markets"][0]["reason"] == "大小球意图: OVER_LEAN"


def test_fixture_detail_includes_analysis_card() -> None:
    repository = FakeRepository(
        dashboard={
            "fixture_id": "1489404",
            "competition_id": "world_cup_2026",
            "competition_name": "World Cup",
            "kickoff_utc": "2026-06-25T18:00:00Z",
            "status": "NS",
            "home_team_id": "10",
            "away_team_id": "20",
            "home_team_name": "Home",
            "away_team_name": "Away",
            "market_coverage": {},
        }
    )
    service = ReadModelService(
        repository=cast(Any, repository),
    )

    detail = service.fixture("1489404", "UTC")

    assert detail is not None
    assert detail["analysis_card"]["fixture_id"] == "1489404"
    assert len(detail["analysis_card"]["markets"]) == 4


class MixedFixtureRepository:
    def matchday_cards(self) -> list[dict[str, Any]]:
        return []

    def dashboard_fixture(self, fixture_id: str) -> dict[str, Any] | None:
        if fixture_id == "dashboard-only":
            return {"fixture_id": "dashboard-only", "market_coverage": {}}
        return None

    def fixture_payloads(self) -> list[dict[str, Any]]:
        return [
            {
                "fixture": {
                    "id": "db-world-cup-fixture",
                    "date": "2026-06-26T18:00:00Z",
                    "status": {"short": "NS"},
                    "venue": {"name": "World Cup Venue"},
                },
                "league": {"id": "1", "name": "World Cup", "round": "Group Stage - 3"},
                "teams": {
                    "home": {"id": "10", "name": "Home"},
                    "away": {"id": "20", "name": "Away"},
                },
            }
        ]

    def future_market_observations(self) -> list[dict[str, Any]]:
        return [
            {
                "fixture_id": "db-world-cup-fixture",
                "canonical_market": "ASIAN_HANDICAP",
            },
            {
                "fixture_id": "db-world-cup-fixture",
                "canonical_market": "TOTALS",
            },
        ]


def test_analysis_card_falls_back_for_db_fixture_when_dashboard_exists() -> None:
    service = ReadModelService(repository=cast(Any, MixedFixtureRepository()))

    card = service.analysis_card("db-world-cup-fixture")

    assert card is not None
    assert card["fixture_id"] == "db-world-cup-fixture"
    assert card["source"] == "future_refresh_without_analysis_payload"
    assert card["candidate"] is False
    assert card["formal_recommendation"] is False
    assert card["competition_cn"] == "World Cup · Group Stage - 3"
    assert card["competition_name"] == "World Cup"
    assert card["home_cn"] == "Home"
    assert card["away_cn"] == "Away"
    assert card["home_name"] == "Home"
    assert card["away_name"] == "Away"
    assert {market["market"] for market in card["markets"]} == {
        "ASIAN_HANDICAP",
        "TOTALS",
        "FIRST_HALF_GOALS",
        "SCORE",
    }
    assert card["markets"][0]["reasons"] == ["AH_ANALYSIS_INPUT_UNAVAILABLE"]
    assert card["markets"][1]["reasons"] == ["OU_ANALYSIS_INPUT_UNAVAILABLE"]


def test_fixture_list_includes_team_names_for_loading_cards() -> None:
    service = ReadModelService(repository=cast(Any, MixedFixtureRepository()))

    rows, total = service.fixtures(timezone="UTC", page=1, page_size=10)

    assert total == 1
    assert rows[0]["fixture_id"] == "db-world-cup-fixture"
    assert rows[0]["home_team_name"] == "Home"
    assert rows[0]["away_team_name"] == "Away"


def test_read_model_repository_merges_dashboard_and_db_fixtures(monkeypatch) -> None:
    class DbRepository:
        def fixture_payloads(self) -> list[dict[str, Any]]:
            return [
                {
                    "fixture": {
                        "id": "db-world-cup-fixture",
                        "date": "2026-06-26T18:00:00Z",
                    }
                }
            ]

    repository = ReadModelRepository()
    monkeypatch.setattr(
        repository,
        "dashboard_latest_fixtures",
        lambda: [
            {
                "fixture_id": "dashboard-only",
                "kickoff_utc": "2026-06-22T17:00:00Z",
                "status": "NS",
                "competition_id": "1",
                "competition_name": "World Cup",
                "home_team_id": "10",
                "away_team_id": "20",
                "home_team_name": "Home",
                "away_team_name": "Away",
            }
        ],
    )
    monkeypatch.setattr(api_repository, "future_refresh_db_repository", lambda: DbRepository())

    fixtures = repository.fixture_payloads()

    assert {str(item["fixture"]["id"]) for item in fixtures} == {
        "dashboard-only",
        "db-world-cup-fixture",
    }
