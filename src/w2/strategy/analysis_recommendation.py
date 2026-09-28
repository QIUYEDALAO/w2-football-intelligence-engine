"""Offline multi-market analysis recommendation assembly.

The admission gates are deliberately asymmetric between markets:

* ``ASIAN_HANDICAP`` is gated by the **factor gate** (``factor_score``): the two
  evidence families F9_TRUE_XG (xg) and F6_H2H (h2h) must both participate in the
  weighted score.  Bookmaker intent is attached only as reference and does not
  drive direction or admission.  No strength threshold is layered on top of an
  admitted score.
* ``TOTALS`` is a market view only.  OU intent never admits a recommendation.

The asymmetry is structural, not a bug: the home/away weighted strength axis is
the one question ``team_score``'s aggregation was built to answer, whereas
over/under total goals is a different question that no factor's HOME/AWAY side
encodes.  TOTALS therefore keeps its own, independent intent-signal readiness
gate.  The two paths never share a gate, so a candidate can never be double
blocked or double admitted by both.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, ClassVar, Literal

from w2.features.framework import FeatureSet, FeatureStatus, TeamSide
from w2.strategy.bookmaker_intent import BookmakerIntent, IntentSignal
from w2.strategy.factor_score import FactorScore, build_factor_score
from w2.strategy.score_card import ScoreCard, build_score_card
from w2.strategy.score_scenarios import Direction, ScoreMatrix

DISCLAIMER = "分析参考·非稳赢"
BANNED_OUTPUT_TERMS = ("稳赢", "必中", "保证")
MIN_HALF_GOAL_PROBABILITY_EDGE = 0.08
MIN_SCORE_SCENARIO_PROBABILITY = 0.18


class AnalysisDecision(StrEnum):
    SKIP = "SKIP"
    NO_EDGE = "NO_EDGE"
    WATCH = "WATCH"
    ANALYSIS_PICK = "ANALYSIS_PICK"


class AnalysisMarket(StrEnum):
    ASIAN_HANDICAP = "ASIAN_HANDICAP"
    TOTALS = "TOTALS"
    FIRST_HALF_GOALS = "FIRST_HALF_GOALS"
    SCORE = "SCORE"


@dataclass(frozen=True, kw_only=True)
class MarketAnalysis:
    market: AnalysisMarket
    decision: AnalysisDecision
    tendency: str | None
    signal_strength: float
    reasons: tuple[str, ...]
    risks: tuple[str, ...]
    invalidation_conditions: tuple[str, ...]
    score_card: ScoreCard | None = None
    disclaimer: str = DISCLAIMER
    candidate: Literal[False] = False
    formal_recommendation: Literal[False] = False

    def __post_init__(self) -> None:
        _assert_disclaimer(self.disclaimer)
        _assert_compliant_text(*(self.reasons + self.risks + self.invalidation_conditions))
        if self.candidate or self.formal_recommendation:
            raise ValueError("analysis recommendations cannot set candidate/formal flags")
        if (
            self.decision in {AnalysisDecision.SKIP, AnalysisDecision.NO_EDGE}
            and self.tendency is not None
        ):
            raise ValueError("non-pick market analysis must not carry a tendency")


@dataclass(frozen=True, kw_only=True)
class MultiMarketAnalysisCard:
    fixture_id: str
    decision: AnalysisDecision
    markets: tuple[MarketAnalysis, ...]
    bookmaker_intent: BookmakerIntent | None
    factor_score: FactorScore | None = None
    disclaimer: str = DISCLAIMER
    candidate: Literal[False] = False
    formal_recommendation: Literal[False] = False

    def __post_init__(self) -> None:
        _assert_disclaimer(self.disclaimer)
        if self.candidate or self.formal_recommendation:
            raise ValueError("analysis card cannot set candidate/formal flags")


@dataclass(frozen=True, kw_only=True)
class HalfGoalModelInput:
    market_line: ClassVar[float] = 0.5
    expected_home_goals: float
    expected_away_goals: float
    first_half_share: float = 0.45


@dataclass(frozen=True, kw_only=True)
class AnalysisBuildInputs:
    # Legacy weighted-factor / bookmaker-intent inputs. They are None on the
    # F9+F6 softmax path: the softmax path must not build ``feature_set`` or
    # infer ``bookmaker_intent`` at all (停用因子彻底退出新路径).
    ah_intent: BookmakerIntent | None = None
    ou_intent: BookmakerIntent | None = None
    feature_set: FeatureSet | None = None
    half_goals: HalfGoalModelInput | None = None
    score_matrix: ScoreMatrix | None = None
    score_direction: Direction | None = None
    missing_markets: frozenset[AnalysisMarket] = frozenset()
    base_risks: tuple[str, ...] = ("阵容/伤停临场变化可能改变判断。",)
    # F9+F6 softmax path (task "原子切换前整改"). When ``softmax_status`` is not
    # ``LEGACY`` the AH/OU markets are emitted by the frozen softmax selection
    # instead of the legacy weighted ``factor_score`` / ``bookmaker_intent`` path.
    ah_selection: dict[str, Any] | None = None
    ou_selection: dict[str, Any] | None = None
    softmax_status: str = "LEGACY"


def build_multi_market_analysis(
    *,
    fixture_id: str,
    inputs: AnalysisBuildInputs,
) -> MultiMarketAnalysisCard:
    # F9+F6 softmax path: AH direction and OU direction are emitted by the frozen
    # softmax selection (``ah_select``/``ou_select``), not by the legacy weighted
    # ``factor_score`` or the legacy ``bookmaker_intent`` OU view. This is the
    # atomic replacement -- when a selection is present the legacy path is not
    # consulted, so the two can never double-drive a market.
    use_softmax = inputs.softmax_status != "LEGACY"
    if use_softmax:
        ah_market, ou_market = build_softmax_market_analyses(
            ah_selection=inputs.ah_selection,
            ou_selection=inputs.ou_selection,
            status=inputs.softmax_status,
            base_risks=inputs.base_risks,
        )
        factor_score: FactorScore | None = None
    else:
        # `factor_score` is computed once here from the same `feature_set` already
        # carried by `inputs`. It drives ONLY the Asian Handicap market below,
        # because home/away weighted strength is the one axis team_score's
        # aggregation was built to answer. TOTALS (over/under total goals) and
        # the xG/lambda-driven FIRST_HALF_GOALS/SCORE markets ask a different
        # question that no factor's HOME/AWAY side encodes; they keep their own
        # existing, independent readiness gates untouched.
        factor_score = build_factor_score(inputs.feature_set)
        ou_market = _ou_market(inputs)
        _assert_ou_intent_emits_no_positive_recommendation(ou_market)
        ah_market = _ah_market(inputs, factor_score=factor_score)
    markets = (
        ah_market,
        ou_market,
        _half_goal_market(inputs),
        _score_market(inputs),
    )
    card_decision = (
        AnalysisDecision.ANALYSIS_PICK
        if any(item.decision == AnalysisDecision.ANALYSIS_PICK for item in markets)
        else AnalysisDecision.NO_EDGE
        if any(item.decision == AnalysisDecision.NO_EDGE for item in markets)
        else AnalysisDecision.WATCH
        if any(item.decision == AnalysisDecision.WATCH for item in markets)
        else AnalysisDecision.SKIP
    )
    return MultiMarketAnalysisCard(
        fixture_id=fixture_id,
        decision=card_decision,
        markets=markets,
        bookmaker_intent=inputs.ah_intent,
        factor_score=factor_score,
    )


def _ah_market(
    inputs: AnalysisBuildInputs,
    *,
    factor_score: FactorScore,
) -> MarketAnalysis:
    if AnalysisMarket.ASIAN_HANDICAP in inputs.missing_markets:
        return _skip(AnalysisMarket.ASIAN_HANDICAP, "AH_DATA_UNAVAILABLE")
    # Single-chain admission rule (2026-09-28, AH/OU v3): F9_TRUE_XG and F6_H2H
    # must both participate in the weighted score. No strength threshold is
    # applied on top of this.
    if not factor_score.admitted:
        return _skip(
            AnalysisMarket.ASIAN_HANDICAP,
            "FACTOR_ADMISSION_FAILED:" + ",".join(factor_score.admission_blockers),
        )
    if factor_score.direction == TeamSide.NEUTRAL:
        return _no_edge(
            AnalysisMarket.ASIAN_HANDICAP,
            "FACTOR_SCORE_NO_DIRECTION",
            signal_strength=factor_score.strength,
        )
    tendency = _side_tendency(factor_score.direction)
    return MarketAnalysis(
        market=AnalysisMarket.ASIAN_HANDICAP,
        decision=AnalysisDecision.ANALYSIS_PICK,
        tendency=tendency,
        signal_strength=factor_score.strength,
        reasons=_factor_score_reasons(factor_score)
        + (f"庄家意图(参考,不驱动方向): {inputs.ah_intent.intent.value}",),
        risks=inputs.base_risks + ("评分构成因子随赛前信息更新可能变化。",),
        invalidation_conditions=("主力阵容突变", "评分构成因子发生变化"),
    )


def _ou_market(inputs: AnalysisBuildInputs) -> MarketAnalysis:
    if AnalysisMarket.TOTALS in inputs.missing_markets:
        return _skip(AnalysisMarket.TOTALS, "OU_DATA_UNAVAILABLE")
    if inputs.ou_intent.intent in {IntentSignal.LEAKAGE_BLOCKED, IntentSignal.INSUFFICIENT_DATA}:
        return _skip(AnalysisMarket.TOTALS, inputs.ou_intent.intent.value)
    return MarketAnalysis(
        market=AnalysisMarket.TOTALS,
        decision=AnalysisDecision.NO_EDGE,
        tendency=None,
        signal_strength=0.0,
        reasons=("市场观点展示 · 不作投注建议",),
        risks=inputs.base_risks,
        invalidation_conditions=("市场线或水位变化后重新查看",),
    )


def _assert_ou_intent_emits_no_positive_recommendation(market: MarketAnalysis) -> None:
    """Production-path tripwire (PR-4): the OU intent gate must never admit a pick.

    TOTALS is a market view only, so any ``ANALYSIS_PICK`` emitted for TOTALS
    means the intent gate has been re-enabled.  Fail closed rather than let a
    positive TOTALS recommendation escape the intent gate again.
    """
    if (
        market.market == AnalysisMarket.TOTALS
        and market.decision == AnalysisDecision.ANALYSIS_PICK
    ):
        raise AssertionError("OU_INTENT_GATE_POSITIVE_RECOMMENDATION_FORBIDDEN")


def _half_goal_market(inputs: AnalysisBuildInputs) -> MarketAnalysis:
    if AnalysisMarket.FIRST_HALF_GOALS in inputs.missing_markets or inputs.half_goals is None:
        return _skip(AnalysisMarket.FIRST_HALF_GOALS, "HALF_GOAL_INPUT_UNAVAILABLE")
    expected = (
        inputs.half_goals.expected_home_goals + inputs.half_goals.expected_away_goals
    ) * inputs.half_goals.first_half_share
    over_probability = 1.0 - math.exp(-expected)
    probability_edge = abs(over_probability - 0.5)
    if probability_edge < MIN_HALF_GOAL_PROBABILITY_EDGE:
        return _no_edge(
            AnalysisMarket.FIRST_HALF_GOALS,
            "HALF_GOAL_EDGE_INSUFFICIENT",
            signal_strength=round(probability_edge * 2, 4),
        )
    tendency = "1H_OVER" if over_probability >= 0.5 else "1H_UNDER"
    return MarketAnalysis(
        market=AnalysisMarket.FIRST_HALF_GOALS,
        decision=AnalysisDecision.ANALYSIS_PICK,
        tendency=tendency,
        signal_strength=round(abs(over_probability - 0.5) * 2, 4),
        reasons=(f"半场 Poisson 拆分 P(1H>0.5)={over_probability:.3f}",),
        risks=inputs.base_risks + ("半场模型是简化拆分，不代表精确比分。",),
        invalidation_conditions=("首发保守程度变化", "盘口未覆盖半场市场"),
    )


def _score_market(inputs: AnalysisBuildInputs) -> MarketAnalysis:
    if AnalysisMarket.SCORE in inputs.missing_markets:
        return _skip(AnalysisMarket.SCORE, "SCORE_MATRIX_UNAVAILABLE")
    if inputs.score_matrix is None or inputs.score_direction is None:
        return _skip(AnalysisMarket.SCORE, "SCORE_MATRIX_UNAVAILABLE")
    card = build_score_card(
        score_matrix=inputs.score_matrix,
        decision="MAIN",
        primary_direction=inputs.score_direction,
    )
    top_probability = max(
        (
            scenario.probability or 0.0
            for scenario in card.scenarios
        ),
        default=0.0,
    )
    if top_probability < MIN_SCORE_SCENARIO_PROBABILITY:
        return _no_edge(
            AnalysisMarket.SCORE,
            "SCORE_EDGE_INSUFFICIENT",
            signal_strength=round(top_probability, 4),
        )
    return MarketAnalysis(
        market=AnalysisMarket.SCORE,
        decision=AnalysisDecision.ANALYSIS_PICK,
        tendency=inputs.score_direction,
        signal_strength=round(top_probability, 4),
        reasons=("比分使用方向一致条件概率，不输出假精确。",),
        risks=inputs.base_risks + ("比分是分布解释，不是确定结果。",),
        invalidation_conditions=("方向桶变化", "完整 score_matrix 缺失"),
        score_card=card,
    )


def _skip(market: AnalysisMarket, reason: str) -> MarketAnalysis:
    return MarketAnalysis(
        market=market,
        decision=AnalysisDecision.SKIP,
        tendency=None,
        signal_strength=0.0,
        reasons=(reason,),
        risks=("数据不足时保持 SKIP。",),
        invalidation_conditions=("补齐 as-of 数据后重新评估",),
    )


def _no_edge(
    market: AnalysisMarket,
    reason: str,
    *,
    signal_strength: float,
) -> MarketAnalysis:
    return MarketAnalysis(
        market=market,
        decision=AnalysisDecision.NO_EDGE,
        tendency=None,
        signal_strength=round(max(min(signal_strength, 0.49), 0.0), 4),
        reasons=(reason,),
        risks=("信号强度不足时保持观察，不输出方向。",),
        invalidation_conditions=("盘口或模型分歧增强后重新评估",),
    )


def _feature_reasons(feature_set: FeatureSet) -> tuple[str, ...]:
    ready = [
        f"{item.feature_id}:{item.reason}"
        for item in feature_set.contributions
        if item.status == FeatureStatus.READY
    ]
    ready.sort(key=lambda item: (0 if item.startswith("F9_TRUE_XG:") else 1, item))
    return tuple(ready[:4]) if ready else ("FEATURES_INSUFFICIENT",)


def _side_tendency(side: TeamSide) -> str:
    if side == TeamSide.HOME:
        return "HOME_AH"
    if side == TeamSide.AWAY:
        return "AWAY_AH"
    return "NO_SIDE_EDGE"


def _factor_score_reasons(factor_score: FactorScore) -> tuple[str, ...]:
    if not factor_score.participants:
        return ("FACTOR_SCORE_NO_PARTICIPANTS",)
    ranked = sorted(factor_score.participants, key=lambda share: -share.share)
    shares = "、".join(f"{share.feature_id} {round(share.share * 100, 1)}%" for share in ranked)
    return (
        f"评分: 主 {factor_score.home_score} / 客 {factor_score.away_score}"
        f"(margin {factor_score.margin:+.4f}, {factor_score.participant_count} 项因子参与)",
        f"评分构成占比: {shares}",
    )


def _signal_strength(intent_strength: float, feature_set: FeatureSet) -> float:
    ready_count = sum(1 for item in feature_set.contributions if item.status == FeatureStatus.READY)
    coverage_bonus = min(ready_count / 10, 0.25)
    return round(min(intent_strength * 0.75 + coverage_bonus, 1.0), 4)


def _assert_compliant_text(*values: str) -> None:
    for value in values:
        if any(term in value for term in BANNED_OUTPUT_TERMS):
            raise ValueError("analysis output contains banned certainty wording")


def _assert_disclaimer(value: str) -> None:
    if value != DISCLAIMER:
        _assert_compliant_text(value)


def build_softmax_market_analyses(
    *,
    ah_selection: dict[str, Any] | None,
    ou_selection: dict[str, Any] | None,
    status: str,
    base_risks: tuple[str, ...] = ("阵容/伤停临场变化可能改变判断。",),
) -> tuple[MarketAnalysis, MarketAnalysis]:
    """Map ``build_ah_ou_selections`` output to the AH/OU ``MarketAnalysis`` pair.

    This is the new F9+F6 softmax path: AH direction follows the market and is
    admitted when ``selected`` (``|q-0.5| * support >= cutoff``); OU recommends
    OVER when ``selected`` (``factor_over_share - market_over_q >= threshold``).
    It runs *alongside* the legacy ``_ah_market``/``_ou_market`` and does not
    touch the legacy ``OU intent`` tripwire; the caller decides which path emits.
    """
    if ah_selection is None:
        ah_market = _skip(AnalysisMarket.ASIAN_HANDICAP, status)
    elif not ah_selection["selected"]:
        ah_market = _no_edge(
            AnalysisMarket.ASIAN_HANDICAP,
            "SOFTMAX_AH_NOT_SELECTED",
            signal_strength=round(ah_selection["score"], 4),
        )
    else:
        tendency = "HOME_AH" if ah_selection["side"] == "HOME" else "AWAY_AH"
        ah_market = MarketAnalysis(
            market=AnalysisMarket.ASIAN_HANDICAP,
            decision=AnalysisDecision.ANALYSIS_PICK,
            tendency=tendency,
            signal_strength=round(ah_selection["score"], 4),
            reasons=(
                f"F9+F6 软最大值选边 {ah_selection['side']}"
                f"(factor_home_cover_p={ah_selection['factor_home_cover_p']:.3f},"
                f" market_home_cover_p={ah_selection['market_home_cover_p']:.3f})",
            ),
            risks=base_risks + ("评分构成因子随赛前信息更新可能变化。",),
            invalidation_conditions=("主力阵容突变", "滚动快照或交锋样本更新"),
        )

    if ou_selection is None:
        ou_market = _skip(AnalysisMarket.TOTALS, status)
    elif not ou_selection["selected"]:
        ou_market = _no_edge(
            AnalysisMarket.TOTALS,
            "SOFTMAX_OU_NOT_SELECTED",
            signal_strength=round(max(ou_selection["edge"], 0.0), 4),
        )
    else:
        ou_market = MarketAnalysis(
            market=AnalysisMarket.TOTALS,
            decision=AnalysisDecision.ANALYSIS_PICK,
            tendency="OVER",
            signal_strength=round(ou_selection["edge"], 4),
            reasons=(
                f"F9+F6 软最大值 OVER 价值 factor_over_share={ou_selection['factor_over_share']:.3f}"
                f" > market_over_q={ou_selection['market_over_q']:.3f}"
                f" (edge={ou_selection['edge']:+.4f})",
            ),
            risks=base_risks + ("总进球模型是分布估计，不代表确定结果。",),
            invalidation_conditions=("总进球盘口线变化", "滚动快照或交锋样本更新"),
        )

    return ah_market, ou_market

