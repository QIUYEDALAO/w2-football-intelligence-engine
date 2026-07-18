from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from numbers import Real
from typing import Literal

from w2.competitions.registry import CoverageProfile
from w2.features.framework import FeatureContext, FeatureStatus, TeamSide
from w2.features.market_factors import (
    BookmakerQuote,
    bookmaker_divergence_factor,
    market_movement_factor,
)
from w2.markets.movement import MarketSnapshot


class IntentSignal(StrEnum):
    HOME_LEAN = "HOME_LEAN"
    AWAY_LEAN = "AWAY_LEAN"
    OVER_LEAN = "OVER_LEAN"
    UNDER_LEAN = "UNDER_LEAN"
    BALANCED = "BALANCED"
    CONFLICTED = "CONFLICTED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    LEAKAGE_BLOCKED = "LEAKAGE_BLOCKED"


class IntentComponent(StrEnum):
    OPEN_TO_CURRENT = "OPEN_TO_CURRENT"
    LATE_REVERSAL = "LATE_REVERSAL"
    BOOKMAKER_DIVERGENCE = "BOOKMAKER_DIVERGENCE"
    SHARP_SOFT_DIVERGENCE = "SHARP_SOFT_DIVERGENCE"


MarketKind = Literal["AH", "OU", "ONE_X_TWO"]


@dataclass(frozen=True, kw_only=True)
class BookmakerIntentPolicy:
    open_move_unit: float = 0.25
    late_reversal_threshold: float = 0.08
    high_divergence_threshold: float = 0.18
    sharp_soft_threshold: float = 0.06
    min_signal_strength: float = 0.15


@dataclass(frozen=True, kw_only=True)
class IntentEvidence:
    component: IntentComponent
    score: float
    reason: str
    observed_at: datetime | None = None
    diagnostics: tuple[str, ...] = ()
    inputs: dict[str, float | int | str | None] = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class BookmakerIntent:
    fixture_id: str
    market_kind: MarketKind
    intent: IntentSignal
    signal_strength: float
    implied_side: TeamSide
    reason: str
    evidence: tuple[IntentEvidence, ...]
    candidate: Literal[False] = False
    formal_recommendation: Literal[False] = False

    def as_dict(self) -> dict[str, object]:
        return {
            "fixture_id": self.fixture_id,
            "market_kind": self.market_kind,
            "intent": self.intent.value,
            "signal_strength": self.signal_strength,
            "implied_side": self.implied_side.value,
            "reason": self.reason,
            "evidence": [
                {
                    "component": item.component.value,
                    "score": item.score,
                    "reason": item.reason,
                    "observed_at": item.observed_at.isoformat()
                    if item.observed_at is not None
                    else None,
                    "diagnostics": list(item.diagnostics),
                    "inputs": item.inputs,
                }
                for item in self.evidence
            ],
            "candidate": False,
            "formal_recommendation": False,
        }


