from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any

from w2.domain.enums import MarketType
from w2.markets.value_engine import (
    MarketValueEngine,
    OddsQuote,
    SettlementDistribution,
)

SHADOW_STRATEGY_VERSION = "W2_SHADOW_STRATEGY_V1"
PUBLIC_DECISIONS = {"NOT_READY", "SKIP", "WATCH"}
FORBIDDEN_PUBLIC_STATES = {"CANDIDATE", "RECOMMEND"}


class ShadowAction(StrEnum):
    SHADOW_NOT_READY = "SHADOW_NOT_READY"
    SHADOW_SKIP = "SHADOW_SKIP"
    SHADOW_WATCH = "SHADOW_WATCH"
    SHADOW_LOCKED = "SHADOW_LOCKED"
    SHADOW_VOID = "SHADOW_VOID"
    SHADOW_SETTLED = "SHADOW_SETTLED"


class StrategyReason(StrEnum):
    READY = "READY"
    KICKOFF_PASSED = "KICKOFF_PASSED"
    STALE_QUOTE = "STALE_QUOTE"
    LIVE_QUOTE = "LIVE_QUOTE"
    SUSPENDED_QUOTE = "SUSPENDED_QUOTE"
    OUTLIER_QUOTE = "OUTLIER_QUOTE"
    BOOKMAKER_MIN_NOT_MET = "BOOKMAKER_MIN_NOT_MET"
    SAME_LINE_PAIR_INVALID = "SAME_LINE_PAIR_INVALID"
    MODEL_PROBABILITY_MISSING = "MODEL_PROBABILITY_MISSING"
    CALIBRATION_MISSING = "CALIBRATION_MISSING"
    SETTLEMENT_RULE_MISSING = "SETTLEMENT_RULE_MISSING"
    PRICE_BELOW_ADJUSTED_MINIMUM = "PRICE_BELOW_ADJUSTED_MINIMUM"
    NON_POSITIVE_RISK_ADJUSTED_EV = "NON_POSITIVE_RISK_ADJUSTED_EV"
    CORRELATION_POLICY_INSUFFICIENT = "CORRELATION_POLICY_INSUFFICIENT"
    GATE4_PUBLISHED_GRADE_CAP = "GATE4_PUBLISHED_GRADE_CAP"


class StrategyRiskFlag(StrEnum):
    GATE4_PENDING = "GATE4_PENDING"
    SHADOW_ONLY = "SHADOW_ONLY"
    SECONDARY_SUPPRESSED = "SECONDARY_SUPPRESSED"
    DATA_QUALITY_WARNING = "DATA_QUALITY_WARNING"
    MARKET_QUALITY_WARNING = "MARKET_QUALITY_WARNING"


@dataclass(frozen=True, kw_only=True)
class StrategyInput:
    fixture_id: str
    phase: str
    kickoff_utc: datetime
    as_of_time: datetime
    score_matrix: dict[tuple[int, int], Decimal]
    independent_probabilities: dict[str, Decimal]
    quotes: list[OddsQuote]
    most_likely_outcome: str
    data_quality: str = "READY"
    market_quality: str = "READY"
    gate4_status: str = "PROVISIONAL_FORWARD_HOLDOUT_PENDING"
    model_version: str = "STAGE7B_FROZEN_CHALLENGER"
    calibration_version: str = "STAGE7B_FROZEN_CALIBRATION"
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True, kw_only=True)
class MarketOpportunity:
    market: MarketType
    selection: str
    line: Decimal | None
    bookmaker: str
    executable_odds: Decimal
    model_fair_odds: Decimal | None
    adjusted_minimum_odds: Decimal | None
    market_no_vig_odds: Decimal | None
    raw_ev: Decimal | None
    total_penalty: Decimal
    risk_adjusted_ev: Decimal | None
    price_margin_above_minimum: Decimal | None
    settlement_distribution: SettlementDistribution
    raw_grade: str
    published_grade: str
    hard_gate_reasons: tuple[StrategyReason, ...]
    risk_flags: tuple[StrategyRiskFlag, ...]
    executable: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "market": self.market.value,
            "selection": self.selection,
            "line": str(self.line) if self.line is not None else None,
            "bookmaker": self.bookmaker,
            "executable_odds": str(self.executable_odds),
            "model_fair_odds": str(self.model_fair_odds) if self.model_fair_odds else None,
            "adjusted_minimum_odds": str(self.adjusted_minimum_odds)
            if self.adjusted_minimum_odds
            else None,
            "market_no_vig_odds": str(self.market_no_vig_odds)
            if self.market_no_vig_odds
            else None,
            "raw_ev": str(self.raw_ev) if self.raw_ev is not None else None,
            "total_penalty": str(self.total_penalty),
            "risk_adjusted_ev": str(self.risk_adjusted_ev)
            if self.risk_adjusted_ev is not None
            else None,
            "price_margin_above_minimum": str(self.price_margin_above_minimum)
            if self.price_margin_above_minimum is not None
            else None,
            "settlement_distribution": self.settlement_distribution.as_dict(),
            "raw_grade": self.raw_grade,
            "published_grade": self.published_grade,
            "hard_gate_reasons": [reason.value for reason in self.hard_gate_reasons],
            "risk_flags": [flag.value for flag in self.risk_flags],
            "executable": self.executable,
        }


