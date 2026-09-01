from __future__ import annotations

import pytest
from scripts.score_v1_historical_closing_blindtest import _bootstrap, _probability, _scores


def test_five_state_probability_uses_cashflow_equivalent_weights() -> None:
    distribution = {
        "WIN": "0.1",
        "HALF_WIN": "0.2",
        "PUSH": "0.3",
        "HALF_LOSS": "0.1",
        "LOSS": "0.3",
    }

    assert _probability(distribution) == pytest.approx(0.425)
    assert _scores(0.425, 0.75)[0] == pytest.approx((0.425 - 0.75) ** 2)


def test_paired_bootstrap_is_deterministic() -> None:
    values = [-0.1, 0.0, 0.1, 0.2]

    assert _bootstrap(values, 3) == _bootstrap(values, 3)
    assert _bootstrap(values, 3)["seed"] == 20261004
