from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo

import pytest

from w2.api import repository as api_repository
from w2.api.repository import ReadModelService
from w2.dashboard.scorelines import scoreline_picks_from_card, scoreline_reference_from_card

KICKOFF = datetime.now(UTC) + timedelta(hours=12)


class FutureFixtureRepository:
    def __init__(self, *, market_ou: str = "2.5") -> None:
        self.market_ou = market_ou

    def release_counts(self) -> dict[str, int]:
        return {
            "read_model_fixture_count": 1,
            "matchday_card_count": 0,
            "future_fixture_count": 1,
            "result_event_count": 0,
        }

    def staging_seed_dashboard(self) -> dict[str, Any] | None:
        return None

    def dashboard_latest_fixtures(self) -> list[dict[str, Any]]:
        return []

    def matchday_cards(self) -> list[dict[str, Any]]:
        return []

    def dashboard_fixture(self, fixture_id: str) -> dict[str, Any] | None:
        return None

    def result_events(self) -> list[dict[str, Any]]:
        return []

    def fixture_payloads(self) -> list[dict[str, Any]]:
        return [
            {
                "fixture": {
                    "id": "fixture-xg",
                    "date": KICKOFF.isoformat().replace("+00:00", "Z"),
                    "status": {"short": "NS"},
                },
                "league": {"id": 1, "name": "World Cup"},
                "teams": {
                    "home": {"id": 10, "name": "Strong"},
                    "away": {"id": 20, "name": "Weak"},
                },
            }
        ]

    def future_market_observations(self) -> list[dict[str, Any]]:
        captured = (KICKOFF - timedelta(hours=3)).isoformat().replace("+00:00", "Z")
        return [
            {
                "fixture_id": "fixture-xg",
                "canonical_market": "ASIAN_HANDICAP",
                "selection": "Home -0.5",
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
                "fixture_id": "fixture-xg",
                "canonical_market": "ASIAN_HANDICAP",
                "selection": "Away +0.5",
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
                "fixture_id": "fixture-xg",
                "canonical_market": "TOTALS",
                "selection": "Over",
                "line": self.market_ou,
                "decimal_odds": "1.91",
                "captured_at": captured,
                "provider_last_update": captured,
                "bookmaker_id": "bm1",
                "bookmaker_name": "Book",
                "suspended": False,
                "live": False,
            },
            {
                "fixture_id": "fixture-xg",
                "canonical_market": "TOTALS",
                "selection": "Under",
                "line": self.market_ou,
                "decimal_odds": "1.91",
                "captured_at": captured,
                "provider_last_update": captured,
                "bookmaker_id": "bm1",
                "bookmaker_name": "Book",
                "suspended": False,
                "live": False,
            },
        ]


class LegacyEmbeddedScorelineRepository(FutureFixtureRepository):
    def matchday_cards(self) -> list[dict[str, Any]]:
        return [
            {
                "fixture": {
                    "fixture_id": "fixture-xg",
                    "competition_id": "1",
                    "competition_name": "World Cup",
                    "kickoff_utc": KICKOFF.isoformat().replace("+00:00", "Z"),
                    "status": "NS",
                    "home_team_id": "10",
                    "home_team_name": "Strong",
                    "away_team_id": "20",
                    "away_team_name": "Weak",
                },
                "card": {"action": "DATA"},
                "temporal": {},
                "analysis_card": {
                    "decision": "ANALYSIS_PICK",
                    "candidate": False,
                    "formal_recommendation": False,
                    "markets": [
                        {
                            "market": "SCORE",
                            "decision": "ANALYSIS_PICK",
                            "score_card": {
                                "scenarios": [{"scoreline": "1-0", "conditional_probability": 0.2}]
                            },
                        }
                    ],
                },
            }
        ]


class XgStore:
    def __init__(self, *, partial: bool = False) -> None:
        self.partial = partial

    def raw_payloads(self, endpoint: str) -> list[dict[str, Any]]:
        return []

    def team_xg_rolling_snapshots(self, *, fixture_id: str | None = None) -> list[dict[str, Any]]:
        assert fixture_id == "fixture-xg"
        rows = [
            {
                "team_id": "10",
                "as_of_time": (KICKOFF - timedelta(hours=1)).isoformat(),
                "rolling_xg_for": 2.2,
                "rolling_xg_against": 0.6,
                "rolling_goals_for": 2.0,
                "rolling_goals_against": 0.8,
            },
            {
                "team_id": "20",
                "as_of_time": (KICKOFF - timedelta(hours=1)).isoformat(),
                "rolling_xg_for": 0.7,
                "rolling_xg_against": 1.8,
                "rolling_goals_for": 0.8,
                "rolling_goals_against": 1.6,
            },
        ]
        return rows[:1] if self.partial else rows

    def team_xg_matches(self) -> list[dict[str, Any]]:
        return [
            {
                "team_id": team_id,
                "kickoff_at": (KICKOFF - timedelta(days=day)).isoformat(),
            }
            for team_id in ("10", "20")
            for day in range(1, 5)
        ]


