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
            for bookmaker_id, bookmaker_name, home_price, away_price, over_price, under_price in (
                ("1", "Pinnacle", "1.95", "1.96", "1.90", "1.94"),
                ("2", "SoftBook", "2.04", "1.92", "2.02", "1.86"),
            ):
                rows.append(
                    {
                        "fixture_id": "1489410",
                        "canonical_market": "ASIAN_HANDICAP",
                        "selection": "Home -0.5",
                        "line": "-0.5",
                        "decimal_odds": home_price if index == 0 else "1.80",
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
                        "selection": "Away +0.5",
                        "line": "+0.5",
                        "decimal_odds": away_price if index == 0 else "2.02",
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
                        "decimal_odds": over_price if index == 0 else "1.72",
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
                        "selection": "Under",
                        "line": "2.5",
                        "decimal_odds": under_price if index == 0 else "2.10",
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
    assert card["current_odds"]["ah"] == {
        "line": "0.5",
        "home_price": 1.8,
        "away_price": 2.02,
        "home_line": "-0.5",
        "away_line": "0.5",
        "price": 1.91,
    }
    assert card["current_odds"]["ou"] == {
        "line": "2.5",
        "over_price": 1.72,
        "under_price": 2.1,
        "over_line": "2.5",
        "under_line": "2.5",
        "price": 1.91,
    }
    assert card["line_movement"]["ah_open"] in {"-0.5", "0.5"}
    assert card["line_movement"]["ah_current"] in {"-0.5", "0.5"}
    decisions = {market["market"]: market["decision"] for market in card["markets"]}
    assert decisions["ASIAN_HANDICAP"] == "WATCH"
    assert decisions["TOTALS"] == "PICK"
    assert decisions["FIRST_HALF_GOALS"] == "PICK"
    assert decisions["SCORE"] == "PICK"
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
    assert score_market["scores"]
    assert card["bookmaker_intent"]["intent"] in {"HOME_LEAN", "AWAY_LEAN"}


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
                        "fixture_id": "1489410",
                        "canonical_market": "ASIAN_HANDICAP",
                        "selection": selection,
                        "line": line,
                        "decimal_odds": price,
                        "bookmaker_id": bookmaker_id,
                        "bookmaker_name": bookmaker_name,
                        "provider_last_update": captured.isoformat().replace("+00:00", "Z"),
                        "captured_at": captured.isoformat().replace("+00:00", "Z"),
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
                        "fixture_id": "1489410",
                        "canonical_market": "TOTALS",
                        "selection": selection,
                        "line": line,
                        "decimal_odds": price,
                        "bookmaker_id": bookmaker_id,
                        "bookmaker_name": bookmaker_name,
                        "provider_last_update": captured.isoformat().replace("+00:00", "Z"),
                        "captured_at": captured.isoformat().replace("+00:00", "Z"),
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
    assert card["current_odds"]["ou"]["line"] == "3.5"
    assert card["current_odds"]["ou"]["over_price"] == 1.91
    assert card["current_odds"]["ou"]["under_price"] == 1.93
    ah_market = next(market for market in card["markets"] if market["market"] == "ASIAN_HANDICAP")
    totals_market = next(market for market in card["markets"] if market["market"] == "TOTALS")
    assert ah_market["balanced_line"] == "1.5"
    assert ah_market["line"] in {"-1.5", "1.5"}
    assert totals_market["line"] == "3.5"
    assert ah_market["line_status"] == "READY"
    assert totals_market["line_status"] == "READY"


class FakeReadRepositoryWithHighWaterAlternateTotals(FakeReadRepository):
    def future_market_observations(self) -> list[dict[str, Any]]:
        rows = super().future_market_observations()
        captured = NOW - timedelta(minutes=20)
        rows = [row for row in rows if row.get("canonical_market") != "TOTALS"]
        for bookmaker_id, bookmaker_name in (
            ("1", "Pinnacle"),
            ("2", "SoftBook"),
            ("3", "SBO"),
        ):
            for selection, line, price in (
                ("Over 1.5", "1.5", "2.21"),
                ("Under 1.5", "1.5", "2.15"),
                ("Over 2.0", "2.0", "2.05"),
                ("Under 2.0", "2.0", "2.15"),
                ("Over 2.5", "2.5", "4.10"),
                ("Under 2.5", "2.5", "1.87"),
            ):
                rows.append(
                    {
                        "fixture_id": "1489410",
                        "canonical_market": "TOTALS",
                        "selection": selection,
                        "line": line,
                        "decimal_odds": price,
                        "bookmaker_id": bookmaker_id,
                        "bookmaker_name": bookmaker_name,
                        "provider_last_update": captured.isoformat().replace("+00:00", "Z"),
                        "captured_at": captured.isoformat().replace("+00:00", "Z"),
                        "suspended": False,
                        "live": False,
                    }
                )
        return rows


def test_analysis_card_prefers_main_total_over_high_water_alternate_line(monkeypatch) -> None:
    monkeypatch.setattr(api_repository, "future_refresh_db_repository", lambda: FakeDbRepository())
    service = ReadModelService(
        repository=cast(Any, FakeReadRepositoryWithHighWaterAlternateTotals())
    )

    card = service.analysis_card("1489410")

    assert card is not None
    assert card["current_odds"]["ou"] == {
        "line": "2",
        "over_price": 2.05,
        "under_price": 2.15,
        "over_line": "2",
        "under_line": "2",
        "price": 2.1,
    }
    totals_market = next(market for market in card["markets"] if market["market"] == "TOTALS")
    assert totals_market["line"] == "2"
    assert totals_market["balanced_line"] == "2"
    assert totals_market["line_status"] == "READY"


class FakeReadRepositoryOnlyExtremeLines(FakeReadRepository):
    def future_market_observations(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for captured in (NOW - timedelta(hours=3), NOW - timedelta(hours=1)):
            for bookmaker_id, bookmaker_name in (("1", "Pinnacle"), ("2", "SoftBook")):
                rows.append(
                    {
                        "fixture_id": "1489410",
                        "canonical_market": "ASIAN_HANDICAP",
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
