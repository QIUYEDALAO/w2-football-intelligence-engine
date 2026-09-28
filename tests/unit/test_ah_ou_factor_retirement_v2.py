"""Task 4A self-test: F9+F6 single-chain admission and factor retirement.

Covers the AH/OU v3 contract's factor-retirement requirements:

1. Two evidence families (F9_TRUE_XG + F6_H2H) alone admit a recommendation.
2. F3/F5 (and F1/F2/F4/F10) perturbation/missing does not change the decision.
3. Missing F9 or F6 fails closed (SKIP); missing the bilateral price market skips.
"""
from __future__ import annotations

from datetime import UTC, datetime

from w2.features.framework import (
    FeatureContribution,
    FeatureSet,
    FeatureStatus,
    TeamSide,
)
from w2.strategy.analysis_recommendation import (
    AnalysisBuildInputs,
    AnalysisDecision,
    AnalysisMarket,
    HalfGoalModelInput,
    build_multi_market_analysis,
)
from w2.strategy.bookmaker_intent import BookmakerIntent, IntentSignal
from w2.strategy.factor_score import build_factor_score

NOW = datetime(2026, 6, 25, 12, 0, tzinfo=UTC)


def _c(
    feature_id: str,
    *,
    source_group: str,
    status: FeatureStatus = FeatureStatus.READY,
    score: float = 0.6,
    weight: float = 0.1,
    reason: str = "X",
) -> FeatureContribution:
    return FeatureContribution(
        feature_id=feature_id,
        label=feature_id,
        status=status,
        score=score,
        weight=weight,
        side=TeamSide.HOME,
        reason=reason,
        source_group=source_group,
        is_independent_signal=True,
        observed_at=NOW,
    )


def _feature_set(contributions: list[FeatureContribution]) -> FeatureSet:
    return FeatureSet(
        fixture_id="fx",
        competition_id="world_cup_2026",
        as_of=NOW,
        status=FeatureStatus.READY,
        contributions=tuple(contributions),
    )


def _two_families(
    *,
    f9_status: FeatureStatus = FeatureStatus.READY,
    include_f6: bool = True,
) -> FeatureSet:
    contribs: list[FeatureContribution] = [
        _c("F9_TRUE_XG", source_group="xg", status=f9_status, reason="AS_OF_ROLLING_XG_DIFF"),
    ]
    if include_f6:
        contribs.append(
            _c("F6_H2H", source_group="h2h", weight=0.18, reason="INTERNAL_FIXTURE_H2H_DIFF")
        )
    return _feature_set(contribs)


def _inputs(feature_set: FeatureSet, *, missing: frozenset[AnalysisMarket] = frozenset()):
    return AnalysisBuildInputs(
        ah_intent=BookmakerIntent(
            fixture_id="fx",
            market_kind="AH",
            intent=IntentSignal.HOME_LEAN,
            signal_strength=0.7,
            implied_side=TeamSide.HOME,
            reason="t",
            evidence=(),
        ),
        ou_intent=BookmakerIntent(
            fixture_id="fx",
            market_kind="OU",
            intent=IntentSignal.OVER_LEAN,
            signal_strength=0.7,
            implied_side=TeamSide.HOME,
            reason="t",
            evidence=(),
        ),
        feature_set=feature_set,
        half_goals=HalfGoalModelInput(expected_home_goals=1.6, expected_away_goals=1.0),
        score_matrix={(1, 1): 0.28, (2, 1): 0.20},
        score_direction="HOME",
        missing_markets=missing,
    )


def _ah(card):
    return next(m for m in card.markets if m.market == AnalysisMarket.ASIAN_HANDICAP)


def test_two_evidence_families_alone_admit() -> None:
    result = build_factor_score(_two_families())
    assert result.admitted is True
    assert result.admission_blockers == ()
    assert result.participant_count == 2
    assert {p.feature_id for p in result.participants} == {"F9_TRUE_XG", "F6_H2H"}


def test_two_evidence_families_emit_recommendation() -> None:
    card = build_multi_market_analysis(fixture_id="fx", inputs=_inputs(_two_families()))
    assert _ah(card).decision == AnalysisDecision.ANALYSIS_PICK


def test_missing_f9_skips() -> None:
    result = build_factor_score(_two_families(f9_status=FeatureStatus.LEAKAGE_BLOCKED))
    assert result.admitted is False
    assert "REQUIRED_EVIDENCE_MISSING:F9_TRUE_XG" in result.admission_blockers

    card = build_multi_market_analysis(
        fixture_id="fx", inputs=_inputs(_two_families(f9_status=FeatureStatus.LEAKAGE_BLOCKED))
    )
    ah = _ah(card)
    assert ah.decision == AnalysisDecision.SKIP
    assert "REQUIRED_EVIDENCE_MISSING:F9_TRUE_XG" in ah.reasons[0]


def test_missing_f6_skips() -> None:
    result = build_factor_score(_two_families(include_f6=False))
    assert result.admitted is False
    assert "REQUIRED_EVIDENCE_MISSING:F6_H2H" in result.admission_blockers

    card = build_multi_market_analysis(
        fixture_id="fx", inputs=_inputs(_two_families(include_f6=False))
    )
    ah = _ah(card)
    assert ah.decision == AnalysisDecision.SKIP
    assert "REQUIRED_EVIDENCE_MISSING:F6_H2H" in ah.reasons[0]


def test_f3_f5_perturbation_does_not_change_decision() -> None:
    base = list(_two_families().contributions)

    def build(*, f3_score: float, f5_status: FeatureStatus, f1: float, f2: float) -> dict:
        contribs = [
            *base,
            _c("F3_REST_FITNESS", source_group="team_fixture_history", score=f3_score),
            _c(
                "F5_RECENT_AH_COVER",
                source_group="team_fixture_history",
                status=f5_status,
                score=None if f5_status != FeatureStatus.READY else 0.9,
            ),
            _c("F1_MARKET_MOVEMENT", source_group="market", score=f1),
            _c("F2_BOOKMAKER_INTENT", source_group="market", score=f2),
            _c("F4_MATCH_IMPORTANCE", source_group="match_importance", score=0.5),
        ]
        result = build_factor_score(_feature_set(contribs))
        return {
            "admitted": result.admitted,
            "margin": result.margin,
            "direction": result.direction,
            "participants": {p.feature_id for p in result.participants},
        }

    baseline = build(f3_score=0.2, f5_status=FeatureStatus.INSUFFICIENT_DATA, f1=0.1, f2=0.1)
    # Perturb every retired factor's value, drop F5, flip F1/F2/F4 arbitrarily.
    perturbed = build(f3_score=0.99, f5_status=FeatureStatus.READY, f1=0.9, f2=0.9)

    assert baseline["admitted"] is perturbed["admitted"] is True
    assert baseline["margin"] == perturbed["margin"]
    assert baseline["direction"] == perturbed["direction"]
    assert baseline["participants"] == perturbed["participants"] == {"F9_TRUE_XG", "F6_H2H"}


def test_missing_bilateral_price_market_skips() -> None:
    card = build_multi_market_analysis(
        fixture_id="fx",
        inputs=_inputs(_two_families(), missing=frozenset({AnalysisMarket.ASIAN_HANDICAP})),
    )
    ah = _ah(card)
    assert ah.decision == AnalysisDecision.SKIP
    assert ah.reasons[0] == "AH_DATA_UNAVAILABLE"
