"""Shared profit projection helpers.

Settlement remains the sole authority for ``profit_units``.  This module only
projects the optional rebate view and never changes settlement outcomes.
"""
from __future__ import annotations

from decimal import Decimal

REBATE_RATE = Decimal("0.025")


def profit_units_with_rebate(
    profit_units: Decimal | float | int | str, settled_count: int
) -> Decimal:
    """Return pure profit plus the fixed per-settled-recommendation rebate."""
    if settled_count < 0:
        raise ValueError("settled_count must be non-negative")
    return Decimal(str(profit_units)) + REBATE_RATE * settled_count
