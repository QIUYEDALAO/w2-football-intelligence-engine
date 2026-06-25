from __future__ import annotations

from typing import Any, cast

from w2.api.repository import ReadModelService


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
    assert card["disclaimer"] == "分析参考·非稳赢"
    assert card["candidate"] is False
    assert card["formal_recommendation"] is False
    assert all(market["decision"] == "SKIP" for market in card["markets"])


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
