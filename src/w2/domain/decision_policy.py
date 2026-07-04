from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from w2.domain.enums import DataStatus, DecisionTier


@dataclass(frozen=True, kw_only=True)
class DecisionPolicyConfig:
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
    now_utc = policy_config.now_utc or datetime.now(UTC)
    if now_utc.tzinfo is None or now_utc.utcoffset() is None:
        raise ValueError("policy_config.now_utc must be timezone-aware")
    now_utc = now_utc.astimezone(UTC)

    future_kickoff = _kickoff_utc(card_core) > now_utc
    market_complete = policy_config.market_complete
    recommendation_id = _optional_text(_get(card_core, "recommendation_id"))

    if env == "staging":
        return (
            policy_config.data_integrity_passed
            and future_kickoff
            and market_complete
            and (
                recommendation_id is not None
                or policy_config.allow_staging_recommendation_id_generation
            )
        )

    if env == "production":
        return (
            _decision_tier(_get(card_core, "decision_tier")) is DecisionTier.RECOMMEND
            and policy_config.forward_ev_evidence_satisfied
            and _data_status(_get(card_core, "data_status")) is DataStatus.READY
            and future_kickoff
            and market_complete
        )

    raise ValueError("environment must be staging or production")


def _get(card_core: object, key: str) -> Any:
    if isinstance(card_core, Mapping):
        return card_core.get(key)
    return getattr(card_core, key)


def _decision_tier(value: Any) -> DecisionTier:
    if isinstance(value, DecisionTier):
        return value
    return DecisionTier(str(value))


def _data_status(value: Any) -> DataStatus:
    if isinstance(value, DataStatus):
        return value
    return DataStatus(str(value))


def _kickoff_utc(card_core: object) -> datetime:
    value = _get(card_core, "kickoff_utc")
    if not isinstance(value, datetime):
        raise TypeError("card_core.kickoff_utc must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("card_core.kickoff_utc must be timezone-aware")
    return value.astimezone(UTC)


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
