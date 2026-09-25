from __future__ import annotations

import inspect
from math import isclose

import pytest

from w2.quant_research.track_b_lambda_level_fusion import (
    FROZEN_W_AH,
    FROZEN_W_TOTALS,
    _distribution,
    expected_rebate_units,
    five_state_cashflow,
    fuse_lambda_level,
)
from w2.quant_research.track_cd_offline_presentation import single_probability_cashflow


def _ah_pair(home_line: float = 0.25) -> dict[str, dict[str, object]]:
    return {
        side: {
            "line": side_line,
            "price": 1.9,
            "quote_identity": {
                "provider_fixture_id": "123", "bookmaker_id": "4",
                "capture_id": "capture-1", "market": "ASIAN_HANDICAP",
                "selection": side, "line": side_line, "price": 1.9,
                "observation_id": f"observation-{side.lower()}",
            },
        }
        for side, side_line in (("HOME", home_line), ("AWAY", -home_line))
    }


def test_five_state_distribution_sums_to_one_for_ah_and_totals() -> None:
    ah = fuse_lambda_level(
        market="ASIAN_HANDICAP",
        selection="HOME",
        line=0.25,
        model_lambda_home=1.55,
        model_lambda_away=1.05,
        market_odds=_ah_pair(),
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
    # Pure cashflow is 0.075; ABS_PROFIT_V2 expected rebate is 0.018125.
    assert isclose(expected_rebate_units(distribution, 2.0), 0.018125, abs_tol=1e-12)
    assert isclose(five_state_cashflow(distribution, 2.0), 0.093125, abs_tol=1e-12)


def test_abs_profit_v2_rebate_covers_each_five_state() -> None:
    odds = 2.0
    cases = {
        "WIN": 0.025,
        "HALF_WIN": 0.0125,
        "PUSH": 0.0,
        "HALF_LOSS": 0.0125,
        "LOSS": 0.025,
    }
    for state, expected in cases.items():
        distribution = {key: float(key == state) for key in (
            "WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "LOSS"
        )}
        assert isclose(expected_rebate_units(distribution, odds), expected, abs_tol=1e-12)


def test_single_probability_track_d_is_explicit_binary_approximation() -> None:
    # p=0.4, odds=2.5: pure=-0.0, rebate=.025*(.6+.6)=.03.
    assert isclose(single_probability_cashflow(0.4, 2.5), 0.03, abs_tol=1e-12)


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
    assert isclose(result.effective_probability, market_under, abs_tol=1e-6)
    assert not isclose(result.lambda_total_market, result.lambda_total_model, abs_tol=1e-9)


def test_weights_are_frozen_constants() -> None:
    assert FROZEN_W_AH == 0.9
    assert FROZEN_W_TOTALS == 0.0
    assert "weight" not in inspect.signature(fuse_lambda_level).parameters


@pytest.mark.parametrize(
    "mutate",
    [
        lambda q: q["AWAY"].update(line=0.25),
        lambda q: q["AWAY"]["quote_identity"].update(bookmaker_id="9"),
        lambda q: q["AWAY"]["quote_identity"].update(capture_id="other"),
        lambda q: q["AWAY"]["quote_identity"].update(line=0.25),
        lambda q: q["AWAY"]["quote_identity"].update(selection="HOME"),
        lambda q: q["HOME"].update(price=2.1),
    ],
)
def test_ah_quote_pair_mismatch_rejected(mutate: object) -> None:
    pair = _ah_pair()
    mutate(pair)
    with pytest.raises(ValueError, match="QUOTE_PAIR_MISMATCH"):
        fuse_lambda_level(
            market="ASIAN_HANDICAP", selection="HOME", line=0.25,
            model_lambda_home=1.55, model_lambda_away=1.05,
            market_odds=pair,
        )
