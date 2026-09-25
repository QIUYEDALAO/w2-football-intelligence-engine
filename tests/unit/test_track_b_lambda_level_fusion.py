from __future__ import annotations

import csv
import hashlib
import inspect
from math import exp, factorial, isclose
from pathlib import Path

import pytest

from w2.quant_research.track_b_lambda_level_fusion import (
    AH_QUOTE_CAPTURE_MAX_SKEW_SECONDS,
    FROZEN_W_AH,
    FROZEN_W_TOTALS,
    AhQuoteSideMissing,
    _distribution,
    _market_under_probability,
    _poisson_total_five_state,
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
                "captured_at": "2026-09-25T09:00:00Z",
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


@pytest.mark.parametrize(
    ("line", "total_goals", "under_state", "over_state"),
    [
        (2.0, 1, "WIN", "LOSS"), (2.0, 2, "PUSH", "PUSH"),
        (2.0, 3, "LOSS", "WIN"),
        (2.25, 1, "WIN", "LOSS"), (2.25, 2, "HALF_WIN", "HALF_LOSS"),
        (2.25, 3, "LOSS", "WIN"),
        (2.5, 2, "WIN", "LOSS"), (2.5, 3, "LOSS", "WIN"),
        (2.75, 2, "WIN", "LOSS"), (2.75, 3, "HALF_LOSS", "HALF_WIN"),
        (2.75, 4, "LOSS", "WIN"),
    ],
)
def test_total_infer_v2_draft_all_line_settlement_boundaries(
    line: float, total_goals: int, under_state: str, over_state: str
) -> None:
    # The expected states are the V2 draft's eight-row table, independent of
    # the production settlement helper used inside _distribution.
    matrix = {(total_goals, 0): 1.0}
    assert _distribution(matrix, "TOTALS", "UNDER", line)[under_state] == 1.0
    assert _distribution(matrix, "TOTALS", "OVER", line)[over_state] == 1.0


@pytest.mark.parametrize("line", [2.0, 2.25, 2.5, 2.75])
@pytest.mark.parametrize("selection", ["UNDER", "OVER"])
def test_total_infer_v2_draft_analytic_five_states_match_independent_enumeration(
    line: float, selection: str
) -> None:
    # Independent Poisson enumeration uses the table's result for each integer
    # total, with the omitted tail bounded below 1e-12 at lambda=2.6.
    total = 2.6
    expected = {state: 0.0 for state in ("WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "LOSS")}
    for goals in range(25):
        if line == 2.0:
            under = "WIN" if goals < 2 else "PUSH" if goals == 2 else "LOSS"
        elif line == 2.25:
            under = "WIN" if goals < 2 else "HALF_WIN" if goals == 2 else "LOSS"
        elif line == 2.5:
            under = "WIN" if goals <= 2 else "LOSS"
        else:
            under = "WIN" if goals <= 2 else "HALF_LOSS" if goals == 3 else "LOSS"
        over = {"WIN": "LOSS", "HALF_WIN": "HALF_LOSS", "PUSH": "PUSH",
                "HALF_LOSS": "HALF_WIN", "LOSS": "WIN"}[under]
        expected[under if selection == "UNDER" else over] += (
            exp(-total) * total**goals / factorial(goals)
        )
    actual = _poisson_total_five_state(total, selection, line)
    assert all(abs(actual[state] - expected[state]) < 1e-12 for state in expected)
    if selection == "UNDER":
        target = actual["WIN"] + (0.5 * actual["HALF_WIN"] if line != 2.0 else 0.0)
        if line == 2.0:
            target /= 1.0 - actual["PUSH"]
        assert isclose(_market_under_probability(total, line), target, abs_tol=1e-12)


def test_total_infer_v2_draft_real_54_under_x25_rows_have_zero_sse() -> None:
    fixture = Path(__file__).parents[1] / "fixtures/total_infer_v2_under_x25_v3.csv"
    assert hashlib.sha256(fixture.read_bytes()).hexdigest() == (
        "3365af13f7cee7ae29116ada7e82c6095424ba4dcdd8b88377eeecae438fcdb5"
    )
    with fixture.open(newline="") as source:
        rows = list(csv.DictReader(source))
    # Minimal columns extracted from the 1150-row 2026-09-23 historical CSV,
    # source SHA-256 c62207eb587dceb6a47ea1e6582d2556d5fc469c898fff25d2fecb4adc1f2f55.
    assert len(rows) == len({row["fixture_id"] for row in rows}) == 54
    assert {row["selection"] for row in rows} == {"UNDER"}
    for row in rows:
        line = float(row["exact_line"])
        boundary = int(line)
        assert line - boundary == 0.25
        observed = {state: float(row[column]) for state, column in (
            ("WIN", "p_win"), ("HALF_WIN", "p_half_win"),
            ("PUSH", "p_push"), ("HALF_LOSS", "p_half_loss"),
            ("LOSS", "p_loss"),
        )}
        # Solve lambda from P(T < boundary), independently of the code under test.
        lo, hi = 0.5, 6.0
        for _ in range(60):
            midpoint = (lo + hi) / 2.0
            p_below = sum(exp(-midpoint) * midpoint**k / factorial(k) for k in range(boundary))
            if p_below > observed["WIN"]:
                lo = midpoint
            else:
                hi = midpoint
        actual = _poisson_total_five_state((lo + hi) / 2.0, "UNDER", line)
        sse_v2 = sum((actual[state] - observed[state]) ** 2 for state in observed)
        assert sse_v2 < 1e-12, (row["fixture_id"], sse_v2)
        # V1 placed the boundary mass in HALF_LOSS, leaving HALF_WIN at zero.
        assert observed["HALF_WIN"] ** 2 > 0.01, row["fixture_id"]


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


@pytest.mark.parametrize("captured_at", [
    "2026-09-26T09:00:00Z", "2026-09-24T09:00:00Z",
    "2026-09-25T09:30:00.000001Z", "2026-09-25T08:29:59.999999Z",
])
def test_ah_quote_pair_rejects_same_capture_with_excess_time_skew(
    captured_at: str,
) -> None:
    pair = _ah_pair()
    pair["AWAY"]["quote_identity"]["captured_at"] = captured_at

    with pytest.raises(ValueError, match="QUOTE_PAIR_MISMATCH.*captured_at"):
        fuse_lambda_level(
            market="ASIAN_HANDICAP", selection="HOME", line=0.25,
            model_lambda_home=1.55, model_lambda_away=1.05,
            market_odds=pair,
        )


@pytest.mark.parametrize("captured_at", [
    "2026-09-25T09:29:59Z", "2026-09-25T09:30:00Z", "2026-09-25T08:30:00Z",
    "2026-09-25T17:00:00+08:00",
])
def test_ah_quote_pair_allows_capture_skew_at_most_30_minutes(captured_at: str) -> None:
    assert AH_QUOTE_CAPTURE_MAX_SKEW_SECONDS == 1800
    pair = _ah_pair()
    pair["AWAY"]["quote_identity"]["captured_at"] = captured_at

    result = fuse_lambda_level(
        market="ASIAN_HANDICAP", selection="HOME", line=0.25,
        model_lambda_home=1.55, model_lambda_away=1.05,
        market_odds=pair,
    )

    assert result.marker is None


@pytest.mark.parametrize("captured_at", [
    "MISSING", None, "not-a-timestamp", "2026-09-25T09:00:00", 123, {}, "",
])
def test_ah_quote_pair_rejects_missing_or_uncomparable_capture_time(
    captured_at: object,
) -> None:
    pair = _ah_pair()
    if captured_at == "MISSING":
        del pair["AWAY"]["quote_identity"]["captured_at"]
    else:
        pair["AWAY"]["quote_identity"]["captured_at"] = captured_at

    with pytest.raises(ValueError, match="QUOTE_PAIR_MISMATCH"):
        fuse_lambda_level(
            market="ASIAN_HANDICAP", selection="HOME", line=0.25,
            model_lambda_home=1.55, model_lambda_away=1.05,
            market_odds=pair,
        )


@pytest.mark.parametrize("missing", ["HOME", "AWAY"])
def test_ah_quote_pair_missing_side_is_distinct_from_mismatch(missing: str) -> None:
    pair = _ah_pair()
    del pair[missing]

    with pytest.raises(AhQuoteSideMissing, match="missing HOME or AWAY"):
        fuse_lambda_level(
            market="ASIAN_HANDICAP", selection="HOME", line=0.25,
            model_lambda_home=1.55, model_lambda_away=1.05,
            market_odds=pair,
        )