@dataclass(frozen=True, kw_only=True)
class StrategyCandidate:
    opportunity: MarketOpportunity
    rank: int
    role: str

    def as_dict(self) -> dict[str, Any]:
        return {"rank": self.rank, "role": self.role, **self.opportunity.as_dict()}


@dataclass(frozen=True, kw_only=True)
class StrategyDecision:
    fixture_id: str
    phase: str
    strategy_version: str
    most_likely_outcome: str
    primary: StrategyCandidate | None
    secondary: StrategyCandidate | None
    shadow_action: ShadowAction
    public_decision: str
    raw_grade: str
    published_grade: str
    participation_advice: str
    skip_reasons: tuple[StrategyReason, ...]
    supporting_factors: tuple[str, ...]
    opposing_factors: tuple[str, ...]
    invalidation_conditions: tuple[str, ...]
    formal_recommendation: bool = False
    candidate: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "fixture_id": self.fixture_id,
            "phase": self.phase,
            "strategy_version": self.strategy_version,
            "most_likely_outcome": self.most_likely_outcome,
            "primary": self.primary.as_dict() if self.primary else None,
            "secondary": self.secondary.as_dict() if self.secondary else None,
            "shadow_action": self.shadow_action.value,
            "public_decision": self.public_decision,
            "raw_grade": self.raw_grade,
            "published_grade": self.published_grade,
            "participation_advice": self.participation_advice,
            "skip_reasons": [reason.value for reason in self.skip_reasons],
            "supporting_factors": list(self.supporting_factors),
            "opposing_factors": list(self.opposing_factors),
            "invalidation_conditions": list(self.invalidation_conditions),
            "formal_recommendation": self.formal_recommendation,
            "candidate": self.candidate,
            "created_at": self.created_at.isoformat().replace("+00:00", "Z"),
        }
        validate_public_payload(payload)
        return payload


@dataclass(frozen=True, kw_only=True)
class StrategyLock:
    fixture_id: str
    phase: str
    strategy_version: str
    decision_hash: str
    locked_at: datetime


@dataclass(frozen=True, kw_only=True)
class StrategySupersessionEvent:
    fixture_id: str
    event_time: datetime
    old_decision_hash: str
    new_decision_hash: str
    reason: str


@dataclass(frozen=True, kw_only=True)
class StrategySettlement:
    fixture_id: str
    settled_at: datetime
    primary_outcome: str | None
    secondary_outcome: str | None


@dataclass(frozen=True, kw_only=True)
class StrategyEvaluation:
    fixture_id: str
    evaluated_at: datetime
    log_loss: Decimal | None
    rps: Decimal | None
    brier: Decimal | None


class StrategyCorrelationController:
    def __init__(self, *, threshold: Decimal | None) -> None:
        self.threshold = threshold

    def choose_secondary(
        self,
        primary: StrategyCandidate | None,
        alternatives: list[StrategyCandidate],
    ) -> tuple[StrategyCandidate | None, StrategyReason | None]:
        if primary is None:
            return None, None
        if self.threshold is None:
            return None, StrategyReason.CORRELATION_POLICY_INSUFFICIENT
        for candidate in alternatives:
            if candidate.opportunity.market != primary.opportunity.market:
                return candidate, None
        return None, StrategyReason.CORRELATION_POLICY_INSUFFICIENT


