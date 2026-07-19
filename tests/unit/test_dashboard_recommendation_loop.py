from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, cast

from w2.api.repository import ReadModelService
from w2.api.schemas import DashboardResponse
from w2.strategy.formal_recommendation import ah_display_contract
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


class FootballDayResultsRepository(RecommendationLoopRepository):
    def release_counts(self) -> dict[str, int]:
        return {
            "read_model_fixture_count": 4,
            "matchday_card_count": 4,
            "future_fixture_count": 0,
            "result_event_count": 4,
        }

    def matchday_cards(self) -> list[dict[str, Any]]:
        return [
            self._card("previous-football-day", "2026-06-30T03:59:00Z"),
            self._card("football-day-start", "2026-06-30T04:00:00Z"),
            self._card("football-day-morning", "2026-07-01T03:30:00Z"),
            self._card("next-football-day", "2026-07-01T04:00:00Z"),
        ]

    @staticmethod
    def _card(fixture_id: str, kickoff_utc: str) -> dict[str, Any]:
        return {
            "fixture": {
                "fixture_id": fixture_id,
                "competition_id": "1",
                "competition_name": "World Cup",
                "kickoff_utc": kickoff_utc,
                "status": "FT",
                "home_team_id": "10",
                "home_team_name": "Home",
                "away_team_id": "20",
                "away_team_name": "Away",
                "home_goals": 1,
                "away_goals": 0,
            },
            "card": {"action": "DATA"},
            "temporal": {},
            "analysis_card": {"decision": "WATCH", "markets": []},
        }


def test_dashboard_validates_analysis_pick_without_promoting_to_candidate() -> None:
    service = ReadModelService(repository=cast(Any, RecommendationLoopRepository()))

    payload = service.dashboard(target_date="2026-06-26", window="today")

    assert len(payload["all"]) == 1
    card = payload["all"][0]
    assert card["status"] == "FINISHED"
    assert card["candidate"] is False
    assert card["formal_recommendation"] is False
    assert card["decision_tier"] == "NOT_READY"
    assert card["data_status"] == "BLOCKED"
    assert card["lifecycle_status"] == "DRAFT"
    assert card["outcome_tracked"] is False
    assert card["lock_eligible"] is False
    assert card["reason_code"] == "FIXTURE_LIVE_OR_FINISHED"
    assert card["pick"] is None
    assert card["non_pick"]["reason_code"] == "FIXTURE_LIVE_OR_FINISHED"
    assert card["decision_contract"]["decision_tier"] == "NOT_READY"
    assert card["decision_contract"]["environment"] == "staging"
    assert card["data_readiness"]["source"] == "w2.readiness.data_gate.v1"
    assert card["data_readiness"]["data_status"] == "BLOCKED"
    assert card["data_readiness"]["reason_code"] == "FIXTURE_LIVE_OR_FINISHED"
    assert card["decision_contract"]["data_readiness"]["source"] == "w2.readiness.data_gate.v1"
    assert card["recommendation"]["tier"] == "ANALYSIS_PICK"
    assert card["recommendation"]["decision_tier"] == "ANALYSIS_PICK"
    assert "candidate" not in card["recommendation"]
    assert "formal_recommendation" not in card["recommendation"]
    assert "selection" not in card["recommendation"]
    assert "selection_label_cn" not in card["recommendation"]
    assert "line" not in card["recommendation"]
    assert "odds" not in card["recommendation"]
    recommendation_text = json.dumps(card["recommendation"], ensure_ascii=False)
    assert "HOME_AH" not in recommendation_text
    assert "AWAY_AH" not in recommendation_text
    assert "盘口变化支持大球" not in recommendation_text
    assert not re.search(r"(让|受让)\s*[+-]?\d+(?:\.\d+)?", recommendation_text)
    assert card["result"]["final_score"] == "2-1"
    assert card["validation"]["settlement"] == "UNKNOWN"
    assert card["validation"]["market_hit"] is None
    assert card["validation"]["score_exact_hit"] is True
    assert card["validation"]["counted_in_official"] is False
    assert card["validation"]["counted_in_analysis_shadow"] is True
    assert card["scoreline_picks"] == []
    assert card["scoreline_reference"] is None

    performance = payload["performance"]
    assert performance["sample_size"] == 0
    assert performance["official"]["sample_size"] == 0
    assert performance["analysis_shadow"]["sample_size"] == 0
    assert performance["analysis_shadow"]["hit_rate"] is None
    assert performance["candidate_count"] == 0
    assert performance["analysis_pick_count"] == 1
    assert card["analysis_readiness"]["status"] in {"PARTIAL", "BLOCKED"}
    assert "FIXTURE_NOT_UPCOMING" in card["analysis_readiness"]["blockers"]


