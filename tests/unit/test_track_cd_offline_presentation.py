from __future__ import annotations

import inspect
from math import isclose

import pytest

from w2.quant_research.track_b_lambda_level_fusion import FROZEN_W_AH, FROZEN_W_TOTALS
from w2.quant_research.track_cd_offline_presentation import (
    FROZEN_FADE_DELTA,
    FROZEN_REBATE,
    FROZEN_TOTAL_SCALE,
    TIER_GENERAL,
    TIER_OBSERVE,
    TIER_PRIORITY,
    CapturedQuote,
    Evaluation,
    _tier,
    present_offline,
    single_probability_cashflow,
)


def _evaluation(**changes: object) -> Evaluation:
    values = dict(
        fixture_id="123", capture_id="snapshot-1", bookmaker_id="2",
        market="TOTALS", selection="UNDER", line=2.5,
        state="NO_EDGE_CURRENT", model_lambda_home=1.4,
        model_lambda_away=1.1, channel_odds=1.9,
        pinnacle_odds={"OVER": 2.0, "UNDER": 2.0},
    )
    values.update(changes)
    return Evaluation(**values)


def _quote(**changes: object) -> CapturedQuote:
    values = dict(
        provider_fixture_id="123", capture_id="snapshot-1", bookmaker_id="2",
        market="TOTALS", selection="OVER", line=2.5, decimal_odds=2.0,
    )
    values.update(changes)
    return CapturedQuote(**values)


def test_frozen_parameters_and_all_four_tier_boundaries() -> None:
    assert (FROZEN_TOTAL_SCALE, FROZEN_W_AH, FROZEN_W_TOTALS) == (1.0, 0.9, 0.0)
    assert (FROZEN_FADE_DELTA, FROZEN_REBATE) == (0.05, 0.025)
    assert (TIER_PRIORITY, TIER_GENERAL, TIER_OBSERVE) == (0.05, 0.02, 0.0)
    assert [_tier(x) for x in (0.05, 0.049, 0.02, 0.019, 0.0, -0.001)] == [
        "重点", "一般", "一般", "观察", "观察", "不推"
    ]
    assert set(inspect.signature(present_offline).parameters) == {"evaluations", "observations"}


def test_under_fade_uses_same_snapshot_provider_fixture_bookmaker_and_line() -> None:
    e = _evaluation()
    wrong = [
        _quote(provider_fixture_id="api_football:123"),
        _quote(capture_id="snapshot-2"),
        _quote(bookmaker_id="3"),
        _quote(line=2.75),
        _quote(selection="UNDER"),
    ]
    missing = present_offline([e], wrong)
    assert len(missing) == 2
    assert missing[1].marker == "FUSION_MARKET_MISSING"
    assert missing[1].tier == "不推"

    original, faded = present_offline([e], [*wrong, _quote()])
    assert original.source == "TRACK_B"
    assert faded.source == "TRACK_D"
    assert faded.selection == "OVER"
    assert isclose(faded.fusion_ev, single_probability_cashflow(0.55, 2.0))
    assert faded.tier == "重点"
    assert isclose(faded.pinnacle_fair_odds, 2.0)
    assert isclose(faded.channel_price_gap, 0.0)


def test_over_does_not_reverse_and_blocked_is_not_displayed() -> None:
    rows = present_offline(
        [_evaluation(selection="OVER"), _evaluation(state="BLOCKED_BY_FACTOR")],
        [_quote()],
    )
    assert len(rows) == 1
    assert rows[0].source == "TRACK_B"


def test_missing_pinnacle_or_channel_remains_visible_but_not_priority() -> None:
    rows = present_offline(
        [_evaluation(pinnacle_odds=None), _evaluation(capture_id="other")],
        [_quote()],
    )
    assert len(rows) == 4
    assert all(row.marker == "FUSION_MARKET_MISSING" for row in rows[:2])
    assert rows[3].marker == "FUSION_MARKET_MISSING"
    assert rows[3].tier == "不推"


def test_ambiguous_reverse_quote_fails_closed() -> None:
    with pytest.raises(ValueError, match="ambiguous"):
        present_offline([_evaluation()], [_quote(), _quote(decimal_odds=2.05)])
