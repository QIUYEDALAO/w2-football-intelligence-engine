from __future__ import annotations

from datetime import UTC, datetime, timedelta
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


def test_world_cup_neutral_site_policy_keeps_host_home_advantage_only() -> None:
    host_home = {
        "league": {"id": "1", "season": "2026", "name": "World Cup"},
        "teams": {
            "home": {"id": "10", "name": "United States"},
            "away": {"id": "20", "name": "France"},
        },
    }
    non_host_home = {
        "league": {"id": "1", "season": "2026", "name": "World Cup"},
        "teams": {
            "home": {"id": "10", "name": "France"},
            "away": {"id": "20", "name": "Sweden"},
        },
    }
    host_away = {
        "league": {"id": "1", "season": "2026", "name": "World Cup"},
        "teams": {
            "home": {"id": "10", "name": "France"},
            "away": {"id": "20", "name": "USA"},
        },
    }

    assert api_repository._fixture_neutral_site(host_home) is False
    assert api_repository._fixture_neutral_site(non_host_home) is True
    assert api_repository._fixture_neutral_site(host_away) is True


class ExistingFeatureRepository(FakeRepository):
    def fixture_payloads(self) -> list[dict[str, Any]]:
        return [
            {
                "fixture": {
                    "id": "1489404",
                    "date": "2026-06-26T18:00:00Z",
                    "status": {"short": "NS"},
                },
                "league": {"id": "world_cup_2026", "name": "World Cup"},
                "teams": {
                    "home": {"id": "10", "name": "Home"},
                    "away": {"id": "20", "name": "Away"},
                },
            }
        ]

    def future_market_observations(self) -> list[dict[str, Any]]:
        captured = "2026-06-26T12:00:00Z"
        return [
            {
                "fixture_id": "1489404",
                "canonical_market": "ASIAN_HANDICAP",
                "selection": "Home",
                "line": "-0.5",
                "decimal_odds": "1.91",
                "captured_at": captured,
                "provider_last_update": captured,
                "bookmaker_id": "bm1",
                "bookmaker_name": "Book",
                "suspended": False,
                "live": False,
            },
            {
                "fixture_id": "1489404",
                "canonical_market": "ASIAN_HANDICAP",
                "selection": "Away",
                "line": "0.5",
                "decimal_odds": "1.91",
                "captured_at": captured,
                "provider_last_update": captured,
                "bookmaker_id": "bm1",
                "bookmaker_name": "Book",
                "suspended": False,
                "live": False,
            },
            {
                "fixture_id": "1489404",
                "canonical_market": "TOTALS",
                "selection": "Over",
                "line": "2.5",
                "decimal_odds": "1.92",
                "captured_at": captured,
                "provider_last_update": captured,
                "bookmaker_id": "bm1",
                "bookmaker_name": "Book",
                "suspended": False,
                "live": False,
            },
            {
                "fixture_id": "1489404",
                "canonical_market": "TOTALS",
                "selection": "Under",
                "line": "2.5",
                "decimal_odds": "1.92",
                "captured_at": captured,
                "provider_last_update": captured,
                "bookmaker_id": "bm1",
                "bookmaker_name": "Book",
                "suspended": False,
                "live": False,
            },
        ]


class ExistingFeatureStore:
    def team_xg_rolling_snapshots(self, *, fixture_id: str | None = None) -> list[dict[str, Any]]:
        assert fixture_id == "1489404"
        return [
            {
                "team_id": "10",
                "as_of_time": "2026-06-26T12:00:00Z",
                "rolling_xg_for": 1.7,
                "rolling_xg_against": 0.8,
                "rolling_goals_for": 2.0,
                "rolling_goals_against": 1.0,
            },
            {
                "team_id": "20",
                "as_of_time": "2026-06-26T12:00:00Z",
                "rolling_xg_for": 0.8,
                "rolling_xg_against": 1.4,
                "rolling_goals_for": 1.0,
                "rolling_goals_against": 2.0,
            },
        ]

    def team_xg_matches(self) -> list[dict[str, Any]]:
        return [
            {
                "team_id": "10",
                "opponent_team_id": "30",
                "kickoff_at": "2026-06-21T18:00:00Z",
                "goals_for": 2,
                "goals_against": 1,
            },
            {
                "team_id": "20",
                "opponent_team_id": "40",
                "kickoff_at": "2026-06-23T18:00:00Z",
                "goals_for": 0,
                "goals_against": 1,
            },
        ]

    def raw_payloads(self, endpoint: str) -> list[dict[str, Any]]:
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
        "market_observations": 0,
        "bookmakers": 0,
        "odds_snapshots": 0,
        "xg": False,
        "xg_status": "UNKNOWN",
        "xg_home_match_count": 0,
        "xg_away_match_count": 0,
        "xg_snapshot_count": 0,
        "h2h": False,
        "lineups": False,
        "lineups_status": "UNKNOWN",
        "lineups_captured_at": None,
        "statistics_status": "UNKNOWN",
        "statistics_captured_at": None,
    }
    assert card["candidate"] is False
    assert card["formal_recommendation"] is False
    assert all(market["decision"] == "SKIP" for market in card["markets"])
    assert all(market["label_cn"] for market in card["markets"])
    assert all("reason_cn" in market for market in card["markets"])
    assert all("reason" in market for market in card["markets"])


