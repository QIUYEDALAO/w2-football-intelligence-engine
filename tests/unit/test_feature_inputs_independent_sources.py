from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from w2.api import repository as api_repository
from w2.api.repository import ReadModelService


def api_fixture(
    fixture_id: str,
    *,
    date: str,
    home_id: str,
    away_id: str,
    home_goals: int,
    away_goals: int,
    status: str = "FT",
    ah_result: str | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "fixture": {"id": fixture_id, "date": date, "status": {"short": status}},
        "league": {"id": 1, "name": "World Cup"},
        "teams": {
            "home": {"id": int(home_id), "name": f"Team {home_id}"},
            "away": {"id": int(away_id), "name": f"Team {away_id}"},
        },
        "goals": {"home": home_goals, "away": away_goals},
    }
    if ah_result is not None:
        row["ah_result"] = ah_result
        row["settlement_outcome"] = "WIN" if ah_result == "COVER" else "LOSS"
        row["ah_fact_id"] = f"canonical-ah:{fixture_id}"
        row["ah_fact_hash"] = f"{fixture_id}".encode().hex().ljust(64, "0")[:64]
        row["quote_identity_hash"] = f"quote-{fixture_id}".encode().hex().ljust(64, "0")[:64]
        row["result_identity_hash"] = f"result-{fixture_id}".encode().hex().ljust(64, "0")[
            :64
        ]
    return row


