from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from w2.api.repository import ReadModelService
from w2.strategy.simulate import SimulationInputs, run_simulation


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
    assert card["analysis_readiness"]["status"] in {"PARTIAL", "BLOCKED"}
    assert "FIXTURE_NOT_UPCOMING" in card["analysis_readiness"]["blockers"]


class ReadinessRepository:
    def __init__(
        self,
        *,
        analysis_card: dict[str, Any],
        market_observations: list[dict[str, Any]] | None = None,
    ) -> None:
        self.analysis_card = analysis_card
        self.market_observations = market_observations or []

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
        return self.market_observations

    def dashboard_fixture(self, fixture_id: str) -> dict[str, Any] | None:
        return None

    def matchday_cards(self) -> list[dict[str, Any]]:
        return [
            {
                "fixture": {
                    "fixture_id": "future-partial",
                    "competition_id": "1",
                    "competition_name": "World Cup",
                    "kickoff_utc": "2026-06-26T10:00:00Z",
                    "status": "NS",
                    "home_team_id": "10",
                    "home_team_name": "Home",
                    "away_team_id": "20",
                    "away_team_name": "Away",
                },
                "card": {"action": "DATA"},
                "temporal": {},
                "analysis_card": self.analysis_card,
            }
        ]


def formal_ready_simulation_payload() -> dict[str, Any]:
    return run_simulation(
        SimulationInputs(
            fixture_id="future-partial",
            home_team_id="10",
            away_team_id="20",
            home_xg_for=2.2,
            home_xg_against=0.6,
            away_xg_for=0.7,
            away_xg_against=1.8,
            home_elo=1750.0,
            away_elo=1350.0,
            home_squad_value_eur=900_000_000.0,
            away_squad_value_eur=80_000_000.0,
        )
    ).as_dict()


def test_dashboard_exposes_blocked_analysis_readiness_for_missing_inputs() -> None:
    service = ReadModelService(
        repository=cast(
            Any,
            ReadinessRepository(
                analysis_card={
                    "decision": "SKIP",
                    "candidate": False,
                    "formal_recommendation": False,
                    "source": "future_refresh_without_analysis_payload",
                    "data_readiness": {
                        "bookmakers": 0,
                        "odds_snapshots": 0,
                        "xg": False,
                    },
                    "markets": [
                        {
                            "market": "TOTALS",
                            "decision": "SKIP",
                            "reasons": ["OU_MARKET_UNAVAILABLE"],
                        },
                        {
                            "market": "SCORE",
                            "decision": "SKIP",
                            "reasons": ["SCORE_MATRIX_UNAVAILABLE"],
                        },
                    ],
                },
            ),
        )
    )

    payload = service.dashboard(target_date="2026-06-26", window="today")
    card = payload["all"][0]

    assert card["recommendation"] is None
    assert card["analysis_readiness"]["status"] == "BLOCKED"
    assert "MISSING_ANALYSIS_CARD" in card["analysis_readiness"]["blockers"]
    assert "MISSING_MARKET_OBSERVATIONS" in card["analysis_readiness"]["blockers"]
    assert "MISSING_XG" in card["analysis_readiness"]["blockers"]
    assert "SCORE_MARKET_UNAVAILABLE" in card["analysis_readiness"]["blockers"]
    assert payload["performance"]["analysis_blocked_count"] == 1


