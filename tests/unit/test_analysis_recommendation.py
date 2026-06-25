from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from w2.features.framework import FeatureContribution, FeatureSet, FeatureStatus, TeamSide
from w2.strategy.analysis_recommendation import (
    AnalysisBuildInputs,
    AnalysisDecision,
    AnalysisMarket,
    HalfGoalModelInput,
    MarketAnalysis,
    build_multi_market_analysis,
)
from w2.strategy.bookmaker_intent import BookmakerIntent, IntentSignal

NOW = datetime(2026, 6, 25, 12, 0, tzinfo=UTC)


def intent(signal: IntentSignal, confidence: float = 0.7) -> BookmakerIntent:
    side = (
        TeamSide.HOME
        if signal in {IntentSignal.HOME_LEAN, IntentSignal.OVER_LEAN}
        else TeamSide.AWAY
    )
    return BookmakerIntent(
        fixture_id="1489404",
        market_kind="AH" if signal != IntentSignal.OVER_LEAN else "OU",
        intent=signal,
        confidence=confidence,
        implied_side=side,
        reason="test",
        evidence=(),
    )


def feature_set() -> FeatureSet:
    return FeatureSet(
        fixture_id="1489404",
        competition_id="world_cup_2026",
        as_of=NOW,
        status=FeatureStatus.READY,
        contributions=(
            FeatureContribution(
                feature_id="F7_STRENGTH_FORM",
                label="强度/状态/攻防",
                status=FeatureStatus.READY,
                score=0.3,
                weight=0.18,
                side=TeamSide.HOME,
                reason="OPPONENT_ADJUSTED_STRENGTH_FORM",
                observed_at=NOW - timedelta(hours=1),
            ),
        ),
    )


def complete_inputs() -> AnalysisBuildInputs:
    return AnalysisBuildInputs(
        ah_intent=intent(IntentSignal.HOME_LEAN),
        ou_intent=intent(IntentSignal.OVER_LEAN),
        feature_set=feature_set(),
        half_goals=HalfGoalModelInput(expected_home_goals=1.6, expected_away_goals=1.0),
        score_matrix={(1, 1): 0.28, (2, 1): 0.20, (1, 0): 0.15, (0, 1): 0.12},
        score_direction="HOME",
    )


def test_four_markets_emit_analysis_pick_with_explainable_reasons() -> None:
    card = build_multi_market_analysis(fixture_id="1489404", inputs=complete_inputs())

    assert card.decision == AnalysisDecision.ANALYSIS_PICK
    assert {market.market for market in card.markets} == {
        AnalysisMarket.ASIAN_HANDICAP,
        AnalysisMarket.TOTALS,
        AnalysisMarket.FIRST_HALF_GOALS,
        AnalysisMarket.SCORE,
    }
    assert all(market.decision == AnalysisDecision.ANALYSIS_PICK for market in card.markets)
    assert all(market.reasons for market in card.markets)
    assert card.candidate is False
    assert card.formal_recommendation is False


def test_missing_data_skips_only_affected_market() -> None:
    inputs = AnalysisBuildInputs(
        **{
            **complete_inputs().__dict__,
            "missing_markets": frozenset({AnalysisMarket.SCORE}),
            "score_matrix": None,
            "score_direction": None,
        }
    )

    card = build_multi_market_analysis(fixture_id="1489404", inputs=inputs)
    score = next(market for market in card.markets if market.market == AnalysisMarket.SCORE)
    ah = next(market for market in card.markets if market.market == AnalysisMarket.ASIAN_HANDICAP)

    assert score.decision == AnalysisDecision.SKIP
    assert score.tendency is None
    assert ah.decision == AnalysisDecision.ANALYSIS_PICK


def test_score_market_uses_direction_consistent_score_card() -> None:
    card = build_multi_market_analysis(fixture_id="1489404", inputs=complete_inputs())
    score = next(market for market in card.markets if market.market == AnalysisMarket.SCORE)

    assert score.score_card is not None
    assert [row.score_direction for row in score.score_card.scenarios] == ["HOME", "HOME"]


def test_output_rejects_banned_certainty_wording() -> None:
    with pytest.raises(ValueError, match="banned certainty"):
        MarketAnalysis(
            market=AnalysisMarket.TOTALS,
            decision=AnalysisDecision.ANALYSIS_PICK,
            tendency="OVER",
            confidence=0.5,
            reasons=("保证命中",),
            risks=("risk",),
            invalidation_conditions=("condition",),
        )


def test_leakage_blocked_intent_forces_market_skip() -> None:
    inputs = AnalysisBuildInputs(
        **{
            **complete_inputs().__dict__,
            "ah_intent": intent(IntentSignal.LEAKAGE_BLOCKED, confidence=0.0),
        }
    )

    card = build_multi_market_analysis(fixture_id="1489404", inputs=inputs)
    ah = next(market for market in card.markets if market.market == AnalysisMarket.ASIAN_HANDICAP)

    assert ah.decision == AnalysisDecision.SKIP
    assert ah.reasons == ("LEAKAGE_BLOCKED",)
