from __future__ import annotations

import inspect
from math import exp, isclose

import pytest

from w2.quant_research import track_cd_offline_presentation as track_cd
from w2.quant_research.track_b_lambda_level_fusion import FROZEN_W_AH, FROZEN_W_TOTALS
from w2.quant_research.track_cd_offline_presentation import (
    FROZEN_FADE_DELTA,
    FROZEN_REBATE,
    FROZEN_TOTAL_SCALE,
    TIER_GENERAL,
    TIER_OBSERVE,
    TIER_PRIORITY,
    CapturedQuote,
    DisplayCandidate,
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


def _ah_quote_pair() -> dict[str, dict[str, object]]:
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
        for side, side_line in (("HOME", 0.25), ("AWAY", -0.25))
    }


def _ah_evaluation(**changes: object) -> Evaluation:
    values = dict(
        fixture_id="123", capture_id="snapshot-1", bookmaker_id="2",
        market="ASIAN_HANDICAP", selection="HOME", line=0.25,
        state="NO_EDGE_CURRENT", model_lambda_home=1.4,
        model_lambda_away=1.1, channel_odds=1.9,
        pinnacle_odds=None, pinnacle_quote_pair=_ah_quote_pair(),
    )
    values.update(changes)
    return Evaluation(**values)


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
    assert faded.tier == "不推"
    assert faded.display_state == track_cd.VALIDATION_SIGNAL
    assert faded.watermark == track_cd.VALIDATION_SIGNAL_WATERMARK
    assert faded.official_recommendation is False
    assert isclose(faded.pinnacle_fair_odds, 2.0)
    assert isclose(faded.channel_price_gap, 0.0)


def test_none_pinnacle_price_fails_closed_at_offline_display_boundary() -> None:
    evaluation = _evaluation(pinnacle_odds={"OVER": None, "UNDER": 2.0})

    displayed = present_offline([evaluation], [_quote()])

    assert len(displayed) == 2
    assert [candidate.source for candidate in displayed] == ["TRACK_B", "TRACK_D"]
    assert all(isinstance(candidate, DisplayCandidate) for candidate in displayed)
    assert all(candidate.marker == "FUSION_MARKET_MISSING" for candidate in displayed)
    assert all(candidate.fusion_ev is None for candidate in displayed)
    assert all(candidate.tier == "不推" for candidate in displayed)


@pytest.mark.parametrize("odds", [None, "not-numeric", {}, 0, -1, float("nan"), float("inf")])
def test_invalid_binary_odds_raise_value_error(odds: object) -> None:
    with pytest.raises(ValueError, match="odds must be"):
        single_probability_cashflow(0.5, odds)


def test_fair_probability_type_error_is_contained_at_both_call_sites(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def unavailable_probability(odds: object, selection: str) -> float:
        calls.append(selection)
        raise TypeError("malformed market price")

    monkeypatch.setattr(track_cd, "_fair_probability", unavailable_probability)
    displayed = present_offline([_evaluation()], [_quote()])

    assert calls == ["UNDER", "OVER", "OVER"]
    assert len(displayed) == 2
    assert all(candidate.marker == "FUSION_MARKET_MISSING" for candidate in displayed)
    assert all(candidate.fusion_ev is None for candidate in displayed)
    assert all(candidate.tier == "不推" for candidate in displayed)


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


def test_missing_market_under_x25_displays_half_win_model_probability() -> None:
    row = present_offline(
        [_evaluation(line=2.25, pinnacle_odds=None)], []
    )[0]
    total = 1.4 + 1.1
    expected = exp(-total) * (1.0 + total + 0.5 * total**2 / 2.0)
    assert row.marker == "FUSION_MARKET_MISSING"
    assert row.tier == "不推"
    assert isclose(row.pure_model_probability, expected, abs_tol=1e-8)


def test_ah_missing_side_marks_fusion_market_missing() -> None:
    pair = _ah_quote_pair()
    del pair["AWAY"]

    rows = present_offline([_ah_evaluation(pinnacle_quote_pair=pair)], [])

    assert len(rows) == 1
    row = rows[0]
    assert row.marker == "FUSION_MARKET_MISSING"
    assert row.tier == "不推"
    assert row.fusion_ev is None
    assert row.pure_model_probability is not None
    assert row.market_anchor_note == track_cd.NO_MARKET_ANCHOR_LABEL


def test_ah_identity_mismatch_marks_quote_pair_mismatch() -> None:
    pair = _ah_quote_pair()
    pair["AWAY"]["quote_identity"]["bookmaker_id"] = "9"

    rows = present_offline([_ah_evaluation(pinnacle_quote_pair=pair)], [])

    assert len(rows) == 1
    row = rows[0]
    assert row.marker == "QUOTE_PAIR_MISMATCH"
    assert row.tier == "不推"
    assert row.fusion_ev is None


def test_reversal_candidate_kind_is_track_d_fade_and_mutually_exclusive() -> None:
    rows = present_offline([_evaluation()], [_quote()])

    assert [row.source for row in rows] == ["TRACK_B", "TRACK_D"]
    assert rows[0].candidate_kind == track_cd.TRACK_B_FUSION
    assert rows[1].candidate_kind == track_cd.TRACK_D_FADE
    # Mutual exclusion: the fade candidate is a distinct independent path that
    # never shares the fusion candidate's kind.
    assert rows[0].candidate_kind != rows[1].candidate_kind


def test_reversal_candidate_uses_independent_fade_path_not_intent_gate() -> None:
    rows = present_offline([_evaluation()], [_quote()])
    fade = rows[1]

    assert fade.candidate_kind == track_cd.TRACK_D_FADE
    p_over = (1.0 / 2.0) / ((1.0 / 2.0) + (1.0 / 2.0))
    p_fade = min(0.99, max(0.01, p_over + FROZEN_FADE_DELTA))
    assert fade.fusion_ev == single_probability_cashflow(p_fade, 2.0)


def test_fade_exclusivity_assertion_requires_zero_totals_intent_output() -> None:
    track_cd.assert_track_d_fade_exclusive(
        fade_triggered=True,
        ou_intent_gate_passed=False,
        totals_positive_recommendations=0,
    )
    with pytest.raises(AssertionError, match="TOTALS_INTENT_GATE"):
        track_cd.assert_track_d_fade_exclusive(
            fade_triggered=True,
            ou_intent_gate_passed=False,
            totals_positive_recommendations=1,
        )
    with pytest.raises(AssertionError, match="OU_INTENT_GATE"):
        track_cd.assert_track_d_fade_exclusive(
            fade_triggered=True,
            ou_intent_gate_passed=True,
            totals_positive_recommendations=0,
        )
