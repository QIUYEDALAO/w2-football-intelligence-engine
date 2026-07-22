from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

AH_OUTCOMES = ("WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "LOSS")
EFFECTIVE_PROBABILITY_VERSION = "w2.effective_settlement_probability.v1"


def effective_settlement_probability(distribution: Mapping[str, Any]) -> float | None:
    """Return the frozen scalar AH comparison probability.

    This is not a five-state scoring replacement. It is only the legacy scalar
    comparison used by analysis evidence and formal edge checks:
    WIN + 0.5 * HALF_WIN + 0.5 * PUSH.
    """
    values = _distribution_values(distribution)
    if values is None:
        return None
    value = round(
        values["WIN"] + Decimal("0.5") * values["HALF_WIN"] + Decimal("0.5") * values["PUSH"],
        6,
    )
    return float(value)


def complete_five_state_distribution(distribution: Mapping[str, Any]) -> bool:
    return _distribution_values(distribution) is not None


def _distribution_values(distribution: Mapping[str, Any]) -> dict[str, Decimal] | None:
    if set(distribution) != set(AH_OUTCOMES):
        return None
    values: dict[str, Decimal] = {}
    try:
        for outcome in AH_OUTCOMES:
            value = Decimal(str(distribution[outcome]))
            if value < 0:
                return None
            values[outcome] = value
    except (InvalidOperation, TypeError, ValueError):
        return None
    total = sum(values.values(), Decimal("0"))
    if abs(total - Decimal("1")) > Decimal("0.000001"):
        return None
    return values
