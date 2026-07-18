from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar, Literal

from w2.features.framework import FeatureSet, FeatureStatus, TeamSide
from w2.strategy.bookmaker_intent import BookmakerIntent, IntentSignal
from w2.strategy.score_card import ScoreCard, build_score_card
from w2.strategy.score_scenarios import Direction, ScoreMatrix

DISCLAIMER = "分析参考·非稳赢"
BANNED_OUTPUT_TERMS = ("稳赢", "必中", "保证")
MIN_INTENT_CONFIDENCE_FOR_PICK = 0.55
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
    confidence: float
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
    bookmaker_intent: BookmakerIntent
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
    ah_intent: BookmakerIntent
    ou_intent: BookmakerIntent
    feature_set: FeatureSet
    half_goals: HalfGoalModelInput | None
    score_matrix: ScoreMatrix | None
    score_direction: Direction | None
    missing_markets: frozenset[AnalysisMarket] = frozenset()
    base_risks: tuple[str, ...] = ("阵容/伤停临场变化可能改变判断。",)


def build_multi_market_analysis(
    *,
    fixture_id: str,
    inputs: AnalysisBuildInputs,
) -> MultiMarketAnalysisCard:
    markets = (
        _ah_market(inputs),
        _ou_market(inputs),
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
    )


def _ah_market(inputs: AnalysisBuildInputs) -> MarketAnalysis:
    if AnalysisMarket.ASIAN_HANDICAP in inputs.missing_markets:
        return _skip(AnalysisMarket.ASIAN_HANDICAP, "AH_DATA_UNAVAILABLE")
    if inputs.ah_intent.intent in {
        IntentSignal.INSUFFICIENT_DATA,
        IntentSignal.LEAKAGE_BLOCKED,
        IntentSignal.CONFLICTED,
    }:
        return _skip(AnalysisMarket.ASIAN_HANDICAP, inputs.ah_intent.intent.value)
    if inputs.ah_intent.confidence < MIN_INTENT_CONFIDENCE_FOR_PICK:
        return _no_edge(
            AnalysisMarket.ASIAN_HANDICAP,
            "AH_EDGE_INSUFFICIENT",
            confidence=inputs.ah_intent.confidence,
        )
    tendency = _side_tendency(inputs.ah_intent.implied_side)
    return MarketAnalysis(
        market=AnalysisMarket.ASIAN_HANDICAP,
        decision=AnalysisDecision.ANALYSIS_PICK,
        tendency=tendency,
        confidence=_confidence(inputs.ah_intent.confidence, inputs.feature_set),
        reasons=_feature_reasons(inputs.feature_set)
        + (f"庄家意图: {inputs.ah_intent.intent.value}",),
        risks=inputs.base_risks + ("让球盘对临场赔率变化敏感。",),
        invalidation_conditions=("主力阵容突变", "盘口进入 live 或暂停"),
    )


def _ou_market(inputs: AnalysisBuildInputs) -> MarketAnalysis:
    if AnalysisMarket.TOTALS in inputs.missing_markets:
        return _skip(AnalysisMarket.TOTALS, "OU_DATA_UNAVAILABLE")
    if inputs.ou_intent.intent in {IntentSignal.LEAKAGE_BLOCKED, IntentSignal.INSUFFICIENT_DATA}:
        return _skip(AnalysisMarket.TOTALS, inputs.ou_intent.intent.value)
    if inputs.ou_intent.confidence < MIN_INTENT_CONFIDENCE_FOR_PICK:
        return _no_edge(
            AnalysisMarket.TOTALS,
            "OU_EDGE_INSUFFICIENT",
            confidence=inputs.ou_intent.confidence,
        )
    tendency = "OVER" if inputs.ou_intent.intent == IntentSignal.OVER_LEAN else "UNDER"
    return MarketAnalysis(
        market=AnalysisMarket.TOTALS,
        decision=AnalysisDecision.ANALYSIS_PICK,
        tendency=tendency,
        confidence=_confidence(inputs.ou_intent.confidence, inputs.feature_set),
        reasons=_feature_reasons(inputs.feature_set)
        + (f"大小球意图: {inputs.ou_intent.intent.value}",),
        risks=inputs.base_risks + ("天气、红牌、早球会改变节奏。",),
        invalidation_conditions=("总进球盘口大幅跳线", "赛前 xG/阵容数据缺失"),
    )


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
            confidence=round(probability_edge * 2, 4),
        )
    tendency = "1H_OVER" if over_probability >= 0.5 else "1H_UNDER"
    return MarketAnalysis(
        market=AnalysisMarket.FIRST_HALF_GOALS,
        decision=AnalysisDecision.ANALYSIS_PICK,
        tendency=tendency,
        confidence=round(abs(over_probability - 0.5) * 2, 4),
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
            confidence=round(top_probability, 4),
        )
    return MarketAnalysis(
        market=AnalysisMarket.SCORE,
        decision=AnalysisDecision.ANALYSIS_PICK,
        tendency=inputs.score_direction,
        confidence=round(top_probability, 4),
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
        confidence=0.0,
        reasons=(reason,),
        risks=("数据不足时保持 SKIP。",),
        invalidation_conditions=("补齐 as-of 数据后重新评估",),
    )


def _no_edge(
    market: AnalysisMarket,
    reason: str,
    *,
    confidence: float,
) -> MarketAnalysis:
    return MarketAnalysis(
        market=market,
        decision=AnalysisDecision.NO_EDGE,
        tendency=None,
        confidence=round(max(min(confidence, 0.49), 0.0), 4),
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


def _confidence(intent_confidence: float, feature_set: FeatureSet) -> float:
    ready_count = sum(1 for item in feature_set.contributions if item.status == FeatureStatus.READY)
    coverage_bonus = min(ready_count / 10, 0.25)
    return round(min(intent_confidence * 0.75 + coverage_bonus, 1.0), 4)


def _assert_compliant_text(*values: str) -> None:
    for value in values:
        if any(term in value for term in BANNED_OUTPUT_TERMS):
            raise ValueError("analysis output contains banned certainty wording")


def _assert_disclaimer(value: str) -> None:
    if value != DISCLAIMER:
        _assert_compliant_text(value)
