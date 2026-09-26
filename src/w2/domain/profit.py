"""Shared profit projection helpers.

Settlement remains the sole authority for ``profit_units``.  This module only
projects the optional rebate view and never changes settlement outcomes.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from decimal import Decimal
from math import isfinite

REBATE_RATE = Decimal("0.025")
REBATE_FORMULA_VERSION = "ABS_PROFIT_V2"
FROZEN_FADE_DELTA = 0.05


def _track_d_price(value: float) -> float:
    try:
        price = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("odds must be numeric") from exc
    if not isfinite(price) or price <= 1.0:
        raise ValueError("odds must be finite and greater than 1")
    return price


def track_d_fair_probability(odds: Mapping[str, float], selection: str) -> float:
    """Remove two-way market vig for the registered Track D approximation."""
    sides = ("OVER", "UNDER") if selection in {"OVER", "UNDER"} else ("HOME", "AWAY")
    implied: dict[str, float] = {}
    for side in sides:
        price = _track_d_price(odds[side])
        implied[side] = 1.0 / price
    return implied[selection] / sum(implied.values())


def track_d_binary_cashflow(probability: float, decimal_odds: float) -> float:
    """Registered binary approximation; realized settlement remains five-state."""
    if not isfinite(probability) or not 0.0 <= probability <= 1.0:
        raise ValueError("probability must be between 0 and 1")
    price = _track_d_price(decimal_odds)
    if REBATE_FORMULA_VERSION != "ABS_PROFIT_V2":
        raise RuntimeError("unsupported rebate formula version")
    rebate = float(REBATE_RATE) * ((price - 1.0) * probability + (1.0 - probability))
    return probability * price - 1.0 + rebate


def profit_units_with_rebate(
    profit_units: Iterable[Decimal | float | int | str],
) -> Decimal:
    """Sum each settled bet's profit and rebate on its absolute profit."""
    values = [Decimal(str(value)) for value in profit_units]
    return sum(values, Decimal("0")) + rebate_units(values)


def rebate_units(profit_units: Iterable[Decimal | float | int | str]) -> Decimal:
    """Return the rebate earned from each bet's absolute realized profit."""
    absolute_total = sum(
        (abs(Decimal(str(value))) for value in profit_units), Decimal("0")
    )
    return REBATE_RATE * absolute_total


def profit_units_with_rebate_from_sums(
    pure_profit_units: Decimal | float | int | str,
    absolute_profit_units: Decimal | float | int | str,
) -> Decimal:
    """Use SQL-computed sum and absolute sum without loading every historical bet."""
    return Decimal(str(pure_profit_units)) + rebate_units([absolute_profit_units])