def test_all_window_compact_omits_full_data_readiness_objects() -> None:
    service = ReadModelService(repository=cast(Any, RecommendationLoopRepository()))

    payload = service.dashboard(target_date="2026-06-26", window="all")
    card = payload["all"][0]

    assert "data_readiness" not in card
    assert "decision_contract" not in card


def test_non_formal_ah_market_lean_does_not_hand_build_direction_text() -> None:
    service = ReadModelService(repository=cast(Any, RecommendationLoopRepository()))

    decorated = service._decorate_analysis_market(
        {
            "market": "ASIAN_HANDICAP",
            "decision": "ANALYSIS_PICK",
            "tendency": "AWAY_AH",
            "line": "0.25",
            "odds": "2.00",
            "confidence": 0.7,
        }
    )

    assert decorated["lean_cn"] is None
    assert decorated["lean"] is None
    assert decorated["signal_strength"] == 0.7
    assert "confidence" not in decorated
    text = json.dumps(decorated, ensure_ascii=False)
    assert "客队方向 0.25" not in text
    assert not re.search(r"(让|受让)\s*[+-]?\d+(?:\.\d+)?", text)


def test_egypt_api_football_away_plus_quarter_is_canonical_away_favorite() -> None:
    service = ReadModelService(repository=cast(Any, RecommendationLoopRepository()))
    captured = "2026-07-03T17:22:00Z"
    observations: list[dict[str, Any]] = []
    for bookmaker, home_price, away_price in [
        ("Betano", "1.85", "2.00"),
        ("Pinnacle", "1.91", "2.02"),
        ("SBO", "1.94", "1.99"),
        ("Bet365", "1.88", "1.98"),
    ]:
        observations.extend(
            [
                {
                    "fixture_id": "1567306",
                    "canonical_market": "ASIAN_HANDICAP",
                    "raw_market_label": "Asian Handicap",
                    "selection": "Home +0.25",
                    "line": "0.25",
                    "decimal_odds": home_price,
                    "captured_at": captured,
                    "provider_last_update": captured,
                    "bookmaker_id": bookmaker,
                    "bookmaker_name": bookmaker,
                    "suspended": False,
                    "live": False,
                },
                {
                    "fixture_id": "1567306",
                    "canonical_market": "ASIAN_HANDICAP",
                    "raw_market_label": "Asian Handicap",
                    "selection": "Away +0.25",
                    "line": "0.25",
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

    selected = service._select_mainline_observations(observations, market="ASIAN_HANDICAP")
    display = ah_display_contract(selected["line"])

    assert selected["status"] == "READY"
    assert selected["line"] == "0.25"
    assert selected["side_lines"] == {"home": "0.25", "away": "-0.25"}
    assert selected["side_prices"]["away"] > selected["side_prices"]["home"]
    assert display["display_line_cn"] == "客队 -0.25"
    assert display["home_display_line_cn"] == "主队 +0.25"
    assert display["away_display_line_cn"] == "客队 -0.25"


def test_dashboard_results_window_uses_football_day_boundaries() -> None:
    service = ReadModelService(repository=cast(Any, FootballDayResultsRepository()))

    payload = service.dashboard(target_date="2026-06-30", window="results")

    fixture_ids = [card["fixture_id"] for card in payload["all"]]
    assert fixture_ids == ["football-day-start", "football-day-morning"]
    assert [card["fixture_id"] for card in payload["finished"]] == fixture_ids
    assert payload["selected_date"] == "2026-06-30"
    assert payload["selected_football_day"] == "2026-06-30"
    assert payload["selected_date_has_data"] is True
    assert payload["next_available_date"] == "2026-06-30"
    assert payload["football_day_timezone"] == "Asia/Shanghai"
    assert payload["football_day_cutoff_hour"] == 12
    assert payload["football_day_start_utc"] == "2026-06-30T04:00:00Z"
    assert payload["football_day_end_utc"] == "2026-07-01T04:00:00Z"
    assert payload["debug"]["selected_date"] == "2026-06-30"

    response_payload = DashboardResponse.model_validate(
        {"request_id": "test-request", **payload}
    ).model_dump(mode="json")
    assert response_payload["selected_date"] == "2026-06-30"
    assert response_payload["selected_football_day"] == "2026-06-30"
    assert response_payload["selected_date_has_data"] is True
    assert response_payload["next_available_date"] == "2026-06-30"
    assert response_payload["football_day_timezone"] == "Asia/Shanghai"
    assert response_payload["football_day_cutoff_hour"] == 12
    assert response_payload["football_day_start_utc"] == "2026-06-30T04:00:00Z"
    assert response_payload["football_day_end_utc"] == "2026-07-01T04:00:00Z"


def _write_formal_snapshot(
    runtime_root: Path,
    *,
    fixture_id: str = "finished-over",
    snapshot_id: str = "locked-snapshot-1",
) -> None:
    path = runtime_root / "formal_recommendation_snapshots" / f"{snapshot_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "w2_formal_recommendation_snapshot.v1",
                "fixture_id": fixture_id,
                "snapshot_id": snapshot_id,
                "captured_at": "2026-06-26T08:30:00Z",
                "as_of": "2026-06-26T08:30:00Z",
                "kickoff_utc": "2026-06-26T10:00:00Z",
                "home_team_name": "Home",
                "away_team_name": "Away",
                "recommendation": {
                    "tier": "FORMAL",
                    "market": "ASIAN_HANDICAP",
                    "selection": "AWAY_AH",
                    "selection_side": "AWAY",
                    "selection_label_cn": "Away 受让",
                    "line": "1.5",
                    "odds": "1.93",
                    "risk_adjusted_ev": "12.5pct",
                    "reverse_factor_value": True,
                },
                "scoreline_reference": {
                    "source": "formal_simulation",
                    "top_scorelines": [{"scoreline": "1-1", "probability_label": "12%"}],
                },
                "simulation_evidence": {
                    "simulations": 10000,
                    "source": "formal_simulation",
                },
                "candidate": False,
                "formal_recommendation": True,
                "immutable": True,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _write_formal_settlement(
    runtime_root: Path,
    *,
    snapshot_id: str = "locked-snapshot-1",
) -> None:
    path = runtime_root / "formal_recommendation_settlements" / f"{snapshot_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "w2_formal_recommendation_settlement.v1",
                "fixture_id": "finished-over",
                "snapshot_id": snapshot_id,
                "final_score": {"home_goals": 2, "away_goals": 1, "status": "FINISHED"},
                "settlement_outcome": "WIN",
                "settled_units": "1",
                "sample_included": True,
                "win_included": True,
                "evaluated_at": "2026-06-26T12:30:00Z",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_dashboard_exposes_locked_prematch_recommendation_after_kickoff(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.setenv("W2_RUNTIME_ROOT", str(tmp_path))
    _write_formal_snapshot(tmp_path)
    service = ReadModelService(repository=cast(Any, RecommendationLoopRepository()))

    card = service.dashboard(target_date="2026-06-26", window="today")["all"][0]

    locked = card["locked_pre_match_recommendation"]
    assert card["formal_recommendation"] is False
    assert card["formal_suppressed"] is True
    assert card["formal_suppressed_reason"] == "FIXTURE_STARTED_LOCKED_PREMATCH"
    assert locked["status"] == "LOCKED"
    assert locked["recommendation"]["tier"] == "FORMAL"
    assert locked["recommendation"]["selection_label_cn"] == "Away 受让"
    assert locked["settlement"]["status"] == "PENDING"
    assert locked["simulation_evidence"]["simulations"] == 10000


def test_dashboard_reports_no_prematch_formal_when_started_without_snapshot(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.setenv("W2_RUNTIME_ROOT", str(tmp_path))
    service = ReadModelService(repository=cast(Any, RecommendationLoopRepository()))

    card = service.dashboard(target_date="2026-06-26", window="today")["all"][0]

    locked = card["locked_pre_match_recommendation"]
    assert locked["status"] == "NO_PREMATCH_FORMAL"
    assert locked["reason"] == "NO_PREMATCH_FORMAL_SNAPSHOT"
    assert locked["recommendation"] is None
    assert card["formal_suppressed_reason"] == "FIXTURE_STARTED_NO_PREMATCH_FORMAL"


def test_dashboard_exposes_locked_prematch_settlement_when_artifact_exists(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.setenv("W2_RUNTIME_ROOT", str(tmp_path))
    _write_formal_snapshot(tmp_path)
    _write_formal_settlement(tmp_path)
    service = ReadModelService(repository=cast(Any, RecommendationLoopRepository()))

    card = service.dashboard(target_date="2026-06-26", window="today")["all"][0]

    settlement = card["locked_pre_match_recommendation"]["settlement"]
    assert settlement["status"] == "SETTLED"
    assert settlement["settlement_outcome"] == "WIN"
    assert settlement["pnl"] == "1"


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


def test_dashboard_data_refresh_does_not_mark_historical_odds_ready_when_stale() -> None:
    service = ReadModelService(repository=cast(Any, object()))

    refresh = service._dashboard_data_refresh(
        card={
            "data_status": "STALE",
            "non_pick": {"reason_code": "DATA_STALE_ODDS"},
            "data_readiness": {"lineups_status": "NOT_REQUESTED"},
        },
        readiness={"available_inputs": {"market_observations": 3}},
        row={},
    )

    assert refresh["odds_status"] == "STALE"
    assert refresh["lineups_status_label"] == "未到首发请求时点"


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
    assert card["market_timeline"]["status"] == "READY"
    assert card["market_timeline"]["label"] == "盘口时间线 · 参照 · 未验证"
    assert card["market_timeline"]["verified"] is False
    assert card["market_timeline"]["direction_allowed"] is False
    assert card["market_timeline"]["open"]["line"] == -0.5
    assert card["market_timeline"]["open"]["as_of"] == "2026-06-26T08:00:00Z"
    assert card["market_timeline"]["current"]["line"] == -1.0
    assert card["market_timeline"]["current"]["as_of"] == "2026-06-26T09:30:00Z"
    assert card["market_timeline"]["pattern"] == "JUMP_LINE"
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
    monkeypatch.setenv("W2_RECOMPUTE_AH_MAINLINE_AT_READ", "true")
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
    assert card["formal_recommendation"] is False
    assert card["recommendation"]["tier"] == "WATCH"
    assert card["recommendation"]["formal_recommendation"] is False
    assert card["pricing_shadow"]["formal_eligible"] is False
    assert card["pricing_shadow"]["formal_blockers"]


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
                        "raw_market_label": "Asian Handicap",
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
                        "raw_market_label": "Asian Handicap",
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
    assert selected["candidate_lines"][0]["home_line"] == "-0.25"
    assert selected["rejected_lines"] == []


def test_read_model_mainline_excludes_non_full_time_ah_market_labels() -> None:
    captured = "2026-07-03T17:22:42Z"
    observations: list[dict[str, Any]] = []
    for bookmaker in ("bm1", "bm2", "bm3", "bm4"):
        observations.extend(
            [
                {
                    "fixture_id": "colombia-ghana",
                    "canonical_market": "ASIAN_HANDICAP",
                    "raw_market_label": "Asian Handicap",
                    "selection": "Home -1.25",
                    "line": "-1.25",
                    "decimal_odds": "1.92",
                    "captured_at": captured,
                    "provider_last_update": captured,
                    "bookmaker_id": bookmaker,
                    "bookmaker_name": bookmaker,
                    "suspended": False,
                    "live": False,
                },
                {
                    "fixture_id": "colombia-ghana",
                    "canonical_market": "ASIAN_HANDICAP",
                    "raw_market_label": "Asian Handicap",
                    "selection": "Away +1.25",
                    "line": "1.25",
                    "decimal_odds": "1.96",
                    "captured_at": captured,
                    "provider_last_update": captured,
                    "bookmaker_id": bookmaker,
                    "bookmaker_name": bookmaker,
                    "suspended": False,
                    "live": False,
                },
            ]
        )
    for bookmaker in ("cards1", "cards2", "cards3", "cards4", "cards5", "cards6"):
        observations.extend(
            [
                {
                    "fixture_id": "colombia-ghana",
                    "canonical_market": "ASIAN_HANDICAP",
                    "raw_market_label": "Cards Asian Handicap",
                    "selection": "Home -1.5",
                    "line": "-1.5",
                    "decimal_odds": "1.93",
                    "captured_at": captured,
                    "provider_last_update": captured,
                    "bookmaker_id": bookmaker,
                    "bookmaker_name": bookmaker,
                    "suspended": False,
                    "live": False,
                },
                {
                    "fixture_id": "colombia-ghana",
                    "canonical_market": "ASIAN_HANDICAP",
                    "raw_market_label": "Cards Asian Handicap",
                    "selection": "Away +1.5",
                    "line": "1.5",
                    "decimal_odds": "1.95",
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
    assert selected["side_lines"]["home"] == "-1.25"
    assert selected["side_lines"]["away"] == "1.25"
    assert selected["bookmaker_count"] == 4
    assert selected["candidate_lines"][0]["home_line"] == "-1.25"
    assert all(item["line"] != -1.5 for item in selected["candidate_lines"])


def test_read_model_mainline_rejects_low_consensus_balanced_override() -> None:
    captured = "2026-06-26T08:00:00Z"
    observations: list[dict[str, Any]] = []
    for line, home_price, away_price, bookmakers in [
        ("0", "1.66", "2.26", ("bm1", "bm2", "bm3", "bm4", "bm5")),
        ("-0.25", "1.93", "1.95", ("bm1",)),
        ("-0.5", "2.35", "1.61", ("bm1", "bm2", "bm3", "bm4", "bm5")),
    ]:
        for bookmaker in bookmakers:
            observations.extend(
                [
                    {
                        "fixture_id": "future-partial",
                        "canonical_market": "ASIAN_HANDICAP",
                        "raw_market_label": "Asian Handicap",
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
                        "raw_market_label": "Asian Handicap",
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
    odds_entry = service._balanced_odds_entry(selected)

    assert selected["status"] == "READY"
    assert selected["line"] == "0"
    assert selected["side_lines"]["home"] == "0"
    assert "selection_warning" not in selected
    assert selected["candidate_lines"][0]["home_line"] == "0"
    assert selected["candidate_lines"][0]["balanced_override_eligible"] is False
    assert selected["candidate_lines"][0]["consensus_eligible"] is True
    assert odds_entry is not None
    assert odds_entry["candidate_lines"][0]["home_line"] == "0"
    assert "selection_warning" not in odds_entry


def test_read_model_corrects_legacy_timeline_snapshot_to_consensus_mainline() -> None:
    service = ReadModelService(repository=cast(Any, RecommendationLoopRepository()))
    corrected = service._consensus_first_ah_snapshot(
        {
            "market": "ASIAN_HANDICAP",
            "line": -2.5,
            "home_price": 1.93,
            "away_price": 1.86,
            "bookmaker_count": 2,
            "candidate_lines": [
                {
                    "selection_rank": 1,
                    "line": -2.5,
                    "home_price": 1.93,
                    "away_price": 1.86,
                    "bookmaker_count": 2,
                    "balance_distance": 0.010052,
                },
                {
                    "selection_rank": 6,
                    "line": -1.25,
                    "home_price": 2.24,
                    "away_price": 1.685,
                    "bookmaker_count": 4,
                    "balance_distance": 0.070525,
                },
            ],
        }
    )

    assert corrected is not None
    assert corrected["line"] == -1.25
    assert corrected["home_price"] == 2.24
    assert corrected["away_price"] == 1.685
    assert corrected["bookmaker_count"] == 4
    assert corrected["selection_policy"] == "consensus_first_bookmaker_count_then_balance"
    assert corrected["selection_warning"] == "READTIME_CONSENSUS_MAINLINE_CORRECTED"


def test_dashboard_blocks_stale_pricing_shadow_mainline_materialization(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.setenv("W2_RECOMPUTE_AH_MAINLINE_AT_READ", "true")
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
                        "line": -2.5,
                        "home_price": 1.93,
                        "away_price": 1.86,
                        "bookmaker_count": 2,
                        "candidate_lines": [
                            {
                                "selection_rank": 1,
                                "line": -2.5,
                                "home_price": 1.93,
                                "away_price": 1.86,
                                "bookmaker_count": 2,
                                "balance_distance": 0.010052,
                            },
                            {
                                "selection_rank": 6,
                                "line": -1.25,
                                "home_price": 2.24,
                                "away_price": 1.685,
                                "bookmaker_count": 4,
                                "balance_distance": 0.070525,
                            },
                        ],
                        "immutable": True,
                        "source_hash": "legacy-mainline",
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
                            "home_line": "-2.5",
                            "away_line": "2.5",
                            "home_price": 1.93,
                            "away_price": 1.86,
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
    shadow = card["pricing_shadow"]

    assert card["current_odds"]["ah"]["home_line"] == "-1.25"
    assert shadow["market_ah"] == -1.25
    assert shadow["materialized_market_ah"] == -2.5
    assert shadow["selector_market_ah"] == -1.25
    assert shadow["edge_ah"] is None
    assert shadow["mainline_materialization_status"] == "STALE"
    assert shadow["mainline_materialization_blocker"] == "AH_MAINLINE_STALE_MATERIALIZATION"
    assert shadow["canonical_ah_market_blocker"] == "AH_MAINLINE_STALE_MATERIALIZATION"
    assert shadow["canonical_ah_market_validation_status"] == "BLOCKED"
    assert "AH_MAINLINE_STALE_MATERIALIZATION" in shadow["formal_blockers"]
    assert card["formal_recommendation"] is False


def test_runtime_ah_mainline_recompute_is_diagnostic_only_by_default(
    monkeypatch: Any,
) -> None:
    monkeypatch.delenv("W2_RECOMPUTE_AH_MAINLINE_AT_READ", raising=False)
    service = ReadModelService(repository=cast(Any, RecommendationLoopRepository()))
    card: dict[str, Any] = {
        "current_odds": {
            "ah": {
                "home_line": "-2.5",
                "away_line": "2.5",
                "home_price": 1.93,
                "away_price": 1.86,
            }
        },
        "pricing_shadow": {"market_ah": -2.5, "fair_ah": -0.25, "edge_ah": -2.25},
    }
    timeline = {
        "snapshots": [
            {
                "market": "ASIAN_HANDICAP",
                "line": -1.25,
                "home_price": 2.24,
                "away_price": 1.685,
                "bookmaker_count": 4,
                "selection_policy": "consensus_first_bookmaker_count_then_balance",
            }
        ]
    }

    service._apply_signed_ah_line_from_timeline(card, timeline)

    assert card["current_odds"]["ah"]["home_line"] == "-2.5"
    assert card["pricing_shadow"]["market_ah"] == -2.5
    assert card["pricing_shadow"]["edge_ah"] == -2.25
    assert card["pricing_shadow"]["materialized_market_ah"] == -2.5
    assert card["pricing_shadow"]["selector_market_ah"] == -1.25
    assert (
        card["pricing_shadow"]["mainline_materialization_blocker"]
        == "AH_MAINLINE_STALE_MATERIALIZATION"
    )


def test_pricing_shadow_mainline_reconciliation_recomputes_edge() -> None:
    service = ReadModelService(repository=cast(Any, RecommendationLoopRepository()))
    shadow = {"market_ah": -2.5, "fair_ah": -0.25}

    service._reconcile_pricing_shadow_ah_mainline(shadow, -1.25)

    assert shadow["market_ah"] == -1.25
    assert shadow["edge_ah"] == -1.0
    assert shadow["materialized_market_ah"] == -2.5
    assert shadow["selector_market_ah"] == -1.25
    assert shadow["mainline_materialization_status"] == "STALE"
    assert shadow["mainline_materialization_blocker"] == "AH_MAINLINE_STALE_MATERIALIZATION"


def test_read_model_mainline_rejects_cross_bookmaker_ah_pairing() -> None:
    captured = "2026-06-26T08:00:00Z"
    observations = [
        {
            "fixture_id": "future-partial",
            "canonical_market": "ASIAN_HANDICAP",
            "raw_market_label": "Asian Handicap",
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
            "raw_market_label": "Asian Handicap",
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

    assert selected["status"] == "NO_BALANCED_MAINLINE"
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


def test_dashboard_hides_formal_simulation_scorelines_without_public_pick() -> None:
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
    assert card["decision_tier"] not in {"ANALYSIS_PICK", "RECOMMEND"}
    assert card["pick"] is None
    assert card["scoreline_picks"] == []
    assert card["scoreline_reference"] is None


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
