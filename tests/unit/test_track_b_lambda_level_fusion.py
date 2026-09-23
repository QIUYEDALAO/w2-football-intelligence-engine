from __future__ import annotations

import inspect
from math import isclose

from w2.quant_research.track_b_lambda_level_fusion import (
    FROZEN_W_AH,
    FROZEN_W_TOTALS,
    _distribution,
    five_state_cashflow,
    fuse_lambda_level,
)


def test_five_state_distribution_sums_to_one_for_ah_and_totals() -> None:
    ah = fuse_lambda_level(
        market="ASIAN_HANDICAP",
        selection="HOME",
        line=0.25,
        model_lambda_home=1.55,
        model_lambda_away=1.05,
        market_odds={"HOME": 1.90, "AWAY": 1.90},
    )
    totals = fuse_lambda_level(
        market="TOTALS",
        selection="UNDER",
        line=2.25,
        model_lambda_home=1.55,
        model_lambda_away=1.05,
        market_odds={"OVER": 1.90, "UNDER": 1.90},
    )
    assert isclose(ah.probability_sum, 1.0, abs_tol=1e-9)
    assert isclose(totals.probability_sum, 1.0, abs_tol=1e-9)
    assert set(ah.distribution) == {"WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "LOSS"}


def test_quarter_line_cashflow_maps_half_states_exactly() -> None:
    # A total of 1 on 2.25 is WIN for UNDER, 2 is HALF_WIN, and 3 is LOSS.
    under = _distribution({(1, 1): 0.4, (1, 2): 0.6}, "TOTALS", "UNDER", 2.25)
    over = _distribution({(1, 1): 0.4, (1, 2): 0.6}, "TOTALS", "OVER", 2.25)
    assert under == {"WIN": 0.0, "HALF_WIN": 0.4, "PUSH": 0.0, "HALF_LOSS": 0.0, "LOSS": 0.6}
    assert over == {"WIN": 0.6, "HALF_WIN": 0.0, "PUSH": 0.0, "HALF_LOSS": 0.4, "LOSS": 0.0}

    assert _distribution({(0, 1): 1.0}, "TOTALS", "UNDER", 2.25)["WIN"] == 1.0
    assert _distribution({(1, 1): 1.0}, "TOTALS", "UNDER", 2.0)["PUSH"] == 1.0
    assert _distribution({(1, 2): 1.0}, "TOTALS", "UNDER", 2.75)["HALF_LOSS"] == 1.0


def test_five_state_cashflow_applies_half_win_push_half_loss_and_loss() -> None:
    distribution = {
        "WIN": 0.30,
        "HALF_WIN": 0.20,
        "PUSH": 0.10,
        "HALF_LOSS": 0.15,
        "LOSS": 0.25,
    }
    assert isclose(five_state_cashflow(distribution, 2.0), 0.075, abs_tol=1e-12)


def test_no_push_lambda_probability_matches_scalar_success_probability() -> None:
    result = fuse_lambda_level(
        market="TOTALS",
        selection="OVER",
        line=2.5,
        model_lambda_home=1.35,
        model_lambda_away=1.10,
        market_odds={"OVER": 2.0, "UNDER": 2.0},
    )
    assert result.distribution["PUSH"] == 0.0
    assert result.distribution["HALF_WIN"] == 0.0
    assert isclose(result.effective_probability, result.distribution["WIN"], abs_tol=1e-12)


def test_totals_zero_weight_uses_market_total_probability_only() -> None:
    result = fuse_lambda_level(
        market="TOTALS",
        selection="UNDER",
        line=2.5,
        model_lambda_home=0.60,
        model_lambda_away=2.40,
        market_odds={"OVER": 1.80, "UNDER": 2.20},
    )
    market_under = (1 / 2.20) / ((1 / 1.80) + (1 / 2.20))
    assert FROZEN_W_TOTALS == 0.0
    assert isclose(result.effective_probability, market_under, abs_tol=1e-9)
    assert not isclose(result.lambda_total_market, result.lambda_total_model, abs_tol=1e-9)


def test_weights_are_frozen_constants() -> None:
    assert FROZEN_W_AH == 0.9
    assert FROZEN_W_TOTALS == 0.0
    assert "weight" not in inspect.signature(fuse_lambda_level).parameters
