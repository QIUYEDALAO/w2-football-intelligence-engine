from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

Direction = Literal["HOME", "DRAW", "AWAY"]
AnalysisDecision = Literal["NOT_READY", "SKIP", "WATCH", "ANALYSIS_PICK", "RECOMMEND"]

DISCLAIMER = "分析参考，非保证盈利"


class FactorName(StrEnum):
    MARKET_MOVEMENT = "MARKET_MOVEMENT"
    RECENT_FORM = "RECENT_FORM"
    GOAL_RATE = "GOAL_RATE"
    FITNESS = "FITNESS"
    AH_COVER_RATE = "AH_COVER_RATE"
    H2H = "H2H"
    TEAM_VALUE = "TEAM_VALUE"
    INDEPENDENT_MODEL_COMPARE = "INDEPENDENT_MODEL_COMPARE"


class FactorStatus(StrEnum):
    READY = "READY"
    UNAVAILABLE = "UNAVAILABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    LEAKAGE_BLOCKED = "LEAKAGE_BLOCKED"


@dataclass(frozen=True, kw_only=True)
class AnalysisPolicy:
    factor_weights: dict[FactorName, float] | None = None
    minimum_ready_weight: float = 0.55
    watch_threshold: float = 0.12
    pick_threshold: float = 0.28

    def weights(self) -> dict[FactorName, float]:
        return self.factor_weights or {
            FactorName.MARKET_MOVEMENT: 0.20,
            FactorName.RECENT_FORM: 0.18,
            FactorName.GOAL_RATE: 0.18,
            FactorName.FITNESS: 0.12,
            FactorName.AH_COVER_RATE: 0.07,
            FactorName.H2H: 0.05,
            FactorName.TEAM_VALUE: 0.05,
            FactorName.INDEPENDENT_MODEL_COMPARE: 0.15,
        }


@dataclass(frozen=True, kw_only=True)
class FactorSignal:
    name: FactorName
    status: FactorStatus
    score: float
    observed_at: datetime | None
    reason: str
    risk: str | None = None


@dataclass(frozen=True, kw_only=True)
class TeamComparisonSignal:
    home: float
    away: float
    observed_at: datetime
    reason: str
    risk: str | None = None


@dataclass(frozen=True, kw_only=True)
class MarketMovementSignal:
    home_direction_price_move: float
    away_direction_price_move: float
    observed_at: datetime
    reverse_late_move: bool = False
    reason: str = "盘口变化已按 as-of 快照计算"


@dataclass(frozen=True, kw_only=True)
class ModelMarketSignal:
    model_probabilities: dict[Direction, float]
    market_probabilities: dict[Direction, float]
    observed_at: datetime
    reason: str = "独立模型概率仅作为与市场的解释性对比因素"


@dataclass(frozen=True, kw_only=True)
class AnalysisInput:
    fixture_id: str
    as_of: datetime
    kickoff_utc: datetime
    market_movement: MarketMovementSignal | None = None
    recent_form: TeamComparisonSignal | None = None
    goal_rate: TeamComparisonSignal | None = None
    fitness: TeamComparisonSignal | None = None
    ah_cover_rate: TeamComparisonSignal | None = None
    h2h: TeamComparisonSignal | None = None
    team_value: TeamComparisonSignal | None = None
    model_market: ModelMarketSignal | None = None


@dataclass(frozen=True, kw_only=True)
class FactorContribution:
    name: FactorName
    status: FactorStatus
    score: float
    weight: float
    weighted_score: float
    reason: str
    risk: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name.value,
            "status": self.status.value,
            "score": round(self.score, 6),
            "weight": self.weight,
            "weighted_score": round(self.weighted_score, 6),
            "reason": self.reason,
            "risk": self.risk,
        }


