from __future__ import annotations

import pytest

from w2.domain.admission_contract import economic_admission_pass


@pytest.mark.parametrize(
    ("ev", "ev_minus_se", "cashflow_edge", "expected"),
    [
        (0.01, 0.01, 0.05, True),
        (0.0, 0.01, 0.05, False),
        (0.01, 0.0, 0.05, False),
        (0.01, 0.01, 0.049999, False),
        (None, 0.01, 0.05, False),
        (0.01, None, 0.05, False),
        (0.01, 0.01, None, False),
    ],
)
def test_economic_admission_contract(
    ev: float | None,
    ev_minus_se: float | None,
    cashflow_edge: float | None,
    expected: bool,
) -> None:
    assert (
        economic_admission_pass(
            expected_value=ev,
            ev_minus_se=ev_minus_se,
            cashflow_price_edge=cashflow_edge,
        )
        is expected
    )
