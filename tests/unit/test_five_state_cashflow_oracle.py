from __future__ import annotations

from decimal import Decimal

import pytest

from w2.markets.value_engine import (
    SettlementDistribution,
    cashflow_price_edge,
    expected_value,
    fair_decimal_odds,
)


@pytest.mark.parametrize(
    ("line_kind", "probabilities"),
    (
        ("integer_push", ("0.42", "0", "0.18", "0", "0.40")),
        ("half_line", ("0.54", "0", "0", "0", "0.46")),
        ("quarter_half_win", ("0.39", "0.17", "0", "0", "0.44")),
        ("quarter_half_loss", ("0.45", "0", "0", "0.16", "0.39")),
        ("all_five_states", ("0.36", "0.12", "0.08", "0.14", "0.30")),
    ),
)
def test_five_state_fair_odds_and_cashflow_edge_match_independent_oracle(
    line_kind: str,
    probabilities: tuple[str, str, str, str, str],
) -> None:
    win, half_win, push, half_loss, loss = map(Decimal, probabilities)
    distribution = SettlementDistribution(
        full_win_probability=win,
        half_win_probability=half_win,
        push_probability=push,
        half_loss_probability=half_loss,
        full_loss_probability=loss,
    )
    oracle_fair = (
        Decimal("1")
        + (loss + Decimal("0.5") * half_loss)
        / (win + Decimal("0.5") * half_win)
    ).quantize(Decimal("0.0001"))
    executable_price = Decimal("1.95")
    oracle_ev = (
        win * (executable_price - 1)
        + half_win * Decimal("0.5") * (executable_price - 1)
        - half_loss * Decimal("0.5")
        - loss
    )
    oracle_edge = executable_price / oracle_fair - 1

    assert line_kind
    assert fair_decimal_odds(distribution) == oracle_fair
    assert expected_value(executable_price, distribution) == oracle_ev
    assert cashflow_price_edge(executable_price, oracle_fair) == oracle_edge


def test_cashflow_edge_rejects_invalid_price_contract() -> None:
    with pytest.raises(ValueError, match="decimal odds"):
        cashflow_price_edge(Decimal("1"), Decimal("2"))
    with pytest.raises(ValueError, match="fair decimal odds"):
        cashflow_price_edge(Decimal("2"), Decimal("0.99"))
