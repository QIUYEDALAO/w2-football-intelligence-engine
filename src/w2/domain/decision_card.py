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
from w2.models.fair_market_estimate import (
    verify_estimate_semantics,
    verify_estimate_snapshot,
)

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
    estimate_id: str | None = None
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
    analysis_gate: Mapping[str, Any] = field(default_factory=dict)
    analysis_gates: tuple[Mapping[str, Any], ...] = ()
    analysis_gate_v2_shadow: Mapping[str, Any] = field(default_factory=dict)
    analysis_gate_v2_shadows: tuple[Mapping[str, Any], ...] = ()
    fair_market_estimates: tuple[Mapping[str, Any], ...] = ()
    fair_market_estimate_ids: tuple[str, ...] = ()
    fair_market_estimate_snapshots: tuple[Mapping[str, Any], ...] = ()
    optional_enrichment: Mapping[str, Any] = field(default_factory=dict)
    player_impact_estimate: Mapping[str, Any] = field(default_factory=dict)
    pick: DecisionPick | None = None
    non_pick: DecisionNonPick | None = None
    one_liner: str = ""
    card_hash: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "kickoff_utc", require_utc(self.kickoff_utc, "kickoff_utc"))
        if self.kickoff_beijing.tzinfo is None or self.kickoff_beijing.utcoffset() is None:
            raise ValueError("kickoff_beijing must be timezone-aware")
        _validate_tier_payload(self.decision_tier, self.pick, self.non_pick)
        _validate_estimate_references(
            self.fair_market_estimate_ids,
            self.fair_market_estimate_snapshots,
            self.pick,
            self.analysis_gate,
        )
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
            "analysis_gate": card.analysis_gate,
            "analysis_gates": card.analysis_gates,
            "analysis_gate_v2_shadow": card.analysis_gate_v2_shadow,
            "analysis_gate_v2_shadows": card.analysis_gate_v2_shadows,
            "fair_market_estimates": card.fair_market_estimates,
            "fair_market_estimate_ids": card.fair_market_estimate_ids,
            "fair_market_estimate_snapshots": card.fair_market_estimate_snapshots,
            "optional_enrichment": card.optional_enrichment,
            "player_impact_estimate": card.player_impact_estimate,
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


def _validate_estimate_references(
    estimate_ids: Sequence[str],
    snapshots: Sequence[Mapping[str, Any]],
    pick: DecisionPick | None,
    analysis_gate: Mapping[str, Any],
) -> None:
    if pick is None:
        return
    if not snapshots:
        raise ValueError("DecisionCard pick requires immutable v2 estimate snapshots")
    declared = {str(item) for item in estimate_ids if item}
    captured = {str(item.get("estimate_id") or "") for item in snapshots}
    if not declared or "" in captured or declared != captured:
        raise ValueError("DecisionCard estimate IDs must match immutable snapshots")
    if any(
        item.get("schema_version") != "w2.fme_snapshot.v2"
        or not item.get("model_basis_id")
        or not verify_estimate_snapshot(item)
        or not verify_estimate_semantics(item)
        for item in snapshots
    ):
        raise ValueError("DecisionCard snapshots must pass v2 integrity and semantics")
    if pick is not None and (not pick.estimate_id or pick.estimate_id not in declared):
        raise ValueError("DecisionCard pick must reference an immutable estimate snapshot")
    snapshot = next(item for item in snapshots if item.get("estimate_id") == pick.estimate_id)
    if snapshot.get("market") != pick.market:
        raise ValueError("DecisionCard pick market must match estimate snapshot market")
    if analysis_gate.get("estimate_id") != pick.estimate_id:
        raise ValueError("DecisionCard pick estimate must match analysis gate estimate")
    if analysis_gate.get("market") != pick.market:
        raise ValueError("DecisionCard pick market must match analysis gate market")
    if not _quote_matches_pick(snapshot, pick, analysis_gate):
        raise ValueError("DecisionCard pick quote must match estimate evaluation quote")


def _quote_matches_pick(
    snapshot: Mapping[str, Any],
    pick: DecisionPick,
    analysis_gate: Mapping[str, Any],
) -> bool:
    odds = _mapping(_mapping(snapshot.get("input_context")).get("odds_snapshot"))
    if pick.market == "ASIAN_HANDICAP":
        quote = _mapping(odds.get("ah"))
        gate_line = quote.get("home_line")
        if pick.selection == "HOME_AH":
            line, price = quote.get("home_line"), quote.get("home_price")
        elif pick.selection == "AWAY_AH":
            line, price = quote.get("away_line"), quote.get("away_price")
        else:
            return False
    elif pick.market == "TOTALS":
        quote = _mapping(odds.get("ou"))
        gate_line = quote.get("line")
        line = quote.get("line")
        price = quote.get("over_price" if pick.selection == "OVER" else "under_price")
        if pick.selection not in {"OVER", "UNDER"}:
            return False
    else:
        return False
    if any(
        value is None
        for value in (
            analysis_gate.get("market_line"),
            gate_line,
            pick.line,
            line,
            pick.odds,
            price,
        )
    ):
        return False
    return (
        _same_number(analysis_gate.get("market_line"), gate_line)
        and _same_number(pick.line, line)
        and _same_number(pick.odds, price)
    )


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _same_number(left: Any, right: Any) -> bool:
    try:
        return abs(float(left) - float(right)) <= 1e-9
    except (TypeError, ValueError):
        return False


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