class ShadowStrategyEngine:
    def __init__(
        self,
        *,
        uncertainty_penalty: Decimal = Decimal("0.035"),
        data_quality_penalty: Decimal = Decimal("0.010"),
        market_quality_penalty: Decimal = Decimal("0.010"),
        outlier_penalty: Decimal = Decimal("0.050"),
        correlation_threshold: Decimal | None = None,
    ) -> None:
        self.value_engine = MarketValueEngine(uncertainty_margin=uncertainty_penalty)
        self.uncertainty_penalty = uncertainty_penalty
        self.data_quality_penalty = data_quality_penalty
        self.market_quality_penalty = market_quality_penalty
        self.outlier_penalty = outlier_penalty
        self.correlation = StrategyCorrelationController(threshold=correlation_threshold)

    def evaluate(self, strategy_input: StrategyInput) -> StrategyDecision:
        if strategy_input.as_of_time >= strategy_input.kickoff_utc:
            return self._blocked_decision(strategy_input, StrategyReason.KICKOFF_PASSED)

        market_candidates = self.value_engine.evaluate(
            score_matrix=strategy_input.score_matrix,
            independent_probabilities=strategy_input.independent_probabilities,
            quotes=strategy_input.quotes,
            data_quality=strategy_input.data_quality,
            market_quality=strategy_input.market_quality,
            gate4_pending=True,
        )
        opportunities = [self._opportunity(candidate) for candidate in market_candidates]
        ranked = [
            StrategyCandidate(opportunity=opportunity, rank=index + 1, role="PRIMARY")
            for index, opportunity in enumerate(opportunities)
            if opportunity.executable
        ]
        primary = ranked[0] if ranked else None
        secondary, correlation_reason = self.correlation.choose_secondary(primary, ranked[1:])
        if secondary is not None:
            secondary = StrategyCandidate(
                opportunity=secondary.opportunity,
                rank=secondary.rank,
                role="SECONDARY",
            )

        skip_reasons: list[StrategyReason] = []
        if primary is None:
            skip_reasons.append(StrategyReason.NON_POSITIVE_RISK_ADJUSTED_EV)
        if correlation_reason is not None:
            skip_reasons.append(correlation_reason)

        raw_grade = primary.opportunity.raw_grade if primary else "D"
        published_grade = primary.opportunity.published_grade if primary else "D"
        action = ShadowAction.SHADOW_WATCH if primary else ShadowAction.SHADOW_SKIP
        public = "WATCH" if primary else "SKIP"
        decision = StrategyDecision(
            fixture_id=strategy_input.fixture_id,
            phase=strategy_input.phase,
            strategy_version=SHADOW_STRATEGY_VERSION,
            most_likely_outcome=strategy_input.most_likely_outcome,
            primary=primary,
            secondary=secondary,
            shadow_action=action,
            public_decision=public,
            raw_grade=raw_grade,
            published_grade=published_grade,
            participation_advice="SHADOW_ONLY_DO_NOT_PUBLISH_AS_FORMAL",
            skip_reasons=tuple(skip_reasons),
            supporting_factors=(
                "Price passed adjusted minimum odds" if primary else "No positive shadow price",
                "Gate 4 pending cap applied",
            ),
            opposing_factors=(
                "Formal recommendation disabled",
                "Shadow strategy requires future holdout validation",
            ),
            invalidation_conditions=(
                "Kickoff passed",
                "Quote becomes stale/live/suspended",
                "Frozen model or calibration hash changes",
            ),
        )
        validate_public_payload(decision.as_dict())
        return decision

    def _blocked_decision(
        self,
        strategy_input: StrategyInput,
        reason: StrategyReason,
    ) -> StrategyDecision:
        return StrategyDecision(
            fixture_id=strategy_input.fixture_id,
            phase=strategy_input.phase,
            strategy_version=SHADOW_STRATEGY_VERSION,
            most_likely_outcome=strategy_input.most_likely_outcome,
            primary=None,
            secondary=None,
            shadow_action=ShadowAction.SHADOW_NOT_READY,
            public_decision="NOT_READY",
            raw_grade="X",
            published_grade="X",
            participation_advice="SHADOW_BLOCKED",
            skip_reasons=(reason,),
            supporting_factors=(),
            opposing_factors=(reason.value,),
            invalidation_conditions=("Re-run before kickoff with valid inputs",),
        )

    def _opportunity(self, candidate: Any) -> MarketOpportunity:
        distribution = candidate.settlement_distribution
        total_penalty = self.uncertainty_penalty
        if candidate.data_quality != "READY":
            total_penalty += self.data_quality_penalty
        if candidate.market_quality != "READY":
            total_penalty += self.market_quality_penalty
        try:
            adjusted_minimum = adjusted_minimum_odds(distribution, total_penalty)
            price_margin: Decimal | None = candidate.executable_odds - adjusted_minimum
        except ValueError:
            adjusted_minimum = None
            price_margin = None
        hard_gates: list[StrategyReason] = []
        if adjusted_minimum is None or price_margin is None or price_margin < 0:
            hard_gates.append(StrategyReason.PRICE_BELOW_ADJUSTED_MINIMUM)
        if candidate.risk_adjusted_ev is None or candidate.risk_adjusted_ev <= 0:
            hard_gates.append(StrategyReason.NON_POSITIVE_RISK_ADJUSTED_EV)
        if candidate.data_quality == "BLOCKED":
            hard_gates.append(StrategyReason.MODEL_PROBABILITY_MISSING)
        flags = [StrategyRiskFlag.GATE4_PENDING, StrategyRiskFlag.SHADOW_ONLY]
        if candidate.data_quality != "READY":
            flags.append(StrategyRiskFlag.DATA_QUALITY_WARNING)
        if candidate.market_quality != "READY":
            flags.append(StrategyRiskFlag.MARKET_QUALITY_WARNING)
        return MarketOpportunity(
            market=candidate.market_type,
            selection=candidate.selection,
            line=candidate.line,
            bookmaker=candidate.bookmaker,
            executable_odds=candidate.executable_odds,
            model_fair_odds=candidate.model_fair_odds,
            adjusted_minimum_odds=adjusted_minimum,
            market_no_vig_odds=candidate.market_no_vig_odds,
            raw_ev=candidate.raw_ev,
            total_penalty=total_penalty,
            risk_adjusted_ev=candidate.risk_adjusted_ev,
            price_margin_above_minimum=price_margin,
            settlement_distribution=distribution,
            raw_grade=candidate.raw_research_grade,
            published_grade=candidate.published_grade,
            hard_gate_reasons=tuple(hard_gates),
            risk_flags=tuple(flags),
            executable=not hard_gates,
        )