def test_xg_ready_emits_scoreline_readiness_and_dashboard_picks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(api_repository, "future_refresh_db_repository", lambda: XgStore())
    service = ReadModelService(repository=cast(Any, FutureFixtureRepository()))

    card = service.analysis_card("fixture-xg")

    assert card is not None
    assert card["scoreline_readiness"]["status"] == "READY"
    assert card["scoreline_readiness"]["source"] == "independent_xg_poisson"
    assert card["scoreline_readiness"]["lambda_home"] > card["scoreline_readiness"]["lambda_away"]
    assert card["pricing_shadow"]["fair_ou"] == card["scoreline_readiness"]["fair_ou"]
    assert card["pricing_shadow"]["beats_market"] is False
    assert card["formal_recommendation"] is False
    assert card["candidate"] is False
    assert scoreline_picks_from_card(card)

    target_date = KICKOFF.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
    dashboard = service.dashboard(target_date=target_date, window="next36")
    dashboard_card = dashboard["all"][0]
    assert dashboard_card["scoreline_readiness"]["status"] == "READY"
    assert dashboard_card["pick"] is None
    assert dashboard_card["scoreline_picks"] == []
    assert dashboard_card["scoreline_reference"] is None


def test_market_ou_does_not_change_independent_scoreline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(api_repository, "future_refresh_db_repository", lambda: XgStore())
    first = ReadModelService(repository=cast(Any, FutureFixtureRepository(market_ou="2.0")))
    second = ReadModelService(repository=cast(Any, FutureFixtureRepository(market_ou="3.5")))

    first_card = first.analysis_card("fixture-xg")
    second_card = second.analysis_card("fixture-xg")

    assert first_card is not None
    assert second_card is not None
    assert (
        first_card["scoreline_readiness"]["lambda_home"]
        == second_card["scoreline_readiness"]["lambda_home"]
    )
    assert (
        first_card["scoreline_readiness"]["lambda_away"]
        == second_card["scoreline_readiness"]["lambda_away"]
    )
    assert (
        first_card["scoreline_readiness"]["fair_ou"]
        == second_card["scoreline_readiness"]["fair_ou"]
    )
    assert scoreline_picks_from_card(first_card) == scoreline_picks_from_card(second_card)


def test_xg_partial_history_hides_scorelines_and_fair_ou(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        api_repository,
        "future_refresh_db_repository",
        lambda: XgStore(partial=True),
    )
    service = ReadModelService(repository=cast(Any, FutureFixtureRepository()))

    card = service.analysis_card("fixture-xg")

    assert card is not None
    assert card["scoreline_readiness"]["status"] == "INSUFFICIENT_INDEPENDENT_XG"
    assert card["scoreline_readiness"]["reason"] == "PARTIAL_HISTORY"
    assert card["scoreline_readiness"]["blocker"] == "XG_SAMPLE_INSUFFICIENT_FOR_FIXTURE"
    assert card["data_readiness"]["xg_blocker"] == "XG_SAMPLE_INSUFFICIENT_FOR_FIXTURE"
    assert scoreline_picks_from_card(card) == []
    assert card["pricing_shadow"]["fair_ou"] is None
    score_market = next(market for market in card["markets"] if market["market"] == "SCORE")
    assert score_market["decision"] == "SKIP"


def test_legacy_embedded_scoreline_card_is_refreshed_for_readiness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(api_repository, "future_refresh_db_repository", lambda: XgStore())
    service = ReadModelService(repository=cast(Any, LegacyEmbeddedScorelineRepository()))

    card = service.analysis_card("fixture-xg")

    assert card is not None
    assert card["scoreline_readiness"]["status"] == "READY"
    assert card["scoreline_readiness"]["source"] == "independent_xg_poisson"
    assert card["pricing_shadow"]["fair_ou"] == card["scoreline_readiness"]["fair_ou"]

    target_date = KICKOFF.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
    dashboard_card = service.dashboard(target_date=target_date, window="next36")["all"][0]
    assert dashboard_card["scoreline_readiness"]["status"] == "READY"
    assert dashboard_card["pricing_shadow"]["fair_ou"] == card["scoreline_readiness"]["fair_ou"]


def test_recommended_scores_satisfy_primary_and_strict_secondary() -> None:
    card = {
        "simulation": {
            "status": "READY",
            "lambda_home": 1.8,
            "lambda_away": 0.8,
            "ou_probabilities": {},
        },
        "secondary_picks": [{"market": "TOTALS", "tendency": "UNDER", "line": 2.5}],
    }
    reference = scoreline_reference_from_card(
        card,
        recommendation={
            "tier": "ANALYSIS_PICK",
            "market": "ASIAN_HANDICAP",
            "selection": "HOME_AH",
            "line": -0.5,
        },
    )
    assert reference is not None
    scores = reference["direction_top3"]
    assert scores
    assert all(item["home_goals"] > item["away_goals"] for item in scores)
    assert all(item["home_goals"] + item["away_goals"] < 2.5 for item in scores)
