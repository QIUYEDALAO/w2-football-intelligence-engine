from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from w2.domain.enums import DataStatus, DecisionTier, LifecycleStatus

REQUIRED_DECISION_CONTRACT_FIELDS = (
    "decision_tier",
    "data_status",
    "lifecycle_status",
    "outcome_tracked",
    "lock_eligible",
    "recommendation_id",
    "pick",
    "non_pick",
)

CONTRACT_OWNED_FIELDS = frozenset(
    {
        *REQUIRED_DECISION_CONTRACT_FIELDS,
        "reason_code",
        "action",
        "next_eval_at",
        "provider_budget_status",
        "probability_source",
        "model_market_divergence",
        "missing_fields",
        "stale_fields",
        "data_readiness",
        "one_liner",
        "card_hash",
    }
)

_PICK_TIERS = frozenset({DecisionTier.ANALYSIS_PICK, DecisionTier.RECOMMEND})
_NON_PICK_TIERS = frozenset(
    {DecisionTier.NOT_READY, DecisionTier.SKIP, DecisionTier.WATCH}
)


class DecisionContractViolation(ValueError):
    """A persisted decision contract is incomplete or contradictory."""

    code = "SYSTEM_DEGRADED"


def validate_decision_contract(
    raw: object,
    *,
    fixture_id: object = None,
    card: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate one persisted decision contract without rebuilding any field."""
    identity = str(fixture_id or "UNKNOWN")
    if not isinstance(raw, Mapping):
        raise DecisionContractViolation(f"DECISION_CONTRACT_MISSING:{identity}")

    missing = [
        field for field in REQUIRED_DECISION_CONTRACT_FIELDS if field not in raw
    ]
    if missing:
        raise DecisionContractViolation(
            f"DECISION_CONTRACT_INCOMPLETE:{identity}:{','.join(missing)}"
        )

    tier = _enum_value(raw["decision_tier"], DecisionTier, identity, "decision_tier")
    _enum_value(raw["data_status"], DataStatus, identity, "data_status")
    _enum_value(raw["lifecycle_status"], LifecycleStatus, identity, "lifecycle_status")

    outcome_tracked = _required_bool(raw, "outcome_tracked", identity)
    lock_eligible = _required_bool(raw, "lock_eligible", identity)
    _validate_recommendation_id(raw["recommendation_id"], identity)

    pick = raw["pick"]
    non_pick = raw["non_pick"]
    if tier in _PICK_TIERS:
        if not isinstance(pick, Mapping) or not pick:
            raise DecisionContractViolation(
                f"DECISION_CONTRACT_INVALID:{identity}:pick"
            )
        if non_pick is not None:
            raise DecisionContractViolation(
                f"DECISION_CONTRACT_INVALID:{identity}:non_pick"
            )
        if outcome_tracked is not True:
            raise DecisionContractViolation(
                f"DECISION_CONTRACT_INVALID:{identity}:outcome_tracked"
            )
    elif tier in _NON_PICK_TIERS:
        if pick is not None:
            raise DecisionContractViolation(
                f"DECISION_CONTRACT_INVALID:{identity}:pick"
            )
        if not isinstance(non_pick, Mapping) or not non_pick:
            raise DecisionContractViolation(
                f"DECISION_CONTRACT_INVALID:{identity}:non_pick"
            )
        if outcome_tracked is not False:
            raise DecisionContractViolation(
                f"DECISION_CONTRACT_INVALID:{identity}:outcome_tracked"
            )
        if lock_eligible is not False:
            raise DecisionContractViolation(
                f"DECISION_CONTRACT_INVALID:{identity}:lock_eligible"
            )

    if tier is not DecisionTier.RECOMMEND and lock_eligible:
        raise DecisionContractViolation(
            f"DECISION_CONTRACT_INVALID:{identity}:lock_eligible"
        )

    contract = dict(raw)
    if card is not None:
        for field in sorted(CONTRACT_OWNED_FIELDS):
            if field in card and card[field] != contract.get(field):
                raise DecisionContractViolation(
                    f"DECISION_CONTRACT_CONFLICT:{identity}:{field}"
                )
    return contract


def _enum_value(
    value: object,
    enum_type: type[DecisionTier] | type[DataStatus] | type[LifecycleStatus],
    fixture_id: str,
    field: str,
) -> DecisionTier | DataStatus | LifecycleStatus:
    if not isinstance(value, str):
        raise DecisionContractViolation(
            f"DECISION_CONTRACT_INVALID:{fixture_id}:{field}"
        )
    try:
        return enum_type(value)
    except ValueError as exc:
        raise DecisionContractViolation(
            f"DECISION_CONTRACT_INVALID:{fixture_id}:{field}"
        ) from exc


def _required_bool(
    contract: Mapping[str, Any],
    field: str,
    fixture_id: str,
) -> bool:
    value = contract[field]
    if type(value) is not bool:
        raise DecisionContractViolation(
            f"DECISION_CONTRACT_INVALID:{fixture_id}:{field}"
        )
    return value


def _validate_recommendation_id(value: object, fixture_id: str) -> None:
    if value is None:
        return
    if not isinstance(value, str) or not value.strip():
        raise DecisionContractViolation(
            f"DECISION_CONTRACT_INVALID:{fixture_id}:recommendation_id"
        )
