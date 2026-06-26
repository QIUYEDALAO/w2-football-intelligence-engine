from __future__ import annotations

from typing import Any, cast

from w2.api.repository import ReadModelService


class RecommendationLoopRepository:
    def release_counts(self) -> dict[str, int]:
        return {
            "read_model_fixture_count": 1,
            "matchday_card_count": 1,
            "future_fixture_count": 0,
            "result_event_count": 0,
        }

    def staging_seed_dashboard(self) -> dict[str, Any] | None:
        return None

    def dashboard_latest_fixtures(self) -> list[dict[str, Any]]:
        return []

    def fixture_payloads(self) -> list[dict[str, Any]]:
        return []

    def result_events(self) -> list[dict[str, Any]]:
        return []

    def future_market_observations(self) -> list[dict[str, Any]]:
        return []

    def dashboard_fixture(self, fixture_id: str) -> dict[str, Any] | None:
        return None

    def matchday_cards(self) -> list[dict[str, Any]]:
        return [
            {
                "fixture": {
                    "fixture_id": "finished-over",
                    "competition_id": "1",
                    "competition_name": "World Cup",
                    "kickoff_utc": "2026-06-26T10:00:00Z",
                    "status": "FT",
                    "home_team_id": "10",
                    "home_team_name": "Home",
                    "away_team_id": "20",
                    "away_team_name": "Away",
                    "home_goals": 2,
                    "away_goals": 1,
                },
                "card": {"action": "DATA"},
                "temporal": {},
                "analysis_card": {
                    "decision": "ANALYSIS_PICK",
                    "candidate": False,
                    "formal_recommendation": False,
                    "markets": [
                        {
                            "market": "TOTALS",
                            "decision": "ANALYSIS_PICK",
                            "tendency": "OVER",
                            "line": "2.5",
                            "odds": "1.90",
                            "confidence": 0.72,
                            "reasons": ["盘口变化支持大球"],
                            "risks": ["临场阵容变化"],
                        },
                        {
                            "market": "SCORE",
                            "decision": "ANALYSIS_PICK",
                            "tendency": "HOME",
                            "confidence": 0.6,
                            "score_card": {
                                "scenarios": [
                                    {
                                        "scoreline": "2-1",
                                        "conditional_probability": 0.22,
                                    },
                                    {
                                        "scoreline": "1-1",
                                        "conditional_probability": 0.18,
                                    },
                                    {
                                        "scoreline": "2-0",
                                        "conditional_probability": 0.13,
                                    },
                                    {
                                        "scoreline": "3-1",
                                        "conditional_probability": 0.09,
                                    },
                                ]
                            },
                        },
                    ],
                },
            }
        ]


def test_dashboard_validates_analysis_pick_without_promoting_to_candidate() -> None:
    service = ReadModelService(repository=cast(Any, RecommendationLoopRepository()))

    payload = service.dashboard(target_date="2026-06-26", window="today")

    assert len(payload["all"]) == 1
    card = payload["all"][0]
    assert card["status"] == "FINISHED"
    assert card["candidate"] is False
    assert card["formal_recommendation"] is False
    assert card["recommendation"]["tier"] == "ANALYSIS_PICK"
    assert card["recommendation"]["candidate"] is False
    assert card["recommendation"]["formal_recommendation"] is False
    assert card["result"]["final_score"] == "2-1"
    assert card["validation"]["settlement"] == "HIT"
    assert card["validation"]["market_hit"] is True
    assert card["validation"]["score_exact_hit"] is True
    assert card["validation"]["counted_in_official"] is False
    assert card["validation"]["counted_in_analysis_shadow"] is True
    assert len(card["scoreline_picks"]) == 3
    assert card["scoreline_picks"][0]["probability_label"] == "22%"

    performance = payload["performance"]
    assert performance["sample_size"] == 0
    assert performance["official"]["sample_size"] == 0
    assert performance["analysis_shadow"]["sample_size"] == 1
    assert performance["analysis_shadow"]["hit_rate"] == 1.0
    assert performance["candidate_count"] == 0
    assert performance["analysis_pick_count"] == 1