def test_existing_xg_history_is_wired_into_feature_inputs_without_faking_market_factors(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(
        api_repository,
        "future_refresh_db_repository",
        lambda: ExistingFeatureStore(),
    )
    service = ReadModelService(repository=cast(Any, ExistingFeatureRepository()))

    card = service.analysis_card("1489404")

    assert card is not None
    factors = {item["id"]: item for item in card["pricing_shadow"]["factors"]}
    assert {"F3_REST_FITNESS", "F4_MATCH_IMPORTANCE", "F7_STRENGTH_FORM", "F9_TRUE_XG"}.issubset(
        factors
    )
    assert factors["F3_REST_FITNESS"]["status"] == "READY"
    assert factors["F7_STRENGTH_FORM"]["status"] == "READY"
    assert factors["F3_REST_FITNESS"]["source_group"] == "xg"
    assert factors["F3_REST_FITNESS"]["proxy_of"] == "team_fixture_history"
    assert factors["F3_REST_FITNESS"]["is_independent_signal"] is False
    assert factors["F7_STRENGTH_FORM"]["source_group"] == "xg"
    assert factors["F7_STRENGTH_FORM"]["proxy_of"] == "ratings"
    assert factors["F7_STRENGTH_FORM"]["is_independent_signal"] is False
    assert factors["F9_TRUE_XG"]["source_group"] == "xg"
    assert card["pricing_shadow"]["independent_signal_count"] == 1
    assert card["pricing_shadow"]["xg_derived_factor_count"] == 3
    assert "F5_RECENT_AH_COVER" not in factors
    assert card["pricing_shadow"]["coverage"] > 0.29
    assert card["pricing_shadow"]["beats_market"] is False
    assert card["pricing_shadow"]["formal_enabled"] is False
    assert card["pricing_shadow"]["candidate_enabled"] is False


def test_embedded_analysis_card_is_normalized_to_false_flags() -> None:
    repository = FakeRepository(
        dashboard={
            "fixture_id": "1489404",
            "analysis_card": {
                "decision": "ANALYSIS_PICK",
                "candidate": True,
                "formal_recommendation": True,
                "pricing_shadow": {
                    "status": "CALIBRATED",
                    "beats_market": True,
                },
                "model_probabilities": {"HOME": 0.42, "DRAW": 0.30, "AWAY": 0.28},
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
    assert card["pricing_shadow"]["status"] == "INSUFFICIENT_INDEPENDENT_FACTORS"
    assert card["pricing_shadow"]["beats_market"] is False
    assert card["pricing_shadow"]["fair_ah"] is None
    assert card["pricing_shadow"]["edge_ah"] is None
    assert card["pricing_shadow"]["coverage"] == 0
    assert card["pricing_shadow"]["factors"] == []
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
    assert detail["analysis_card"]["reason_code"] == "FROZEN_ANALYSIS_CAPTURE_UNAVAILABLE"


class MixedFixtureRepository:
    def matchday_cards(self) -> list[dict[str, Any]]:
        return []

    def dashboard_fixture(self, fixture_id: str) -> dict[str, Any] | None:
        if fixture_id == "dashboard-only":
            return {"fixture_id": "dashboard-only", "market_coverage": {}}
        return None

    def fixture_payloads(self) -> list[dict[str, Any]]:
        kickoff = (datetime.now(UTC) + timedelta(days=1)).isoformat().replace("+00:00", "Z")
        return [
            {
                "fixture": {
                    "id": "db-world-cup-fixture",
                    "date": kickoff,
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
    assert card["source"] == "db_feature_materialized_analysis"
    assert card["decision"] == "SKIP"
    assert card["candidate"] is False
    assert card["formal_recommendation"] is False
    assert card["feature_readiness"]["xg_status"] == "PROVIDER_EMPTY_OR_UNAVAILABLE"
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
    assert card["markets"][0]["reasons"] == ["无有效主盘"]
    assert card["markets"][1]["reasons"] == ["无有效主盘"]


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