def infer_bookmaker_intent(
    *,
    context: FeatureContext,
    profile: CoverageProfile,
    market_kind: MarketKind,
    snapshots: list[MarketSnapshot],
    quotes: list[BookmakerQuote],
    policy: BookmakerIntentPolicy | None = None,
) -> BookmakerIntent:
    resolved = policy or BookmakerIntentPolicy()
    movement = market_movement_factor(context=context, profile=profile, snapshots=snapshots)
    divergence = bookmaker_divergence_factor(context=context, profile=profile, quotes=quotes)
    if (
        movement.status == FeatureStatus.LEAKAGE_BLOCKED
        or divergence.status == FeatureStatus.LEAKAGE_BLOCKED
    ):
        return _terminal_intent(
            context=context,
            market_kind=market_kind,
            intent=IntentSignal.LEAKAGE_BLOCKED,
            reason="AS_OF_LEAKAGE_BLOCKED",
        )
    evidence: list[IntentEvidence] = []
    open_move = _float_input(movement.inputs, "first_seen_to_current")
    if movement.status == FeatureStatus.READY and open_move is not None:
        open_score = _directional_score(-open_move, resolved.open_move_unit)
        evidence.append(
            IntentEvidence(
                component=IntentComponent.OPEN_TO_CURRENT,
                score=open_score,
                reason="OPEN_TO_CURRENT_DIRECTION",
                observed_at=movement.observed_at,
                diagnostics=movement.diagnostics,
                inputs={"first_seen_to_current": open_move},
            )
        )
    recent_move = _float_input(movement.inputs, "recent_move")
    if (
        open_move is not None
        and recent_move is not None
        and abs(recent_move) >= resolved.late_reversal_threshold
    ):
        open_direction = _sign(-open_move)
        recent_direction = _sign(-recent_move)
        if open_direction and recent_direction and open_direction != recent_direction:
            evidence.append(
                IntentEvidence(
                    component=IntentComponent.LATE_REVERSAL,
                    score=recent_direction * min(abs(recent_move) / resolved.open_move_unit, 1.0),
                    reason="LATE_REVERSAL_AGAINST_OPEN_MOVE",
                    observed_at=movement.observed_at,
                    inputs={"recent_move": recent_move, "open_move": open_move},
                )
            )
    dispersion = _float_input(divergence.inputs, "dispersion")
    if dispersion is not None and dispersion >= resolved.high_divergence_threshold:
        evidence.append(
            IntentEvidence(
                component=IntentComponent.BOOKMAKER_DIVERGENCE,
                score=0.0,
                reason="HIGH_BOOKMAKER_DIVERGENCE",
                observed_at=divergence.observed_at,
                diagnostics=divergence.diagnostics,
                inputs={
                    "dispersion": dispersion,
                    "effective_bookmakers": _int_input(divergence.inputs, "effective_bookmakers"),
                },
            )
        )
    sharp_soft_gap = _float_input(divergence.inputs, "sharp_soft_gap")
    if sharp_soft_gap is not None and abs(sharp_soft_gap) >= resolved.sharp_soft_threshold:
        evidence.append(
            IntentEvidence(
                component=IntentComponent.SHARP_SOFT_DIVERGENCE,
                score=_directional_score(-sharp_soft_gap, resolved.sharp_soft_threshold * 2),
                reason="SHARP_SOFT_PRICE_GAP",
                observed_at=divergence.observed_at,
                inputs={"sharp_soft_gap": sharp_soft_gap},
            )
        )
    if not evidence:
        return _terminal_intent(
            context=context,
            market_kind=market_kind,
            intent=IntentSignal.INSUFFICIENT_DATA,
            reason="INTENT_INPUTS_INSUFFICIENT",
        )
    directional = [
        item.score
        for item in evidence
        if item.component != IntentComponent.BOOKMAKER_DIVERGENCE
    ]
    net = sum(directional) / max(len(directional), 1)
    has_high_divergence = any(
        item.component == IntentComponent.BOOKMAKER_DIVERGENCE for item in evidence
    )
    signal_strength = min(abs(net) * (0.75 if has_high_divergence else 1.0), 1.0)
    if has_high_divergence and signal_strength < 0.45:
        intent = IntentSignal.CONFLICTED
        side = TeamSide.NEUTRAL
        reason = "MARKET_DIVERGENCE_CONFLICTS_WITH_DIRECTION"
    elif signal_strength < resolved.min_signal_strength:
        intent = IntentSignal.BALANCED
        side = TeamSide.NEUTRAL
        reason = "NO_CLEAR_BOOKMAKER_LEAN"
    else:
        side = TeamSide.HOME if net > 0 else TeamSide.AWAY
        intent = _intent_for_side(market_kind, side)
        reason = "BOOKMAKER_INTENT_INFERRED_FROM_CAPTURED_MARKET_EVOLUTION"
    return BookmakerIntent(
        fixture_id=context.fixture_id,
        market_kind=market_kind,
        intent=intent,
        signal_strength=round(signal_strength, 4),
        implied_side=side,
        reason=reason,
        evidence=tuple(evidence),
    )


def _terminal_intent(
    *,
    context: FeatureContext,
    market_kind: MarketKind,
    intent: IntentSignal,
    reason: str,
) -> BookmakerIntent:
    return BookmakerIntent(
        fixture_id=context.fixture_id,
        market_kind=market_kind,
        intent=intent,
        signal_strength=0.0,
        implied_side=TeamSide.NEUTRAL,
        reason=reason,
        evidence=(),
    )


def _directional_score(value: float, unit: float) -> float:
    return max(min(value / max(unit, 1e-9), 1.0), -1.0)


def _sign(value: float) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def _intent_for_side(market_kind: MarketKind, side: TeamSide) -> IntentSignal:
    if market_kind == "OU":
        return IntentSignal.OVER_LEAN if side == TeamSide.HOME else IntentSignal.UNDER_LEAN
    return IntentSignal.HOME_LEAN if side == TeamSide.HOME else IntentSignal.AWAY_LEAN


def _float_input(inputs: dict[str, object], key: str) -> float | None:
    value = inputs.get(key)
    if value is None:
        return None
    if isinstance(value, Real):
        return float(value)
    if isinstance(value, str):
        return float(value)
    raise TypeError(f"{key} must be numeric")


def _int_input(inputs: dict[str, object], key: str) -> int | None:
    value = inputs.get(key)
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, Real):
        return int(float(value))
    if isinstance(value, str):
        return int(value)
    raise TypeError(f"{key} must be integer-like")