def test_dashboard_emits_watch_for_partially_ready_non_pick_without_candidate_flags() -> None:
    service = ReadModelService(
        repository=cast(
            Any,
            ReadinessRepository(
                analysis_card={
                    "decision": "SKIP",
                    "candidate": False,
                    "formal_recommendation": False,
                    "source": "db_feature_materialized_analysis",
                    "data_readiness": {
                        "market_observations": 8,
                        "bookmakers": 4,
                        "odds_snapshots": 2,
                        "xg": False,
                    },
                    "current_odds": {"ou": {"line": "2.5", "price": 1.9}},
                    "markets": [
                        {"market": "TOTALS", "decision": "SKIP", "reasons": ["CONFLICTED"]},
                        {
                            "market": "SCORE",
                            "decision": "SKIP",
                            "reasons": ["SCORE_MATRIX_UNAVAILABLE"],
                        },
                    ],
                },
            ),
        )
    )

    payload = service.dashboard(target_date="2026-06-26", window="today")
    card = payload["all"][0]

    assert card["analysis_readiness"]["status"] == "PARTIAL"
    assert card["recommendation"]["tier"] == "WATCH"
    assert card["recommendation"]["candidate"] is False
    assert card["recommendation"]["formal_recommendation"] is False
    assert card["candidate"] is False
    assert card["formal_recommendation"] is False
    assert payload["performance"]["watch_count"] == 1
    assert payload["performance"]["analysis_partial_count"] == 1


def test_dashboard_card_exposes_data_refresh_status_without_promoting_flags() -> None:
    service = ReadModelService(
        repository=cast(
            Any,
            ReadinessRepository(
                analysis_card={
                    "decision": "SKIP",
                    "candidate": False,
                    "formal_recommendation": False,
                    "source": "db_feature_materialized_analysis",
                    "data_readiness": {
                        "market_observations": 8,
                        "bookmakers": 4,
                        "odds_snapshots": 2,
                        "xg": False,
                        "xg_status": "INSUFFICIENT_HISTORY",
                        "lineups": True,
                        "lineups_status": "READY",
                        "statistics_status": "PROVIDER_EMPTY",
                    },
                    "current_odds": {"ah": {"line": "-0.25", "price": 1.9}},
                    "markets": [
                        {"market": "ASIAN_HANDICAP", "decision": "SKIP", "reasons": ["CONFLICTED"]},
                    ],
                },
            ),
        )
    )

    payload = service.dashboard(target_date="2026-06-26", window="today")
    card = payload["all"][0]

    assert card["data_refresh"]["provider"] == "api_football"
    assert card["data_refresh"]["status"] == "PROVIDER_EMPTY"
    assert card["data_refresh"]["odds_status"] == "READY"
    assert card["data_refresh"]["lineups_status"] == "READY"
    assert card["data_refresh"]["lineups_status_label"] == "首发已出"
    assert card["data_refresh"]["xg_status"] == "INSUFFICIENT_HISTORY"
    assert card["data_refresh"]["xg_status_label"] == "xG 样本不足"
    assert card["data_refresh"]["status_label"] == "provider 未返回"
    assert card["candidate"] is False
    assert card["formal_recommendation"] is False


