"""Shared profit projection helpers.

Settlement remains the sole authority for ``profit_units``.  This module only
projects the optional rebate view and never changes settlement outcomes.
"""
from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

REBATE_RATE = Decimal("0.025")
REBATE_FORMULA_VERSION = "ABS_PROFIT_V2"


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
