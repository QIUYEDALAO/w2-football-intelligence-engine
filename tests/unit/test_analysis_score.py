from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from w2.strategy.analysis_score import (
    DISCLAIMER,
    AnalysisInput,
    MarketMovementSignal,
    ModelMarketSignal,
    TeamComparisonSignal,
    build_analysis_card,
)

NOW = datetime(2026, 6, 25, 10, tzinfo=UTC)


def comparison(home: float, away: float, reason: str) -> TeamComparisonSignal:
    return TeamComparisonSignal(
        home=home,
        away=away,
        observed_at=NOW - timedelta(minutes=5),
        reason=reason,
    )


def complete_input() -> AnalysisInput:
    return AnalysisInput(
        fixture_id="analysis-001",
        as_of=NOW,
        kickoff_utc=NOW + timedelta(hours=2),
        market_movement=MarketMovementSignal(
            home_direction_price_move=-0.08,
            away_direction_price_move=0.04,
            observed_at=NOW - timedelta(minutes=3),
            reason="主队方向赔率下行且客队方向走弱",
        ),
        recent_form=comparison(2.1, 1.0, "主队近期状态优于客队"),
        goal_rate=comparison(1.8, 1.1, "主队进攻/防守综合强度占优"),
        fitness=comparison(5, 3, "主队休息天数更多"),
        ah_cover_rate=comparison(0.54, 0.47, "主队近期赢盘率略优，弱信号低权重"),
        h2h=comparison(3, 1, "历史交锋样本支持主队方向"),
        model_market=ModelMarketSignal(
            model_probabilities={"HOME": 0.49, "DRAW": 0.26, "AWAY": 0.25},
            market_probabilities={"HOME": 0.42, "DRAW": 0.28, "AWAY": 0.30},
            observed_at=NOW - timedelta(minutes=4),
        ),
    )


def test_analysis_pick_is_explainable_and_never_formal_recommendation() -> None:
    card = build_analysis_card(complete_input())
    payload = card.as_dict()

    assert payload["decision"] == "ANALYSIS_PICK"
    assert payload["primary_direction"] == "HOME"
    assert payload["analysis_score"] > 0
    assert payload["candidate"] is False
    assert payload["formal_recommendation"] is False
    assert payload["disclaimer"] == DISCLAIMER
    assert any(item["name"] == "MARKET_MOVEMENT" for item in payload["factors"])
    assert all("weighted_score" in item and "reason" in item for item in payload["factors"])


def test_missing_h2h_and_team_value_are_honest_zero_contribution() -> None:
    input_data = complete_input()
    degraded = AnalysisInput(
        fixture_id=input_data.fixture_id,
        as_of=input_data.as_of,
        kickoff_utc=input_data.kickoff_utc,
        market_movement=input_data.market_movement,
        recent_form=input_data.recent_form,
        goal_rate=input_data.goal_rate,
        fitness=input_data.fitness,
        ah_cover_rate=input_data.ah_cover_rate,
        h2h=None,
        team_value=None,
        model_market=input_data.model_market,
    )

    factors = {item["name"]: item for item in build_analysis_card(degraded).as_dict()["factors"]}

    assert factors["H2H"]["status"] == "UNAVAILABLE"
    assert factors["H2H"]["reason"] == "H2H_UNAVAILABLE"
    assert factors["H2H"]["weighted_score"] == 0
    assert factors["TEAM_VALUE"]["status"] == "UNAVAILABLE"
    assert factors["TEAM_VALUE"]["reason"] == "VALUE_DATA_UNAVAILABLE"
    assert factors["TEAM_VALUE"]["weighted_score"] == 0


def test_default_without_data_is_skip() -> None:
    card = build_analysis_card(
        AnalysisInput(
            fixture_id="analysis-002",
            as_of=NOW,
            kickoff_utc=NOW + timedelta(hours=2),
        )
    )

    assert card.decision == "SKIP"
    assert card.primary_direction is None
    assert "INSUFFICIENT_READY_FACTOR_WEIGHT" in card.reasons


def test_future_observed_factor_is_blocked_as_leakage() -> None:
    input_data = complete_input()
    leaky = AnalysisInput(
        fixture_id=input_data.fixture_id,
        as_of=input_data.as_of,
        kickoff_utc=input_data.kickoff_utc,
        market_movement=MarketMovementSignal(
            home_direction_price_move=-0.08,
            away_direction_price_move=0.04,
            observed_at=NOW + timedelta(minutes=1),
            reason="future movement should be blocked",
        ),
        recent_form=input_data.recent_form,
        goal_rate=input_data.goal_rate,
        fitness=input_data.fitness,
        ah_cover_rate=input_data.ah_cover_rate,
        h2h=input_data.h2h,
        model_market=input_data.model_market,
    )

    movement = {
        item["name"]: item for item in build_analysis_card(leaky).as_dict()["factors"]
    }["MARKET_MOVEMENT"]

    assert movement["status"] == "LEAKAGE_BLOCKED"
    assert movement["weighted_score"] == 0


def test_analysis_card_does_not_use_forbidden_profit_language() -> None:
    encoded = json.dumps(build_analysis_card(complete_input()).as_dict(), ensure_ascii=False)

    assert DISCLAIMER in encoded
    for phrase in ("稳赢", "必中", "稳赚", "guaranteed profit", "sure win"):
        assert phrase not in encoded
