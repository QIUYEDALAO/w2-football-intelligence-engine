from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

import pytest

from w2.api import repository as api_repository
from w2.api.repository import ReadModelService

NOW = datetime(2026, 6, 25, 12, 0, tzinfo=UTC)
KICKOFF = NOW + timedelta(days=1)


class FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW if tz is not None else NOW.replace(tzinfo=None)


@pytest.fixture(autouse=True)
def _freeze_repository_clock(monkeypatch):
    monkeypatch.setattr(api_repository, "datetime", FrozenDateTime)


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

    def public_fixture_payloads(self, *, limit: int) -> list[dict[str, Any]]:
        return self.fixture_payloads()[:limit]

    def fixture_payload(self, fixture_id: str) -> dict[str, Any] | None:
        aliases = {fixture_id}
        if fixture_id.startswith("api_football:"):
            aliases.add(fixture_id.removeprefix("api_football:"))
        elif fixture_id.isdigit():
            aliases.add(f"api_football:{fixture_id}")
        for payload in self.fixture_payloads():
            payload_id = str(payload.get("fixture", {}).get("id") or "")
            if payload_id in aliases:
                return payload
        return None

    def future_market_observations(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for index, captured in enumerate(
            (NOW - timedelta(hours=3), NOW - timedelta(minutes=10))
        ):
            for bookmaker_id, bookmaker_name, home_price, away_price, over_price, under_price in (
                ("1", "Pinnacle", "1.95", "1.96", "1.90", "1.94"),
                ("2", "SoftBook", "2.04", "1.92", "2.02", "1.86"),
            ):
                rows.append(
                    {
                        "observation_id": f"ah-home-{index}-{bookmaker_id}",
                        "fixture_id": "1489410",
                        "provider": "api-football",
                        "canonical_market": "ASIAN_HANDICAP",
                        "raw_market_label": "Asian Handicap",
                        "selection": "Home -0.5",
                        "line": "-0.5",
                        "decimal_odds": home_price if index == 0 else "1.80",
                        "bookmaker_id": bookmaker_id,
                        "bookmaker_name": bookmaker_name,
                        "provider_last_update": captured.isoformat().replace("+00:00", "Z"),
                        "captured_at": captured.isoformat().replace("+00:00", "Z"),
                        "raw_payload_sha256": f"{index + 1}" * 64,
                        "source_revision": "future-refresh.v1",
                        "suspended": False,
                        "live": False,
                    }
                )
                rows.append(
                    {
                        "observation_id": f"ah-away-{index}-{bookmaker_id}",
                        "fixture_id": "1489410",
                        "provider": "api-football",
                        "canonical_market": "ASIAN_HANDICAP",
                        "raw_market_label": "Asian Handicap",
                        "selection": "Away +0.5",
                        "line": "+0.5",
                        "decimal_odds": away_price if index == 0 else "2.02",
                        "bookmaker_id": bookmaker_id,
                        "bookmaker_name": bookmaker_name,
                        "provider_last_update": captured.isoformat().replace("+00:00", "Z"),
                        "captured_at": captured.isoformat().replace("+00:00", "Z"),
                        "raw_payload_sha256": f"{index + 1}" * 64,
                        "source_revision": "future-refresh.v1",
                        "suspended": False,
                        "live": False,
                    }
                )
                rows.append(
                    {
                        "observation_id": f"ou-over-{index}-{bookmaker_id}",
                        "fixture_id": "1489410",
                        "provider": "api-football",
                        "canonical_market": "TOTALS",
                        "selection": "Over",
                        "line": "2.5",
                        "decimal_odds": over_price if index == 0 else "1.72",
                        "bookmaker_id": bookmaker_id,
                        "bookmaker_name": bookmaker_name,
                        "provider_last_update": captured.isoformat().replace("+00:00", "Z"),
                        "captured_at": captured.isoformat().replace("+00:00", "Z"),
                        "raw_payload_sha256": f"{index + 1}" * 64,
                        "source_revision": "future-refresh.v1",
                        "suspended": False,
                        "live": False,
                    }
                )
                rows.append(
                    {
                        "observation_id": f"ou-under-{index}-{bookmaker_id}",
                        "fixture_id": "1489410",
                        "provider": "api-football",
                        "canonical_market": "TOTALS",
                        "selection": "Under",
                        "line": "2.5",
                        "decimal_odds": under_price if index == 0 else "2.10",
                        "bookmaker_id": bookmaker_id,
                        "bookmaker_name": bookmaker_name,
                        "provider_last_update": captured.isoformat().replace("+00:00", "Z"),
                        "captured_at": captured.isoformat().replace("+00:00", "Z"),
                        "raw_payload_sha256": f"{index + 1}" * 64,
                        "source_revision": "future-refresh.v1",
                        "suspended": False,
                        "live": False,
                    }
                )
        return rows

    def future_market_observations_for_fixtures(
        self,
        fixture_ids: list[str],
    ) -> list[dict[str, Any]]:
        aliases: set[str] = set()
        for fixture_id in fixture_ids:
            aliases.add(fixture_id)
            if fixture_id.startswith("api_football:"):
                aliases.add(fixture_id.removeprefix("api_football:"))
            elif fixture_id.isdigit():
                aliases.add(f"api_football:{fixture_id}")
        return [
            row
            for row in self.future_market_observations()
            if str(row.get("fixture_id") or "") in aliases
        ]


class FakeReadRepositoryWithStaleDashboardFixture(FakeReadRepository):
    def dashboard_fixture(self, fixture_id: str) -> dict[str, Any] | None:
        if fixture_id != "1489410":
            return None
        return {
            "fixture_id": "1489410",
            "competition_id": "world_cup_2026",
            "competition_name": "World Cup",
            "kickoff_utc": KICKOFF.isoformat().replace("+00:00", "Z"),
            "status": "NS",
            "home_team_id": "10",
            "away_team_id": "20",
            "home_team_name": "Home",
            "away_team_name": "Away",
            "market_coverage": {},
        }


class FakeReadRepositoryWithStaleEmbeddedCard(FakeReadRepository):
    def matchday_cards(self) -> list[dict[str, Any]]:
        return [
            {
                "fixture": {
                    "fixture_id": "1489410",
                    "competition_id": "world_cup_2026",
                    "competition_name": "World Cup",
                    "kickoff_utc": KICKOFF.isoformat().replace("+00:00", "Z"),
                    "status": "NS",
                    "home_team_id": "10",
                    "away_team_id": "20",
                    "home_team_name": "Home",
                    "away_team_name": "Away",
                    "market_coverage": {},
                },
                "analysis_card": {
                    "fixture_id": "1489410",
                    "decision": "SKIP",
                    "markets": [],
                    "data_readiness": {
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
                    },
                    "scoreline_readiness": {
                        "status": "INSUFFICIENT_INDEPENDENT_XG",
                        "reason": "STALE_EMBEDDED_CARD",
                    },
                },
            }
        ]


class FakeReadRepositoryWithStaleQuotes(FakeReadRepository):
    def future_market_observations(self) -> list[dict[str, Any]]:
        rows = super().future_market_observations()
        stale = (NOW - timedelta(minutes=31)).isoformat().replace("+00:00", "Z")
        return [{**row, "captured_at": stale} for row in rows]


class FakeDbRepository:
    def raw_payloads(self, endpoint: str) -> list[dict[str, Any]]:
        if endpoint != "lineups":
            return []
        return [
            {
                "captured_at": (NOW - timedelta(minutes=10)).isoformat().replace(
                    "+00:00",
                    "Z",
                ),
                "payload": {
                    "parameters": {"fixture": "1489410"},
                    "response": [
                        {
                            "team": {"id": 10},
                            "startXI": [{"player": {"id": 1, "name": "Home GK"}}],
                        },
                        {
                            "team": {"id": 20},
                            "startXI": [{"player": {"id": 2, "name": "Away GK"}}],
                        },
                    ],
                },
            }
        ]

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

    def team_xg_matches(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for team_id in ("10", "20"):
            for index in range(5):
                rows.append(
                    {
                        "team_id": team_id,
                        "kickoff_at": (NOW - timedelta(days=10 - index)).isoformat(),
                    }
                )
        return rows


class FakeCanonicalDbRepository(FakeDbRepository):
    def matchday_fixture_identity(self, fixture_id: str) -> dict[str, Any] | None:
        if fixture_id not in {"1489410", "api_football:1489410"}:
            return None
        return {
            "status": "PROVIDER_PRIMARY_READY",
            "fixture_id": "api_football:1489410",
            "provider_fixture_id": "1489410",
            "competition_id": "world_cup_2026",
            "season": "2026",
            "home_provider_team_id": "10",
            "away_provider_team_id": "20",
            "home_w2_team_id": "w2:team:home",
            "away_w2_team_id": "w2:team:away",
            "identity_hash": "fixture-identity",
        }

    def canonical_match_history_for_teams(
        self,
        team_ids: list[str],
        *,
        before: datetime,
        limit_per_team: int = 20,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for team_id, opponent_id, goals_for, goals_against in (
            ("w2:team:home", "w2:team:away", 2, 1),
            ("w2:team:away", "w2:team:home", 1, 2),
        ):
            for index in range(5):
                rows.append(
                    {
                        "history_id": f"{team_id}:{index}",
                        "fixture_id": f"canonical-{index}",
                        "provider_fixture_id": f"provider-{index}",
                        "team_w2_id": team_id,
                        "opponent_w2_id": opponent_id,
                        "kickoff_utc": (KICKOFF - timedelta(days=30 - index)).isoformat(),
                        "goals_for": goals_for,
                        "goals_against": goals_against,
                        "result_identity_hash": f"result-{team_id}-{index}",
                        "history_hash": f"history-{team_id}-{index}",
                    }
                )
        return [row for row in rows if row["team_w2_id"] in team_ids]

    def team_rating_snapshots_for_w2_teams(
        self,
        team_ids: list[str],
        *,
        before: datetime,
    ) -> list[dict[str, Any]]:
        rows = [
            {
                "rating_id": "rating-home",
                "w2_team_id": "w2:team:home",
                "observed_at": (KICKOFF - timedelta(days=1)).isoformat(),
                "model_version": "rating_from_history.v1",
                "elo": 1600.0,
                "attack_strength": 1.7,
                "defence_strength": 0.8,
                "form_index": 0.6,
                "source": "team_rating_snapshots",
                "rating_hash": "rating-hash-home",
            },
            {
                "rating_id": "rating-away",
                "w2_team_id": "w2:team:away",
                "observed_at": (KICKOFF - timedelta(days=1)).isoformat(),
                "model_version": "rating_from_history.v1",
                "elo": 1450.0,
                "attack_strength": 0.8,
                "defence_strength": 1.5,
                "form_index": -0.3,
                "source": "team_rating_snapshots",
                "rating_hash": "rating-hash-away",
            },
        ]
        return [row for row in rows if row["w2_team_id"] in team_ids]

    def team_xg_rolling_snapshots_for_w2_teams(
        self,
        team_ids: list[str],
        *,
        before: datetime,
        competition_id: str,
        season: str,
    ) -> list[dict[str, Any]]:
        rows = [
            {
                "snapshot_id": "xg-home",
                "team_id": "w2:team:home",
                "provider_team_id": "10",
                "as_of_fixture_id": "1489410",
                "as_of_time": (KICKOFF - timedelta(hours=1)).isoformat(),
                "match_count": 5,
                "rolling_xg_for": 1.8,
                "rolling_xg_against": 0.7,
                "rolling_goals_for": 2.0,
                "rolling_goals_against": 0.8,
                "regression_index": 0.3,
                "identity_projection_status": "READY",
            },
            {
                "snapshot_id": "xg-away",
                "team_id": "w2:team:away",
                "provider_team_id": "20",
                "as_of_fixture_id": "1489410",
                "as_of_time": (KICKOFF - timedelta(hours=1)).isoformat(),
                "match_count": 5,
                "rolling_xg_for": 0.9,
                "rolling_xg_against": 1.5,
                "rolling_goals_for": 0.8,
                "rolling_goals_against": 1.8,
                "regression_index": -0.2,
                "identity_projection_status": "READY",
            },
        ]
        return [row for row in rows if row["team_id"] in team_ids]

    def team_xg_matches_for_w2_teams(
        self,
        team_ids: list[str],
        *,
        before: datetime,
        limit_per_team: int = 20,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for team_id in ("w2:team:home", "w2:team:away"):
            for index in range(5):
                rows.append(
                    {
                        "team_id": team_id,
                        "provider_team_id": "10" if team_id.endswith("home") else "20",
                        "kickoff_at": (KICKOFF - timedelta(days=10 - index)).isoformat(),
                    }
                )
        return [row for row in rows if row["team_id"] in team_ids]


def test_read_model_line_value_prefers_split_selection_over_stale_stored_line() -> None:
    service = ReadModelService(repository=cast(Any, FakeReadRepository()))
    row = {"selection": "Over 2/2.5", "line": "2.5"}

    assert service._line_value(row) == "2.25"  # noqa: SLF001
    assert service._decimal_line(row) == Decimal("2.25")  # noqa: SLF001


def test_analysis_card_uses_materialized_xg_and_market_snapshots(monkeypatch) -> None:
    monkeypatch.setattr(api_repository, "future_refresh_db_repository", lambda: FakeDbRepository())
    service = ReadModelService(repository=cast(Any, FakeReadRepository()))

    card = service.analysis_card("1489410")

    assert card is not None
    assert card["decision"] == "ANALYSIS_PICK"
    assert card["candidate"] is False
    assert card["formal_recommendation"] is False
    assert card["home_name"] == "Home"
    assert card["away_name"] == "Away"
    assert card["competition_name"] == "World Cup"
    assert card["competition_id"] == "world_cup_2026"
    assert card["data_readiness"] == {
        "market_observations": 16,
        "bookmakers": 2,
        "odds_snapshots": 2,
        "xg": True,
        "xg_status": "READY",
        "xg_home_match_count": 5,
        "xg_away_match_count": 5,
        "xg_snapshot_count": 2,
        "h2h": False,
        "lineups": True,
        "lineups_status": "READY",
        "lineups_captured_at": (NOW - timedelta(minutes=10)).isoformat().replace(
            "+00:00",
            "Z",
        ),
        "statistics_status": "NOT_REQUESTED",
        "statistics_captured_at": None,
    }
    assert card["model_probabilities"]
    assert {
        key: card["current_odds"]["ah"].get(key)
        for key in ("line", "home_price", "away_price", "home_line", "away_line", "price")
    } == {
        "line": "0.5",
        "home_price": 1.8,
        "away_price": 2.02,
        "home_line": "-0.5",
        "away_line": "0.5",
        "price": 1.91,
    }
    assert card["current_odds"]["ah"]["selection_policy"]
    assert card["current_odds"]["ah"]["candidate_lines"]
    assert card["current_odds"]["ah"]["rejected_lines"] == []
    assert {
        key: card["current_odds"]["ou"].get(key)
        for key in ("line", "over_price", "under_price", "over_line", "under_line", "price")
    } == {
        "line": "2.5",
        "over_price": 1.72,
        "under_price": 2.1,
        "over_line": "2.5",
        "under_line": "2.5",
        "price": 1.91,
    }
    assert card["current_odds"]["ou"]["selection_policy"]
    assert card["current_odds"]["ou"]["candidate_lines"]
    assert card["quote_identity_audit"]["ah"]["identity_status"] == "COMPLETE"
    assert card["quote_identity_audit"]["ou"]["identity_status"] == "COMPLETE"
    assert len(card["quote_identity_audit"]["ah"]["observation_ids"]) == 2
    assert "quote_identity" not in card["current_odds"]["ah"]
    assert "quote_identity" not in card["pricing_shadow"]
    assert card["line_movement"]["ah_open"] in {"-0.5", "0.5"}
    assert card["line_movement"]["ah_current"] in {"-0.5", "0.5"}
    decisions = {market["market"]: market["decision"] for market in card["markets"]}
    assert decisions["ASIAN_HANDICAP"] == "WATCH"
    assert decisions["TOTALS"] in {"PICK", "ANALYSIS_PICK"}
    assert decisions["FIRST_HALF_GOALS"] == "PICK"
    assert decisions["SCORE"] == "NO_EDGE"
    assert any(
        "F9_TRUE_XG:AS_OF_ROLLING_XG_DIFF" in reason
        for market in card["markets"]
        for reason in market["reasons"]
    )
    ah_market = next(market for market in card["markets"] if market["market"] == "ASIAN_HANDICAP")
    totals_market = next(market for market in card["markets"] if market["market"] == "TOTALS")
    score_market = next(market for market in card["markets"] if market["market"] == "SCORE")
    assert ah_market["lean"] is None
    assert "跟随市场 · 无独立优势 · 仅参考" in ah_market["reason"]
    assert totals_market["reason"].startswith("两队滚动 xG 进攻合计 2.70")
    assert score_market["scores"] == []
    assert card["bookmaker_intent"]["intent"] in {"HOME_LEAN", "AWAY_LEAN"}


def test_analysis_card_prefers_future_refresh_observations_over_stale_dashboard(
    monkeypatch,
) -> None:
    monkeypatch.setattr(api_repository, "future_refresh_db_repository", lambda: FakeDbRepository())
    service = ReadModelService(
        repository=cast(Any, FakeReadRepositoryWithStaleDashboardFixture()),
    )

    card = service.analysis_card("1489410")

    assert card is not None
    assert card["source"] == "db_feature_materialized_analysis"
    assert card["data_readiness"]["market_observations"] == 16
    assert card["current_odds"]["ah"]["home_line"] == "-0.5"
    assert card["current_odds"]["ou"]["line"] == "2.5"
    reasons = {
        market["market"]: market["reasons"]
        for market in card["markets"]
        if isinstance(market, dict)
    }
    assert reasons["ASIAN_HANDICAP"] != ["AH_MARKET_UNAVAILABLE"]
    assert reasons["TOTALS"] != ["OU_MARKET_UNAVAILABLE"]


def test_stale_quotes_remain_auditable_but_are_not_current_or_executable(
    monkeypatch,
) -> None:
    monkeypatch.setattr(api_repository, "future_refresh_db_repository", lambda: FakeDbRepository())
    service = ReadModelService(repository=cast(Any, FakeReadRepositoryWithStaleQuotes()))

    card = service.analysis_card("1489410")

    assert card is not None
    assert card["quote_identity_audit"]["ah"]["freshness_status"] == "STALE"
    assert card["quote_identity_audit"]["ou"]["freshness_status"] == "STALE"
    assert "current_odds" not in card
    assert "market_probabilities" not in card
    for market in card["markets"]:
        if market["market"] in {"ASIAN_HANDICAP", "TOTALS"}:
            assert "odds" not in market


class FakeReadRepositoryWithMarketBalancedLines(FakeReadRepository):
    def future_market_observations(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        captured = NOW - timedelta(minutes=20)
        for bookmaker_id, bookmaker_name in (("1", "Pinnacle"), ("2", "SoftBook")):
            for selection, line, price in (
                ("Home 0", "0", "1.11"),
                ("Away 0", "0", "6.80"),
                ("Home -1.5", "-1.5", "1.92"),
                ("Away +1.5", "+1.5", "1.96"),
            ):
                rows.append(
                    {
                        "observation_id": f"ah-{bookmaker_id}-{selection}",
                        "fixture_id": "1489410",
                        "provider": "api-football",
                        "canonical_market": "ASIAN_HANDICAP",
                        "raw_market_label": "Asian Handicap",
                        "selection": selection,
                        "line": line,
                        "decimal_odds": price,
                        "bookmaker_id": bookmaker_id,
                        "bookmaker_name": bookmaker_name,
                        "provider_last_update": captured.isoformat().replace("+00:00", "Z"),
                        "captured_at": captured.isoformat().replace("+00:00", "Z"),
                        "raw_payload_sha256": "a" * 64,
                        "source_revision": "future-refresh.v1",
                        "suspended": False,
                        "live": False,
                    }
                )
            for selection, line, price in (
                ("Over 2.5", "2.5", "1.18"),
                ("Under 2.5", "2.5", "5.90"),
                ("Over 3.5", "3.5", "1.91"),
                ("Under 3.5", "3.5", "1.93"),
            ):
                rows.append(
                    {
                        "observation_id": f"ou-{bookmaker_id}-{selection}",
                        "fixture_id": "1489410",
                        "provider": "api-football",
                        "canonical_market": "TOTALS",
                        "selection": selection,
                        "line": line,
                        "decimal_odds": price,
                        "bookmaker_id": bookmaker_id,
                        "bookmaker_name": bookmaker_name,
                        "provider_last_update": captured.isoformat().replace("+00:00", "Z"),
                        "captured_at": captured.isoformat().replace("+00:00", "Z"),
                        "raw_payload_sha256": "b" * 64,
                        "source_revision": "future-refresh.v1",
                        "suspended": False,
                        "live": False,
                    }
                )
        return rows


def test_analysis_card_prefers_market_balanced_lines_over_fixed_lines(monkeypatch) -> None:
    monkeypatch.setattr(api_repository, "future_refresh_db_repository", lambda: FakeDbRepository())
    service = ReadModelService(repository=cast(Any, FakeReadRepositoryWithMarketBalancedLines()))

    card = service.analysis_card("1489410")

    assert card is not None
    assert card["current_odds"]["ah"]["line"] == "1.5"
    assert card["current_odds"]["ah"]["home_line"] == "-1.5"
    assert card["current_odds"]["ah"]["away_line"] == "1.5"
    assert card["current_odds"]["ah"]["display_line_cn"] == "主队 -1.5"
    assert card["current_odds"]["ah"]["home_display_line_cn"] == "主队 -1.5"
    assert card["current_odds"]["ah"]["away_display_line_cn"] == "客队 +1.5"
    assert card["pricing_shadow"]["market_ah"] == -1.5
    assert card["current_odds"]["ou"]["line"] == "3.5"
    assert card["current_odds"]["ou"]["over_price"] == 1.91
    assert card["current_odds"]["ou"]["under_price"] == 1.93
    ah_market = next(market for market in card["markets"] if market["market"] == "ASIAN_HANDICAP")
    totals_market = next(market for market in card["markets"] if market["market"] == "TOTALS")
    assert ah_market["balanced_line"] == "-1.5"
    assert ah_market["line"] in {"-1.5", "1.5"}
    assert totals_market["line"] == "3.5"
    assert ah_market["line_status"] == "READY"
    assert totals_market["line_status"] == "READY"


def test_public_bounded_analysis_rebuilds_materialized_card_over_stale_embedded(
    monkeypatch,
) -> None:
    monkeypatch.setattr(api_repository, "future_refresh_db_repository", lambda: FakeDbRepository())
    service = ReadModelService(
        repository=cast(Any, FakeReadRepositoryWithStaleEmbeddedCard()),
    )

    card = service.public_analysis_card_bounded(
        "1489410",
        evaluation_time=NOW,
        use_frozen_canary=False,
    )

    assert card is not None
    assert card["source"] == "db_feature_materialized_analysis"
    assert card["data_readiness"]["market_observations"] == 16
    assert card["data_readiness"]["bookmakers"] == 2
    assert card["quote_identity_audit"]["ah"]["identity_status"] == "COMPLETE"
    assert card["quote_identity_audit"]["ou"]["identity_status"] == "COMPLETE"
    assert card["scoreline_readiness"]["reason"] != "STALE_EMBEDDED_CARD"


def test_public_bounded_analysis_accepts_api_football_fixture_alias(
    monkeypatch,
) -> None:
    monkeypatch.setattr(api_repository, "future_refresh_db_repository", lambda: FakeDbRepository())
    service = ReadModelService(repository=cast(Any, FakeReadRepository()))

    card = service.public_analysis_card_bounded(
        "api_football:1489410",
        evaluation_time=NOW,
        use_frozen_canary=False,
    )

    assert card is not None
    assert card["source"] == "db_feature_materialized_analysis"
    assert card["data_readiness"]["market_observations"] == 16
    assert card["quote_identity_audit"]["ah"]["identity_status"] == "COMPLETE"


def test_public_bounded_analysis_consumes_canonical_identity_history_and_ratings(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        api_repository,
        "future_refresh_db_repository",
        lambda: FakeCanonicalDbRepository(),
    )
    service = ReadModelService(repository=cast(Any, FakeReadRepository()))

    card = service.public_analysis_card_bounded(
        "api_football:1489410",
        evaluation_time=NOW,
        use_frozen_canary=False,
    )

    assert card is not None
    assert card["source"] == "db_feature_materialized_analysis"
    assert card["data_readiness"]["xg"] is True
    assert card["data_readiness"]["xg_home_match_count"] == 5
    assert card["data_readiness"]["xg_away_match_count"] == 5
    assert card["simulation"]["input_readiness"]["home_elo_source"] == "team_rating_snapshots"
    assert card["simulation"]["input_readiness"]["away_elo_source"] == "team_rating_snapshots"
    assert card["simulation"]["input_readiness"]["home_elo_collection_status"] == "READY"
    assert card["simulation"]["input_readiness"]["away_elo_collection_status"] == "READY"
    contributions = card["feature_contributions"]
    assert any(
        item["id"] == "F3_REST_FITNESS"
        and item["source_group"] == "team_fixture_history"
        and item["is_independent_signal"] is True
        for item in contributions
    )
    assert all(item.get("proxy_of") != "ratings" for item in contributions)


class FakeReadRepositoryOnlyExtremeLines(FakeReadRepository):
    def future_market_observations(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for captured in (NOW - timedelta(hours=3), NOW - timedelta(hours=1)):
            for bookmaker_id, bookmaker_name in (("1", "Pinnacle"), ("2", "SoftBook")):
                rows.append(
                    {
                        "fixture_id": "1489410",
                        "canonical_market": "ASIAN_HANDICAP",
                        "raw_market_label": "Asian Handicap",
                        "selection": "Home 0",
                        "line": "0",
                        "decimal_odds": "1.11",
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
                        "canonical_market": "ASIAN_HANDICAP",
                        "raw_market_label": "Asian Handicap",
                        "selection": "Away 0",
                        "line": "0",
                        "decimal_odds": "6.50",
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
                        "selection": "Over 2.5",
                        "line": "2.5",
                        "decimal_odds": "1.08",
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
                        "selection": "Under 2.5",
                        "line": "2.5",
                        "decimal_odds": "7.00",
                        "bookmaker_id": bookmaker_id,
                        "bookmaker_name": bookmaker_name,
                        "provider_last_update": captured.isoformat().replace("+00:00", "Z"),
                        "captured_at": captured.isoformat().replace("+00:00", "Z"),
                        "suspended": False,
                        "live": False,
                    }
                )
        return rows


def test_analysis_card_skips_market_when_only_extreme_lines_exist(monkeypatch) -> None:
    monkeypatch.setattr(api_repository, "future_refresh_db_repository", lambda: FakeDbRepository())
    service = ReadModelService(repository=cast(Any, FakeReadRepositoryOnlyExtremeLines()))

    card = service.analysis_card("1489410")

    assert card is not None
    assert "current_odds" not in card
    ah_market = next(market for market in card["markets"] if market["market"] == "ASIAN_HANDICAP")
    totals_market = next(market for market in card["markets"] if market["market"] == "TOTALS")
    assert ah_market["decision"] == "SKIP"
    assert totals_market["decision"] == "SKIP"
    assert ah_market["line_status"] == "NO_BALANCED_MAINLINE"
    assert totals_market["line_status"] == "NO_BALANCED_MAINLINE"
    assert ah_market["reason"] == "无有效主盘"
    assert totals_market["reason"] == "无有效主盘"
