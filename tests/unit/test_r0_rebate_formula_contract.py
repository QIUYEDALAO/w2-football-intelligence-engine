"""Independent arithmetic examples for the offline ABS_PROFIT_V2 proposal."""
from __future__ import annotations

from decimal import Decimal

import pytest

from w2.domain.profit import (
    REBATE_FORMULA_VERSION,
    profit_units_with_rebate,
    rebate_units,
)
from w2.quant_research import track_b_lambda_level_fusion as track_b
from w2.quant_research import track_cd_offline_presentation as track_cd


def test_settled_cashflows_and_offline_expectation_match_independent_oracle() -> None:
    # Odds 1.90.  This table is written directly from the Boss's per-state rule,
    # independently of the code's probability formula.
    state_profit = {
        "WIN": Decimal("0.9"),
        "HALF_WIN": Decimal("0.45"),
        "PUSH": Decimal("0"),
        "HALF_LOSS": Decimal("-0.5"),
        "LOSS": Decimal("-1"),
    }
    state_rebate = {
        "WIN": Decimal("0.0225"),
        "HALF_WIN": Decimal("0.01125"),
        "PUSH": Decimal("0"),
        "HALF_LOSS": Decimal("0.0125"),
        "LOSS": Decimal("0.025"),
    }
    probabilities = {
        "WIN": Decimal("0.2"),
        "HALF_WIN": Decimal("0.15"),
        "PUSH": Decimal("0.1"),
        "HALF_LOSS": Decimal("0.25"),
        "LOSS": Decimal("0.3"),
    }
    for state, profit in state_profit.items():
        assert rebate_units([profit]) == state_rebate[state]
        assert profit_units_with_rebate([profit]) == profit + state_rebate[state]

    oracle_rebate = sum(
        (probabilities[state] * state_rebate[state] for state in state_profit),
        Decimal("0"),
    )
    oracle_ev = sum(
        (
            probabilities[state] * (state_profit[state] + state_rebate[state])
            for state in state_profit
        ),
        Decimal("0"),
    )
    # Keep the probability channel float-based; only amount arithmetic is Decimal.
    distribution = {state: float(probabilities[state]) for state in state_profit}
    assert oracle_rebate == Decimal("0.0168125")
    assert oracle_ev == Decimal("-0.1606875")
    assert track_b.expected_rebate_units(distribution, Decimal("1.9")) == oracle_rebate
    assert track_b.five_state_cashflow(distribution, Decimal("1.9")) == oracle_ev


def test_version_is_shared_and_binary_track_d_is_not_five_state_equivalent() -> None:
    assert REBATE_FORMULA_VERSION == "ABS_PROFIT_V2"
    assert track_b.REBATE_FORMULA_VERSION == REBATE_FORMULA_VERSION
    assert track_cd.REBATE_FORMULA_VERSION == REBATE_FORMULA_VERSION
    assert track_cd.TRACK_D_APPROX_FORMULA_VERSION == "w2.track_d.binary_abs_profit_v2.v1"

    distribution = {
        "WIN": 0.2,
        "HALF_WIN": 0.15,
        "PUSH": 0.1,
        "HALF_LOSS": 0.25,
        "LOSS": 0.3,
    }
    binary_p = distribution["WIN"] + 0.5 * distribution["HALF_WIN"]
    assert track_cd.single_probability_cashflow(binary_p, 1.9) != pytest.approx(
        float(track_b.five_state_cashflow(distribution, 1.9))
    )


def test_r0_five_state_examples_are_digit_exact_across_all_three_paths() -> None:
    cases = {
        "WIN": (Decimal("0.9"), Decimal("0.0225"), Decimal("0.9225")),
        "HALF_WIN": (Decimal("0.45"), Decimal("0.01125"), Decimal("0.46125")),
        "PUSH": (Decimal("0"), Decimal("0"), Decimal("0")),
        "HALF_LOSS": (Decimal("-0.5"), Decimal("0.0125"), Decimal("-0.4875")),
        "LOSS": (Decimal("-1"), Decimal("0.025"), Decimal("-0.975")),
    }
    for state, (profit, rebate, net) in cases.items():
        distribution = {key: 1.0 if key == state else 0.0 for key in cases}
        assert rebate_units([profit]) == rebate
        assert profit_units_with_rebate([profit]) == net
        assert track_b.expected_rebate_units(distribution, Decimal("1.90")) == rebate
        assert track_b.five_state_cashflow(distribution, Decimal("1.90")) == net
