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


def intent(signal: IntentSignal, signal_strength: float = 0.7) -> BookmakerIntent:
    side = (
        TeamSide.HOME
        if signal in {IntentSignal.HOME_LEAN, IntentSignal.OVER_LEAN}
        else TeamSide.AWAY
    )
    return BookmakerIntent(
        fixture_id="1489404",
        market_kind="AH" if signal != IntentSignal.OVER_LEAN else "OU",
        intent=signal,
        signal_strength=signal_strength,
        implied_side=side,
        reason="test",
        evidence=(),
    )


def feature_set(*, xg_status: FeatureStatus = FeatureStatus.READY) -> FeatureSet:
    # Three factors, all HOME-leaning, all eligible to enter the AH factor
    # score (registry ACTIVE/SCORING/numeric_effect_enabled=true,
    # is_independent_signal=True, source_group in
    # team_score.AUTHORITATIVE_SIGNAL_GROUPS) — satisfies the Owner-approved
    # admission rule (F9 participates + >=3 factors participate). `xg_status`
    # lets tests simulate F9 being unavailable/leakage-blocked without
    # duplicating the whole fixture.
    return FeatureSet(
        fixture_id="1489404",
        competition_id="world_cup_2026",
        as_of=NOW,
        status=FeatureStatus.READY,
        contributions=(
            FeatureContribution(
                feature_id="F9_TRUE_XG",
                label="四字段 xG",
                status=xg_status,
                score=0.6,
                weight=0.10,
                side=TeamSide.HOME,
                reason="AS_OF_ROLLING_XG_DIFF",
                source_group="xg",
                is_independent_signal=True,
                observed_at=NOW - timedelta(hours=1),
            ),
            FeatureContribution(
                feature_id="F7_STRENGTH_FORM",
                label="强度/状态/攻防",
                status=FeatureStatus.READY,
                score=0.3,
                weight=0.18,
                side=TeamSide.HOME,
                reason="OPPONENT_ADJUSTED_STRENGTH_FORM",
                source_group="ratings",
                is_independent_signal=True,
                observed_at=NOW - timedelta(hours=1),
            ),
            FeatureContribution(
                feature_id="F5_RECENT_AH_COVER",
                label="近期让球覆盖",
                status=FeatureStatus.READY,
                score=0.2,
                weight=0.05,
                side=TeamSide.HOME,
                reason="RECENT_AH_COVER_RATE_DIFF",
                source_group="team_fixture_history",
                is_independent_signal=True,
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


def test_half_goal_model_contract_supports_only_first_half_point_five() -> None:
    model_input = HalfGoalModelInput(expected_home_goals=1.2, expected_away_goals=0.8)
    assert model_input.market_line == 0.5
    with pytest.raises(TypeError):
        HalfGoalModelInput(  # type: ignore[call-arg]
            expected_home_goals=1.2,
            expected_away_goals=0.8,
            threshold=1.5,
        )
    with pytest.raises(TypeError):
        HalfGoalModelInput(  # type: ignore[call-arg]
            expected_home_goals=1.2,
            expected_away_goals=0.8,
            market_line=1.5,
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
            signal_strength=0.5,
            reasons=("保证命中",),
            risks=("risk",),
            invalidation_conditions=("condition",),
        )


def test_leakage_blocked_bookmaker_intent_no_longer_gates_ah() -> None:
    # AH's direction and admission are driven by factor_score, not
    # ah_intent, as of the score-driven-recommendation change (2026-09-03):
    # bookmaker_intent no longer determines whether AH publishes a pick.
    # A leakage-blocked ah_intent by itself must not force a skip.
    inputs = AnalysisBuildInputs(
        **{
            **complete_inputs().__dict__,
            "ah_intent": intent(IntentSignal.LEAKAGE_BLOCKED, signal_strength=0.0),
        }
    )

    card = build_multi_market_analysis(fixture_id="1489404", inputs=inputs)
    ah = next(market for market in card.markets if market.market == AnalysisMarket.ASIAN_HANDICAP)

    assert ah.decision == AnalysisDecision.ANALYSIS_PICK


def test_leakage_blocked_mandatory_factor_forces_ah_skip() -> None:
    # The equivalent safety property now lives at the factor level: a
    # LEAKAGE_BLOCKED F9_TRUE_XG contribution is not READY, so it does not
    # participate in the factor score, the mandatory-factor admission rule
    # fails, and AH correctly skips rather than publishing a pick built
    # without its required strength anchor.
    inputs = AnalysisBuildInputs(
        **{
            **complete_inputs().__dict__,
            "feature_set": feature_set(xg_status=FeatureStatus.LEAKAGE_BLOCKED),
        }
    )

    card = build_multi_market_analysis(fixture_id="1489404", inputs=inputs)
    ah = next(market for market in card.markets if market.market == AnalysisMarket.ASIAN_HANDICAP)

    assert ah.decision == AnalysisDecision.SKIP
    assert ah.tendency is None
    assert len(ah.reasons) == 1
    assert ah.reasons[0].startswith("FACTOR_ADMISSION_FAILED:")
    assert "MANDATORY_FACTOR_MISSING:F9_TRUE_XG" in ah.reasons[0]


def test_low_strength_non_ah_markets_emit_no_edge_not_analysis_pick() -> None:
    # TOTALS/FIRST_HALF_GOALS/SCORE are untouched by the AH change and keep
    # their own strength thresholds: weak signals still emit NO_EDGE there.
    inputs = AnalysisBuildInputs(
        **{
            **complete_inputs().__dict__,
            "ou_intent": intent(IntentSignal.OVER_LEAN, signal_strength=0.4),
            "half_goals": HalfGoalModelInput(
                expected_home_goals=0.78,
                expected_away_goals=0.78,
            ),
            "score_matrix": {
                (0, 0): 0.40,
                (0, 1): 0.30,
                (1, 1): 0.18,
                (1, 0): 0.02,
            },
            "score_direction": "HOME",
        }
    )

    card = build_multi_market_analysis(fixture_id="1489404", inputs=inputs)
    non_ah = [market for market in card.markets if market.market != AnalysisMarket.ASIAN_HANDICAP]

    assert all(market.decision == AnalysisDecision.NO_EDGE for market in non_ah)
    assert {market.tendency for market in non_ah} == {None}
    assert all(market.signal_strength < 0.55 for market in non_ah)


def test_ah_has_no_strength_threshold_by_design() -> None:
    # Owner-approved (2026-09-03): no strength threshold is set on AH yet —
    # see W2_UPGRADE_PLAN.md cut 06 step 5. An admitted, non-neutral factor
    # score always produces ANALYSIS_PICK, regardless of how small the
    # margin is; weak ah_intent (unlike before this change) has no bearing
    # on this at all.
    inputs = AnalysisBuildInputs(
        **{
            **complete_inputs().__dict__,
            "ah_intent": intent(IntentSignal.HOME_LEAN, signal_strength=0.0),
        }
    )

    card = build_multi_market_analysis(fixture_id="1489404", inputs=inputs)
    ah = next(market for market in card.markets if market.market == AnalysisMarket.ASIAN_HANDICAP)

    assert ah.decision == AnalysisDecision.ANALYSIS_PICK
    assert ah.tendency == "HOME_AH"


def test_ah_emits_no_edge_when_factor_score_is_exactly_neutral() -> None:
    # AH's own no-edge path: admitted (F9 + >=3 factors participate) but the
    # weighted margin is exactly zero, so there is no side to lean toward.
    tied_features = FeatureSet(
        fixture_id="1489404",
        competition_id="world_cup_2026",
        as_of=NOW,
        status=FeatureStatus.READY,
        contributions=(
            FeatureContribution(
                feature_id="F9_TRUE_XG",
                label="四字段 xG",
                status=FeatureStatus.READY,
                score=0.5,
                weight=0.10,
                side=TeamSide.NEUTRAL,
                reason="AS_OF_ROLLING_XG_DIFF",
                source_group="xg",
                is_independent_signal=True,
                observed_at=NOW - timedelta(hours=1),
            ),
            FeatureContribution(
                feature_id="F7_STRENGTH_FORM",
                label="强度/状态/攻防",
                status=FeatureStatus.READY,
                score=0.3,
                weight=0.18,
                side=TeamSide.NEUTRAL,
                reason="OPPONENT_ADJUSTED_STRENGTH_FORM",
                source_group="ratings",
                is_independent_signal=True,
                observed_at=NOW - timedelta(hours=1),
            ),
            FeatureContribution(
                feature_id="F5_RECENT_AH_COVER",
                label="近期让球覆盖",
                status=FeatureStatus.READY,
                score=0.2,
                weight=0.05,
                side=TeamSide.NEUTRAL,
                reason="RECENT_AH_COVER_RATE_DIFF",
                source_group="team_fixture_history",
                is_independent_signal=True,
                observed_at=NOW - timedelta(hours=1),
            ),
        ),
    )
    inputs = AnalysisBuildInputs(**{**complete_inputs().__dict__, "feature_set": tied_features})

    card = build_multi_market_analysis(fixture_id="1489404", inputs=inputs)
    ah = next(market for market in card.markets if market.market == AnalysisMarket.ASIAN_HANDICAP)

    assert ah.decision == AnalysisDecision.NO_EDGE
    assert ah.tendency is None
    assert ah.reasons == ("FACTOR_SCORE_NO_DIRECTION",)