class IndependentSourceRepository:
    def matchday_cards(self) -> list[dict[str, Any]]:
        return []

    def dashboard_fixture(self, fixture_id: str) -> dict[str, Any] | None:
        return None

    def fixture_payloads(self) -> list[dict[str, Any]]:
        return [
            {
                "fixture": {
                    "id": "future-1",
                    "date": "2026-07-10T18:00:00Z",
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
        captured = "2026-07-01T12:00:00Z"
        return [
            {
                "fixture_id": "future-1",
                "canonical_market": "ASIAN_HANDICAP",
                "selection": "Home",
                "line": "0",
                "decimal_odds": "1.91",
                "captured_at": captured,
                "provider_last_update": captured,
                "bookmaker_id": "bm1",
                "bookmaker_name": "Book",
                "suspended": False,
                "live": False,
            },
            {
                "fixture_id": "future-1",
                "canonical_market": "ASIAN_HANDICAP",
                "selection": "Away",
                "line": "0",
                "decimal_odds": "1.91",
                "captured_at": captured,
                "provider_last_update": captured,
                "bookmaker_id": "bm1",
                "bookmaker_name": "Book",
                "suspended": False,
                "live": False,
            },
        ]


class IndependentSourceStore:
    def __init__(self, *, include_ah: bool = True, h2h_empty: bool = False) -> None:
        self.include_ah = include_ah
        self.h2h_empty = h2h_empty

    def team_xg_rolling_snapshots(self, *, fixture_id: str | None = None) -> list[dict[str, Any]]:
        assert fixture_id == "future-1"
        return [
            {
                "team_id": "10",
                "as_of_time": "2026-07-01T12:00:00Z",
                "rolling_xg_for": 1.8,
                "rolling_xg_against": 0.7,
                "rolling_goals_for": 2.0,
                "rolling_goals_against": 1.0,
            },
            {
                "team_id": "20",
                "as_of_time": "2026-07-01T12:00:00Z",
                "rolling_xg_for": 0.7,
                "rolling_xg_against": 1.8,
                "rolling_goals_for": 1.0,
                "rolling_goals_against": 2.0,
            },
        ]

    def team_xg_matches(self) -> list[dict[str, Any]]:
        return []

    def raw_payloads(self, endpoint: str) -> list[dict[str, Any]]:
        if endpoint == "fixtures":
            ah_cover = "COVER" if self.include_ah else None
            ah_loss = "NO_COVER" if self.include_ah else None
            return [
                {
                    "payload": {
                        "response": [
                            api_fixture(
                                "h10-1",
                                date="2026-06-20T18:00:00Z",
                                home_id="10",
                                away_id="30",
                                home_goals=4,
                                away_goals=0,
                                ah_result=ah_cover,
                            ),
                            api_fixture(
                                "h10-2",
                                date="2026-06-25T18:00:00Z",
                                home_id="40",
                                away_id="10",
                                home_goals=0,
                                away_goals=2,
                                ah_result=ah_cover,
                            ),
                            api_fixture(
                                "h20-1",
                                date="2026-06-19T18:00:00Z",
                                home_id="20",
                                away_id="50",
                                home_goals=0,
                                away_goals=2,
                                ah_result=ah_loss,
                            ),
                            api_fixture(
                                "h20-2",
                                date="2026-06-24T18:00:00Z",
                                home_id="60",
                                away_id="20",
                                home_goals=3,
                                away_goals=0,
                                ah_result=ah_loss,
                            ),
                            api_fixture(
                                "future-leak",
                                date="2026-08-01T18:00:00Z",
                                home_id="10",
                                away_id="20",
                                home_goals=9,
                                away_goals=0,
                            ),
                        ]
                    }
                }
            ]
        if endpoint == "h2h":
            return [
                {
                    "payload": {
                        "response": []
                        if self.h2h_empty
                        else [
                            api_fixture(
                                "h2h-1",
                                date="2026-06-01T18:00:00Z",
                                home_id="10",
                                away_id="20",
                                home_goals=3,
                                away_goals=0,
                            )
                        ]
                    }
                }
            ]
        return []


def write_value_mapping(root: Path) -> None:
    path = root / "config/team_values/world_cup_2026.v1.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "team_id": "10",
                        "observed_at": "2026-06-20T00:00:00Z",
                        "squad_value_eur": 900000000,
                        "source_system": "reviewed_static_test_mapping",
                        "confidence": 1.0,
                    },
                    {
                        "team_id": "20",
                        "observed_at": "2026-06-20T00:00:00Z",
                        "squad_value_eur": 120000000,
                        "source_system": "reviewed_static_test_mapping",
                        "confidence": 1.0,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )


def write_rating_mapping(
    root: Path,
    *,
    observed_at: str = "2026-07-01T00:00:00Z",
) -> None:
    path = root / "config/team_ratings/world_cup_2026.v1.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "version": "world_cup_2026.real_elo.test",
                "source_system": "world_football_elo",
                "source_url": "https://www.eloratings.net/World.tsv",
                "items": [
                    {
                        "team_id": "10",
                        "team_name": "Strong",
                        "elo": 2010,
                        "observed_at": observed_at,
                        "source_system": "world_football_elo",
                        "source_url": "https://www.eloratings.net/World.tsv",
                        "confidence": 0.95,
                        "reviewed_by": "liudehua",
                    },
                    {
                        "team_id": "20",
                        "team_name": "Weak",
                        "elo": 1610,
                        "observed_at": observed_at,
                        "source_system": "world_football_elo",
                        "source_url": "https://www.eloratings.net/World.tsv",
                        "confidence": 0.95,
                        "reviewed_by": "liudehua",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )


def test_real_history_h2h_values_and_ratings_drive_isc(monkeypatch: Any, tmp_path: Path) -> None:
    write_value_mapping(tmp_path)
    monkeypatch.setattr(api_repository, "ROOT", tmp_path)
    monkeypatch.setattr(
        api_repository,
        "future_refresh_db_repository",
        lambda: IndependentSourceStore(),
    )
    service = ReadModelService(repository=cast(Any, IndependentSourceRepository()))

    card = service.analysis_card("future-1")

    assert card is not None
    factors = {item["id"]: item for item in card["pricing_shadow"]["factors"]}
    assert factors["F3_REST_FITNESS"]["source_group"] == "team_fixture_history"
    assert factors["F3_REST_FITNESS"]["is_independent_signal"] is True
    assert factors["F3_REST_FITNESS"]["inputs"]["home_rest_days"] > 0
    assert factors["F5_RECENT_AH_COVER"]["status"] == "READY"
    assert factors["F6_H2H"]["source_group"] == "h2h"
    assert factors["F7_STRENGTH_FORM"]["source_group"] == "ratings"
    assert factors["F8_SQUAD_VALUE"]["source_group"] == "squad_value"
    assert factors["F9_TRUE_XG"]["source_group"] == "xg"
    assert card["pricing_shadow"]["independent_signal_count"] >= 3
    assert (
        card["pricing_shadow"]["team_score"]["home"]
        > card["pricing_shadow"]["team_score"]["away"]
    )
    assert card["pricing_shadow"]["fair_ah"] < 0
    assert card["pricing_shadow"]["beats_market"] is False
    assert card["formal_recommendation"] is False
    assert card["candidate"] is False


def test_static_real_elo_overrides_history_rating_and_enters_lambda(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    write_value_mapping(tmp_path)
    write_rating_mapping(tmp_path)
    monkeypatch.setattr(api_repository, "ROOT", tmp_path)
    monkeypatch.setattr(
        api_repository,
        "future_refresh_db_repository",
        lambda: IndependentSourceStore(),
    )
    service = ReadModelService(repository=cast(Any, IndependentSourceRepository()))

    card = service.analysis_card("future-1")

    assert card is not None
    factors = {item["id"]: item for item in card["pricing_shadow"]["factors"]}
    strength = factors["F7_STRENGTH_FORM"]
    assert strength["source"] == "world_football_elo"
    assert strength["source_group"] == "ratings"
    assert strength["collection_status"] == "REAL_ELO"
    assert strength["is_independent_signal"] is True
    assert strength["inputs"]["home_elo"] == 2010.0
    assert strength["inputs"]["away_elo"] == 1610.0
    readiness = card["pricing_shadow"]["simulation"]["input_readiness"]
    assert readiness["home_elo_source"] == "world_football_elo"
    assert readiness["away_elo_source"] == "world_football_elo"
    assert readiness["home_elo_collection_status"] == "REAL_ELO"
    assert readiness["away_elo_collection_status"] == "REAL_ELO"
    assert readiness["ratings_used_in_lambda"] is True
    assert readiness["proxy_elo_excluded"] is False
    assert "ratings" in card["pricing_shadow"]["independent_signal_groups"]


def test_static_real_elo_after_as_of_is_not_used(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    write_value_mapping(tmp_path)
    write_rating_mapping(tmp_path, observed_at="2026-08-01T00:00:00Z")
    monkeypatch.setattr(api_repository, "ROOT", tmp_path)
    monkeypatch.setattr(
        api_repository,
        "future_refresh_db_repository",
        lambda: IndependentSourceStore(),
    )
    service = ReadModelService(repository=cast(Any, IndependentSourceRepository()))

    card = service.analysis_card("future-1")

    assert card is not None
    factors = {item["id"]: item for item in card["pricing_shadow"]["factors"]}
    strength = factors["F7_STRENGTH_FORM"]
    assert strength["source"] != "world_football_elo"
    assert strength["collection_status"] != "REAL_ELO"
    assert strength["inputs"]["home_elo"] != 2010.0


def test_missing_ah_and_h2h_are_reported_without_fake_ready(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(api_repository, "ROOT", tmp_path)
    monkeypatch.setattr(
        api_repository,
        "future_refresh_db_repository",
        lambda: IndependentSourceStore(include_ah=False, h2h_empty=True),
    )
    service = ReadModelService(repository=cast(Any, IndependentSourceRepository()))

    card = service.analysis_card("future-1")

    assert card is not None
    summary = card["pricing_shadow"]["factor_source_summary"]
    assert summary["F5_RECENT_AH_COVER"]["collection_status"] == "MISSING_AH_EVIDENCE"
    assert summary["F6_H2H"]["collection_status"] == "NO_H2H_HISTORY"
    assert "h2h" in card["pricing_shadow"]["missing_independent_sources"]
    assert "squad_value" in card["pricing_shadow"]["missing_independent_sources"]