class ShadowStrategyLedger:
    def __init__(self) -> None:
        self._locks: dict[tuple[str, str, str], StrategyLock] = {}
        self.events: list[dict[str, Any]] = []

    def lock(self, decision: StrategyDecision) -> StrategyLock:
        key = (decision.fixture_id, decision.phase, decision.strategy_version)
        digest = stable_sha256(decision.as_dict())
        existing = self._locks.get(key)
        if existing is not None:
            if existing.decision_hash != digest:
                raise ValueError("SHADOW_LOCK_IMMUTABILITY_VIOLATION")
            return existing
        lock = StrategyLock(
            fixture_id=decision.fixture_id,
            phase=decision.phase,
            strategy_version=decision.strategy_version,
            decision_hash=digest,
            locked_at=datetime.now(UTC),
        )
        self._locks[key] = lock
        self.events.append(
            {
                "event_type": "LOCKED",
                "fixture_id": decision.fixture_id,
                "phase": decision.phase,
                "decision_hash": digest,
                "event_time": lock.locked_at.isoformat().replace("+00:00", "Z"),
                "append_only": True,
            }
        )
        return lock

    @property
    def locks(self) -> list[StrategyLock]:
        return list(self._locks.values())


def adjusted_minimum_odds(
    distribution: SettlementDistribution,
    total_penalty: Decimal,
) -> Decimal:
    effective_win = (
        distribution.full_win_probability
        + Decimal("0.5") * distribution.half_win_probability
    )
    effective_loss = (
        distribution.full_loss_probability
        + Decimal("0.5") * distribution.half_loss_probability
    )
    if effective_win <= 0:
        raise ValueError("effective win probability is zero")
    return (Decimal("1") + ((effective_loss + total_penalty) / effective_win)).quantize(
        Decimal("0.0001"),
        rounding=ROUND_HALF_UP,
    )


def manifest_payload(root: Path) -> dict[str, Any]:
    policy_files = [
        root / "config/policies/strategy_hard_gate.v1.json",
        root / "config/policies/strategy_correlation.v1.json",
        root / "config/policies/shadow_strategy.v1.json",
    ]
    return {
        "strategy_version": SHADOW_STRATEGY_VERSION,
        "hard_gate_policy_sha256": file_sha256(policy_files[0]),
        "correlation_policy_sha256": file_sha256(policy_files[1]),
        "shadow_strategy_policy_sha256": file_sha256(policy_files[2]),
        "grade_policy": "GATE4_CAP_MAX_C",
        "model_version": "STAGE7B_FROZEN_CHALLENGER",
        "calibration_version": "STAGE7B_FROZEN_CALIBRATION",
        "formal_recommendation": False,
        "candidate": False,
    }


def validate_public_payload(payload: dict[str, Any]) -> None:
    text = json.dumps(payload, sort_keys=True)
    if payload.get("public_decision") not in PUBLIC_DECISIONS:
        raise ValueError("invalid public shadow decision")
    if payload.get("formal_recommendation") or payload.get("candidate"):
        raise ValueError("shadow strategy cannot publish formal recommendations")
    for forbidden in FORBIDDEN_PUBLIC_STATES:
        if f'"public_decision": "{forbidden}"' in text:
            raise ValueError(f"forbidden public state: {forbidden}")


def stable_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