@dataclass(frozen=True, kw_only=True)
class AnalysisCard:
    fixture_id: str
    decision: AnalysisDecision
    primary_direction: Direction | None
    analysis_score: float
    confidence: str
    factors: tuple[FactorContribution, ...]
    reasons: tuple[str, ...]
    risks: tuple[str, ...]
    disclaimer: str = DISCLAIMER
    candidate: Literal[False] = False
    formal_recommendation: Literal[False] = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "W2_ANALYSIS_CARD_V1",
            "fixture_id": self.fixture_id,
            "decision": self.decision,
            "primary_direction": self.primary_direction,
            "analysis_score": round(self.analysis_score, 6),
            "confidence": self.confidence,
            "factors": [factor.as_dict() for factor in self.factors],
            "reasons": list(self.reasons),
            "risks": list(self.risks),
            "disclaimer": self.disclaimer,
            "candidate": False,
            "formal_recommendation": False,
        }


def parse_utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


def clamp(value: float, lower: float = -1.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def comparison_score(signal: TeamComparisonSignal) -> float:
    denominator = max(abs(signal.home), abs(signal.away), 1.0)
    return clamp((signal.home - signal.away) / denominator)


def model_market_score(signal: ModelMarketSignal) -> float:
    home_delta = signal.model_probabilities.get("HOME", 0.0) - signal.market_probabilities.get(
        "HOME", 0.0
    )
    away_delta = signal.model_probabilities.get("AWAY", 0.0) - signal.market_probabilities.get(
        "AWAY", 0.0
    )
    return clamp((home_delta - away_delta) * 4)


def movement_score(signal: MarketMovementSignal) -> float:
    raw = signal.away_direction_price_move - signal.home_direction_price_move
    if signal.reverse_late_move:
        raw *= 0.5
    return clamp(raw * 3)


def unavailable(name: FactorName, reason: str, risk: str | None = None) -> FactorSignal:
    return FactorSignal(
        name=name,
        status=FactorStatus.UNAVAILABLE,
        score=0.0,
        observed_at=None,
        reason=reason,
        risk=risk,
    )


def _signals(input_data: AnalysisInput) -> tuple[FactorSignal, ...]:
    signals: list[FactorSignal] = []
    if input_data.market_movement is None:
        signals.append(
            unavailable(
                FactorName.MARKET_MOVEMENT,
                "盘口变化数据不足，默认不放大倾向",
                "缺少开盘到当前的 as-of 盘口序列",
            )
        )
    else:
        signals.append(
            FactorSignal(
                name=FactorName.MARKET_MOVEMENT,
                status=FactorStatus.READY,
                score=movement_score(input_data.market_movement),
                observed_at=input_data.market_movement.observed_at,
                reason=input_data.market_movement.reason,
                risk=(
                    "临场反向移动已降权"
                    if input_data.market_movement.reverse_late_move
                    else "盘口变化可能反映市场共识而非独立优势"
                ),
            )
        )
    for name, signal in (
        (FactorName.RECENT_FORM, input_data.recent_form),
        (FactorName.GOAL_RATE, input_data.goal_rate),
        (FactorName.FITNESS, input_data.fitness),
        (FactorName.AH_COVER_RATE, input_data.ah_cover_rate),
        (FactorName.H2H, input_data.h2h),
        (FactorName.TEAM_VALUE, input_data.team_value),
    ):
        if signal is None:
            reason = (
                "VALUE_DATA_UNAVAILABLE"
                if name == FactorName.TEAM_VALUE
                else "H2H_UNAVAILABLE"
                if name == FactorName.H2H
                else f"{name.value}_UNAVAILABLE"
            )
            signals.append(unavailable(name, reason, "数据缺失时该因素按 0 贡献处理"))
            continue
        signals.append(
            FactorSignal(
                name=name,
                status=FactorStatus.READY,
                score=comparison_score(signal),
                observed_at=signal.observed_at,
                reason=signal.reason,
                risk=signal.risk,
            )
        )
    if input_data.model_market is None:
        signals.append(
            unavailable(
                FactorName.INDEPENDENT_MODEL_COMPARE,
                "INDEPENDENT_MODEL_COMPARE_UNAVAILABLE",
                "独立模型不作为打赢市场证明，仅作解释性对比",
            )
        )
    else:
        signals.append(
            FactorSignal(
                name=FactorName.INDEPENDENT_MODEL_COMPARE,
                status=FactorStatus.READY,
                score=model_market_score(input_data.model_market),
                observed_at=input_data.model_market.observed_at,
                reason=input_data.model_market.reason,
                risk="模型概率未经 +EV 证明，不能升级为正式推荐",
            )
        )
    return tuple(signals)


def build_analysis_card(
    input_data: AnalysisInput,
    *,
    policy: AnalysisPolicy | None = None,
) -> AnalysisCard:
    resolved_policy = policy or AnalysisPolicy()
    weights = resolved_policy.weights()
    as_of = parse_utc(input_data.as_of)
    kickoff = parse_utc(input_data.kickoff_utc)
    factors: list[FactorContribution] = []
    risks: list[str] = []
    blockers: list[str] = []

    if kickoff <= as_of:
        blockers.append("KICKOFF_PASSED")

    for signal in _signals(input_data):
        status = signal.status
        if signal.observed_at is not None and parse_utc(signal.observed_at) > as_of:
            status = FactorStatus.LEAKAGE_BLOCKED
            risks.append(f"{signal.name.value}: observed_at after as_of blocked")
        weight = weights[signal.name]
        weighted = signal.score * weight if status == FactorStatus.READY else 0.0
        if signal.risk:
            risks.append(f"{signal.name.value}: {signal.risk}")
        factors.append(
            FactorContribution(
                name=signal.name,
                status=status,
                score=signal.score if status == FactorStatus.READY else 0.0,
                weight=weight,
                weighted_score=weighted,
                reason=signal.reason,
                risk=signal.risk,
            )
        )

    ready_weight = sum(factor.weight for factor in factors if factor.status == FactorStatus.READY)
    total_score = sum(factor.weighted_score for factor in factors)
    normalized_score = total_score / ready_weight if ready_weight else 0.0
    abs_score = abs(normalized_score)
    primary_direction: Direction | None = (
        "HOME" if normalized_score > 0 else "AWAY" if normalized_score < 0 else None
    )

    if blockers:
        decision: AnalysisDecision = "SKIP"
        reasons = tuple(blockers)
        primary_direction = None
    elif ready_weight < resolved_policy.minimum_ready_weight:
        decision = "SKIP"
        reasons = ("INSUFFICIENT_READY_FACTOR_WEIGHT",)
        primary_direction = None
    elif abs_score >= resolved_policy.pick_threshold and primary_direction is not None:
        decision = "ANALYSIS_PICK"
        reasons = tuple(
            factor.reason
            for factor in sorted(factors, key=lambda item: abs(item.weighted_score), reverse=True)
            if factor.status == FactorStatus.READY
        )[:4]
    elif abs_score >= resolved_policy.watch_threshold and primary_direction is not None:
        decision = "WATCH"
        reasons = tuple(
            factor.reason
            for factor in sorted(factors, key=lambda item: abs(item.weighted_score), reverse=True)
            if factor.status == FactorStatus.READY
        )[:3]
    else:
        decision = "SKIP"
        reasons = ("NO_CLEAR_ANALYSIS_LEAN",)
        primary_direction = None

    confidence = (
        "LOW"
        if ready_weight < 0.70
        else "MEDIUM"
        if abs_score < resolved_policy.pick_threshold
        else "HIGH_ATTENTION_NOT_PROFIT_CLAIM"
    )
    return AnalysisCard(
        fixture_id=input_data.fixture_id,
        decision=decision,
        primary_direction=primary_direction,
        analysis_score=normalized_score,
        confidence=confidence,
        factors=tuple(factors),
        reasons=reasons,
        risks=tuple(dict.fromkeys(risks)),
    )
