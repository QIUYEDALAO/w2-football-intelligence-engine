from __future__ import annotations

from fractions import Fraction

from w2.markets.devig import devig_balance_distance


def test_balance_distance_uses_six_decimal_places() -> None:
    first = Fraction(19, 10)
    second = Fraction(9501, 5000)
    exact = abs(second / (first + second) - Fraction(1, 2))

    assert devig_balance_distance([float(first), float(second)]) == round(float(exact), 6)
    assert devig_balance_distance([float(first), float(second)]) == 0.000026


def test_balance_distance_rejects_incomplete_or_nonpositive_pairs() -> None:
    assert devig_balance_distance([1.9]) == 999.0
    assert devig_balance_distance([1.9, 0.0]) == 999.0
