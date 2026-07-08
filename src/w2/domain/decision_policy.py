from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from w2.domain.enums import DecisionTier


@dataclass(frozen=True, kw_only=True)
class DecisionPolicyConfig:
    """Upstream RECOMMEND admission context, not lock eligibility inputs.

    Since #207, lock eligibility depends only on ``decision_tier == RECOMMEND``.
    The fields below are retained for adapter/API compatibility and document the
    prerequisites used before a card may be upgraded to RECOMMEND.
    """

    now_utc: datetime | None = None
    data_integrity_passed: bool = False
    market_complete: bool = False
    forward_ev_evidence_satisfied: bool = False
    allow_staging_recommendation_id_generation: bool = True


def compute_outcome_tracked(decision_tier: DecisionTier | str) -> bool:
    tier = _decision_tier(decision_tier)
    return tier in {DecisionTier.ANALYSIS_PICK, DecisionTier.RECOMMEND}


def compute_lock_eligible(
    card_core: object,
    environment: str,
    policy_config: DecisionPolicyConfig,
) -> bool:
    env = environment.strip().lower()
    if env not in {"staging", "production"}:
        raise ValueError("environment must be staging or production")
    return _decision_tier(_get(card_core, "decision_tier")) is DecisionTier.RECOMMEND


def _get(card_core: object, key: str) -> Any:
    if isinstance(card_core, Mapping):
        return card_core.get(key)
    return getattr(card_core, key)


def _decision_tier(value: Any) -> DecisionTier:
    if isinstance(value, DecisionTier):
        return value
    return DecisionTier(str(value))
