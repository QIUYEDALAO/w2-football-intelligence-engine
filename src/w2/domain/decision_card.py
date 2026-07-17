from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, cast

from w2.domain.enums import (
    DataStatus,
    DecisionReasonCode,
    DecisionTier,
    LifecycleStatus,
    ProbabilitySource,
)
from w2.domain.time import require_utc

PICK_TIERS = {DecisionTier.ANALYSIS_PICK, DecisionTier.RECOMMEND}
NON_PICK_TIERS = {DecisionTier.NOT_READY, DecisionTier.SKIP, DecisionTier.WATCH}
ANALYSIS_PICK_DISCLAIMER_REQUIRED = ("分析参考", "非稳赢")
DETERMINISTIC_CLAIM_TERMS = ("必中", "保证", "包赢")


@dataclass(frozen=True, kw_only=True)
class DecisionPick:
    market: str
    selection: str
    line: str | None
    odds: str | None
    fair_line: str | None
    market_line: str | None
    value_edge: float | None
    key_factors: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    invalidation: str | None = None
    disclaimer: str = "分析参考·非稳赢；production 动作需 RECOMMEND"


@dataclass(frozen=True, kw_only=True)
class DecisionNonPick:
    reason_code: DecisionReasonCode
    reason_human: str
    action: str
    next_eval_at: datetime | None

    def __post_init__(self) -> None:
        if self.next_eval_at is not None:
            object.__setattr__(
                self,
                "next_eval_at",
                require_utc(self.next_eval_at, "next_eval_at"),
            )


@dataclass(frozen=True, kw_only=True)
class DecisionCard:
    fixture_id: str
    competition_id: str
    kickoff_utc: datetime
    kickoff_beijing: datetime
    decision_tier: DecisionTier
    data_status: DataStatus
    lifecycle_status: LifecycleStatus
    outcome_tracked: bool
    lock_eligible: bool
    recommendation_id: str | None
    model_version: str
    provenance: Mapping[str, Any]
    environment: str
    probability_source: ProbabilitySource = ProbabilitySource.UNKNOWN
    model_market_divergence: Mapping[str, Any] = field(default_factory=dict)
    pick: DecisionPick | None = None
    non_pick: DecisionNonPick | None = None
    one_liner: str = ""
    card_hash: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "kickoff_utc", require_utc(self.kickoff_utc, "kickoff_utc"))
        if self.kickoff_beijing.tzinfo is None or self.kickoff_beijing.utcoffset() is None:
            raise ValueError("kickoff_beijing must be timezone-aware")
        _validate_tier_payload(self.decision_tier, self.pick, self.non_pick)
        object.__setattr__(self, "card_hash", compute_card_hash(self))

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["decision_tier"] = self.decision_tier.value
        payload["data_status"] = self.data_status.value
        payload["lifecycle_status"] = self.lifecycle_status.value
        payload["probability_source"] = self.probability_source.value
        if self.non_pick is not None:
            payload["non_pick"]["reason_code"] = self.non_pick.reason_code.value
        return payload


def compute_card_hash(card: DecisionCard | Mapping[str, Any]) -> str:
    payload = _hash_payload(card)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=_json_default)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _hash_payload(card: DecisionCard | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(card, DecisionCard):
        payload: dict[str, Any] = {
            "fixture_id": card.fixture_id,
            "competition_id": card.competition_id,
            "kickoff_utc": card.kickoff_utc,
            "kickoff_beijing": card.kickoff_beijing,
            "decision_tier": card.decision_tier,
            "data_status": card.data_status,
            "lifecycle_status": card.lifecycle_status,
            "outcome_tracked": card.outcome_tracked,
            "recommendation_id": card.recommendation_id,
            "model_version": card.model_version,
            "probability_source": card.probability_source,
            "model_market_divergence": card.model_market_divergence,
            "provenance": card.provenance,
            "pick": card.pick,
            "non_pick": card.non_pick,
            "one_liner": card.one_liner,
        }
    else:
        payload = {
            key: value
            for key, value in card.items()
            if key not in {"card_hash", "environment", "lock_eligible"}
        }
    return cast(dict[str, Any], _normalize(payload))


def _validate_tier_payload(
    decision_tier: DecisionTier,
    pick: DecisionPick | None,
    non_pick: DecisionNonPick | None,
) -> None:
    if decision_tier in PICK_TIERS:
        if pick is None or non_pick is not None:
            raise ValueError("ANALYSIS_PICK and RECOMMEND DecisionCard values require pick only")
        _validate_disclaimer(decision_tier, pick.disclaimer)
        return

    if decision_tier in NON_PICK_TIERS:
        if non_pick is None or pick is not None:
            raise ValueError("NOT_READY, SKIP, and WATCH DecisionCard values require non_pick only")
        return

    raise ValueError(f"unsupported decision_tier: {decision_tier}")


def _validate_disclaimer(decision_tier: DecisionTier, disclaimer: str) -> None:
    if decision_tier is DecisionTier.ANALYSIS_PICK and any(
        required not in disclaimer for required in ANALYSIS_PICK_DISCLAIMER_REQUIRED
    ):
        raise ValueError("ANALYSIS_PICK disclaimer must include 分析参考 and 非稳赢")

    if "稳赢" in disclaimer and "非稳赢" not in disclaimer:
        raise ValueError("disclaimer cannot contain deterministic win claims")
    if any(term in disclaimer for term in DETERMINISTIC_CLAIM_TERMS):
        raise ValueError("disclaimer cannot contain deterministic win claims")


def _normalize(value: Any) -> Any:
    if isinstance(value, DecisionPick | DecisionNonPick):
        return _normalize(asdict(value))
    if isinstance(
        value,
        DecisionTier | DataStatus | LifecycleStatus | DecisionReasonCode | ProbabilitySource,
    ):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_normalize(item) for item in value]
    return value


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)