def test_dashboard_exposes_market_movement_without_promoting_flags(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.setenv("W2_MARKET_TIMELINE_RUNTIME_ROOT", str(tmp_path))
    (tmp_path / "future-partial.json").write_text(
        json.dumps(
            {
                "schema_version": "w2.market_timeline.v1",
                "fixture_id": "future-partial",
                "kickoff_utc": "2026-06-26T10:00:00Z",
                "snapshots": [
                    {
                        "schema_version": "w2.market_timeline.v1",
                        "fixture_id": "future-partial",
                        "checkpoint": "opening",
                        "market": "ASIAN_HANDICAP",
                        "as_of": "2026-06-26T08:00:00Z",
                        "kickoff_utc": "2026-06-26T10:00:00Z",
                        "line": -0.5,
                        "home_price": 1.92,
                        "away_price": 1.88,
                        "bookmaker_count": 4,
                        "immutable": True,
                        "source_hash": "opening",
                    },
                    {
                        "schema_version": "w2.market_timeline.v1",
                        "fixture_id": "future-partial",
                        "checkpoint": "lock",
                        "market": "ASIAN_HANDICAP",
                        "as_of": "2026-06-26T09:30:00Z",
                        "kickoff_utc": "2026-06-26T10:00:00Z",
                        "line": -1.0,
                        "home_price": 1.86,
                        "away_price": 1.94,
                        "bookmaker_count": 4,
                        "immutable": True,
                        "source_hash": "lock",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    service = ReadModelService(
        repository=cast(
            Any,
            ReadinessRepository(
                analysis_card={
                    "fixture_id": "future-partial",
                    "decision": "SKIP",
                    "candidate": False,
                    "formal_recommendation": False,
                    "source": "db_feature_materialized_analysis",
                    "data_readiness": {
                        "market_observations": 8,
                        "bookmakers": 4,
                        "odds_snapshots": 2,
                        "xg": False,
                    },
                    "feature_contributions": [
                        {
                            "id": "F3_REST_FITNESS",
                            "side": "HOME",
                            "weight": 0.2,
                            "score": 0.6,
                            "status": "READY",
                            "source_group": "team_fixture_history",
                        },
                        {
                            "id": "F7_STRENGTH_FORM",
                            "side": "HOME",
                            "weight": 0.2,
                            "score": 0.7,
                            "status": "READY",
                            "source_group": "ratings",
                        },
                        {
                            "id": "F8_SQUAD_VALUE",
                            "side": "HOME",
                            "weight": 0.2,
                            "score": 0.7,
                            "status": "READY",
                            "source_group": "squad_value",
                        },
                    ],
                    "current_odds": {"ah": {"line": "-1.0", "price": 1.86}},
                    "markets": [{"market": "ASIAN_HANDICAP", "decision": "SKIP"}],
                },
            ),
        )
    )

    card = service.dashboard(target_date="2026-06-26", window="today")["all"][0]

    assert card["market_movement"]["status"] == "READY"
    assert card["market_movement"]["line_move_direction"] == "HOME_DEEPENED"
    assert card["market_divergence"]["direction_allowed"] is False
    assert card["market_divergence"]["calibration_status"] == "UNVALIDATED"
    assert card["bookmaker_hypothesis"]["label"] == "盘口假设 · 未验证"
    assert card["bookmaker_hypothesis"]["verified"] is False
    assert card["candidate"] is False
    assert card["formal_recommendation"] is False
    assert card["pricing_shadow"]["beats_market"] is False


def test_dashboard_formal_uses_timeline_ah_prices_as_canonical_market(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.setenv("W2_MARKET_TIMELINE_RUNTIME_ROOT", str(tmp_path))
    (tmp_path / "future-partial.json").write_text(
        json.dumps(
            {
                "schema_version": "w2.market_timeline.v1",
                "fixture_id": "future-partial",
                "kickoff_utc": "2026-06-26T10:00:00Z",
                "snapshots": [
                    {
                        "schema_version": "w2.market_timeline.v1",
                        "fixture_id": "future-partial",
                        "checkpoint": "opening",
                        "market": "ASIAN_HANDICAP",
                        "as_of": "2026-06-26T08:00:00Z",
                        "kickoff_utc": "2026-06-26T10:00:00Z",
                        "line": -1.0,
                        "home_price": 1.95,
                        "away_price": 1.95,
                        "bookmaker_count": 4,
                        "selection_policy": "latest_bucket_ladder_balance_same_bookmaker_pair",
                        "candidate_lines": [
                            {"line": -1.0, "bookmaker_count": 4, "selection_rank": 1}
                        ],
                        "rejected_lines": [{"line": -0.5, "reason": "LOWER_BOOKMAKER_CONSENSUS"}],
                        "immutable": True,
                        "source_hash": "opening",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    service = ReadModelService(
        repository=cast(
            Any,
            ReadinessRepository(
                analysis_card={
                    "fixture_id": "future-partial",
                    "decision": "SKIP",
                    "candidate": False,
                    "formal_recommendation": False,
                    "source": "db_feature_materialized_analysis",
                    "data_readiness": {
                        "market_observations": 8,
                        "bookmakers": 4,
                        "odds_snapshots": 2,
                        "xg": True,
                    },
                    "feature_contributions": [
                        {
                            "id": "F3_REST_FITNESS",
                            "side": "HOME",
                            "weight": 0.2,
                            "score": 0.6,
                            "status": "READY",
                            "source_group": "team_fixture_history",
                        },
                        {
                            "id": "F7_STRENGTH_FORM",
                            "side": "HOME",
                            "weight": 0.2,
                            "score": 0.7,
                            "status": "READY",
                            "source_group": "ratings",
                        },
                        {
                            "id": "F8_SQUAD_VALUE",
                            "side": "HOME",
                            "weight": 0.2,
                            "score": 0.7,
                            "status": "READY",
                            "source_group": "squad_value",
                        },
                    ],
                    "current_odds": {"ou": {"line": "2.5", "price": 1.9}},
                    "simulation": formal_ready_simulation_payload(),
                    "markets": [{"market": "ASIAN_HANDICAP", "decision": "SKIP"}],
                },
            ),
        )
    )

    card = service.dashboard(target_date="2026-06-26", window="today")["all"][0]

    assert card["current_odds"]["ah"]["home_line"] == "-1"
    assert card["current_odds"]["ah"]["away_line"] == "1"
    assert card["current_odds"]["ah"]["home_price"] == 1.95
    assert card["current_odds"]["ah"]["away_price"] == 1.95
    assert (
        card["current_odds"]["ah"]["selection_policy"]
        == "latest_bucket_ladder_balance_same_bookmaker_pair"
    )
    assert card["current_odds"]["ah"]["candidate_lines"][0]["line"] == -1.0
    assert card["current_odds"]["ah"]["rejected_lines"][0]["line"] == -0.5
    assert card["pricing_shadow"]["market_ah"] == -1.0
    assert card["pricing_shadow"]["canonical_ah_market_validation_status"] == "READY"
    assert card["pricing_shadow"]["canonical_ah_market_blocker"] is None
    assert card["pricing_shadow"]["canonical_ah_market"]["home_line"] == -1.0
    assert card["pricing_shadow"]["canonical_ah_market"]["away_line"] == 1.0
    assert "MISSING_AH_MARKET" not in card["pricing_shadow"]["formal_blockers"]


def test_read_model_mainline_prefers_ladder_balance_center() -> None:
    captured = "2026-06-26T08:00:00Z"
    observations: list[dict[str, Any]] = []
    for line, home_price, away_price in [
        ("0", "1.66", "2.26"),
        ("-0.25", "1.93", "1.95"),
        ("-0.5", "2.35", "1.61"),
    ]:
        for bookmaker in ("bm1", "bm2"):
            observations.extend(
                [
                    {
                        "fixture_id": "future-partial",
                        "canonical_market": "ASIAN_HANDICAP",
                        "selection": "Home",
                        "line": line,
                        "decimal_odds": home_price,
                        "captured_at": captured,
                        "provider_last_update": captured,
                        "bookmaker_id": bookmaker,
                        "bookmaker_name": bookmaker,
                        "suspended": False,
                        "live": False,
                    },
                    {
                        "fixture_id": "future-partial",
                        "canonical_market": "ASIAN_HANDICAP",
                        "selection": "Away",
                        "line": str(-float(line)),
                        "decimal_odds": away_price,
                        "captured_at": captured,
                        "provider_last_update": captured,
                        "bookmaker_id": bookmaker,
                        "bookmaker_name": bookmaker,
                        "suspended": False,
                        "live": False,
                    },
                ]
            )
    service = ReadModelService(repository=cast(Any, RecommendationLoopRepository()))

    selected = service._select_mainline_observations(observations, market="ASIAN_HANDICAP")

    assert selected["status"] == "READY"
    assert selected["side_lines"]["home"] == "-0.25"
    assert selected["side_lines"]["away"] == "0.25"
    assert selected["side_prices"]["home"] == 1.93
    assert selected["side_prices"]["away"] == 1.95


def test_read_model_mainline_rejects_cross_bookmaker_ah_pairing() -> None:
    captured = "2026-06-26T08:00:00Z"
    observations = [
        {
            "fixture_id": "future-partial",
            "canonical_market": "ASIAN_HANDICAP",
            "selection": "Home",
            "line": "-1",
            "decimal_odds": "1.91",
            "captured_at": captured,
            "provider_last_update": captured,
            "bookmaker_id": "home-only",
            "bookmaker_name": "home-only",
            "suspended": False,
            "live": False,
        },
        {
            "fixture_id": "future-partial",
            "canonical_market": "ASIAN_HANDICAP",
            "selection": "Away",
            "line": "1",
            "decimal_odds": "1.97",
            "captured_at": captured,
            "provider_last_update": captured,
            "bookmaker_id": "away-only",
            "bookmaker_name": "away-only",
            "suspended": False,
            "live": False,
        },
    ]
    service = ReadModelService(repository=cast(Any, RecommendationLoopRepository()))

    selected = service._select_mainline_observations(observations, market="ASIAN_HANDICAP")

    assert selected["status"] == "UNAVAILABLE"
    assert selected["bookmaker_count"] == 0


def test_dashboard_ignores_invalid_timeline_ah_price_pair(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.setenv("W2_MARKET_TIMELINE_RUNTIME_ROOT", str(tmp_path))
    (tmp_path / "future-partial.json").write_text(
        json.dumps(
            {
                "schema_version": "w2.market_timeline.v1",
                "fixture_id": "future-partial",
                "kickoff_utc": "2026-06-26T10:00:00Z",
                "snapshots": [
                    {
                        "schema_version": "w2.market_timeline.v1",
                        "fixture_id": "future-partial",
                        "checkpoint": "opening",
                        "market": "ASIAN_HANDICAP",
                        "as_of": "2026-06-26T08:00:00Z",
                        "kickoff_utc": "2026-06-26T10:00:00Z",
                        "line": -1.0,
                        "home_price": 5.55,
                        "away_price": 11.5,
                        "bookmaker_count": 2,
                        "immutable": True,
                        "source_hash": "bad-composite",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    service = ReadModelService(
        repository=cast(
            Any,
            ReadinessRepository(
                analysis_card={
                    "fixture_id": "future-partial",
                    "decision": "SKIP",
                    "candidate": False,
                    "formal_recommendation": False,
                    "source": "db_feature_materialized_analysis",
                    "data_readiness": {
                        "market_observations": 8,
                        "bookmakers": 4,
                        "odds_snapshots": 2,
                        "xg": True,
                    },
                    "feature_contributions": [
                        {
                            "id": "F3_REST_FITNESS",
                            "side": "HOME",
                            "weight": 0.2,
                            "score": 0.6,
                            "status": "READY",
                            "source_group": "team_fixture_history",
                        },
                        {
                            "id": "F7_STRENGTH_FORM",
                            "side": "HOME",
                            "weight": 0.2,
                            "score": 0.7,
                            "status": "READY",
                            "source_group": "ratings",
                        },
                        {
                            "id": "F8_SQUAD_VALUE",
                            "side": "HOME",
                            "weight": 0.2,
                            "score": 0.7,
                            "status": "READY",
                            "source_group": "squad_value",
                        },
                    ],
                    "current_odds": {
                        "ah": {
                            "home_line": "-0.5",
                            "away_line": "0.5",
                            "home_price": 1.94,
                            "away_price": 1.96,
                            "source": "read_model_mainline",
                        }
                    },
                    "simulation": formal_ready_simulation_payload(),
                    "markets": [{"market": "ASIAN_HANDICAP", "decision": "SKIP"}],
                },
            ),
        )
    )

    card = service.dashboard(target_date="2026-06-26", window="today")["all"][0]

    assert card["current_odds"]["ah"]["home_line"] == "-0.5"
    assert card["current_odds"]["ah"]["away_line"] == "0.5"
    assert card["current_odds"]["ah"]["home_price"] == 1.94
    assert card["current_odds"]["ah"]["away_price"] == 1.96
    assert card["current_odds"]["ah"]["source"] == "read_model_mainline"
    assert card["pricing_shadow"]["canonical_ah_market_validation_status"] == "READY"
    assert card["pricing_shadow"]["canonical_ah_market_blocker"] is None


def test_dashboard_scoreline_picks_prefer_formal_simulation_source() -> None:
    service = ReadModelService(
        repository=cast(
            Any,
            ReadinessRepository(
                analysis_card={
                    "fixture_id": "future-partial",
                    "decision": "SKIP",
                    "candidate": False,
                    "formal_recommendation": False,
                    "source": "db_feature_materialized_analysis",
                    "data_readiness": {
                        "market_observations": 8,
                        "bookmakers": 4,
                        "odds_snapshots": 2,
                        "xg": True,
                    },
                    "current_odds": {
                        "ah": {"home_line": "-1", "home_price": 1.95, "away_price": 1.95}
                    },
                    "simulation": formal_ready_simulation_payload(),
                    "markets": [
                        {
                            "market": "SCORE",
                            "decision": "ANALYSIS_PICK",
                            "reference_scores": [
                                {"scoreline": "4-4", "probability": 0.99},
                            ],
                        }
                    ],
                },
            ),
        )
    )

    card = service.dashboard(target_date="2026-06-26", window="today")["all"][0]

    assert card["scoreline_readiness"]["source"] == "formal_simulation"
    assert card["scoreline_picks"] == card["pricing_shadow"]["simulation"]["scoreline_picks"][:3]
    assert card["scoreline_picks"][0]["scoreline"] != "4-4"


def test_validation_summary_reports_sample_insufficiency_without_fake_hit_rate() -> None:
    service = ReadModelService(
        repository=cast(
            Any,
            ReadinessRepository(
                analysis_card={
                    "decision": "SKIP",
                    "candidate": False,
                    "formal_recommendation": False,
                    "source": "future_refresh_without_analysis_payload",
                    "data_readiness": {
                        "bookmakers": 0,
                        "odds_snapshots": 0,
                        "xg": False,
                        "lineups_status": "NOT_REQUESTED",
                        "xg_status": "MAPPING_MISSING",
                    },
                    "markets": [{"market": "TOTALS", "decision": "SKIP"}],
                },
            ),
        )
    )

    payload = service.validation_summary(target_date="2026-06-26", window="today")

    assert payload["validation"]["beats_market"] is False
    assert payload["validation"]["formal_enabled"] is False
    assert payload["validation"]["candidate_enabled"] is False
    assert payload["validation"]["policy"]["sample_minimum"] == 200
    assert payload["validation"]["official"]["sample_size"] == 0
    assert payload["validation"]["official"]["hit_rate"] is None
    assert payload["validation"]["official"]["label"] == "official 样本不足，暂不计算命中率"
    assert payload["validation"]["analysis_shadow"]["sample_size"] == 0
    assert payload["validation"]["analysis_shadow"]["hit_rate"] is None
    assert (
        payload["validation"]["analysis_shadow"]["label"]
        == "analysis_shadow 样本不足，暂不计算命中率"
    )


def test_data_refresh_labels_explain_not_requested_and_xg_mapping_missing() -> None:
    service = ReadModelService(
        repository=cast(
            Any,
            ReadinessRepository(
                analysis_card={
                    "decision": "SKIP",
                    "candidate": False,
                    "formal_recommendation": False,
                    "source": "db_feature_materialized_analysis",
                    "data_readiness": {
                        "market_observations": 1,
                        "bookmakers": 1,
                        "odds_snapshots": 1,
                        "xg": False,
                        "xg_status": "MAPPING_MISSING",
                        "lineups": False,
                        "lineups_status": "NOT_REQUESTED",
                        "statistics_status": "MAPPING_MISSING",
                    },
                    "current_odds": {"ah": {"line": "0", "price": 1.9}},
                    "markets": [{"market": "ASIAN_HANDICAP", "decision": "SKIP"}],
                },
            ),
        )
    )

    card = service.dashboard(target_date="2026-06-26", window="today")["all"][0]

    assert card["data_refresh"]["lineups_status_label"] == "未到首发请求时点"
    assert card["data_refresh"]["xg_status_label"] == "xG 映射缺失"
