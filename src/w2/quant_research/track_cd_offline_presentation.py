"""Offline Track C presentation and one-way Track D totals fade.

Inputs are already captured records.  This module has no database, Provider,
recommendation, or validation-sample writer.  Its output is presentation only.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isfinite

from w2.domain.profit import (
    FROZEN_FADE_DELTA,
    REBATE_RATE,
    track_d_binary_cashflow,
    track_d_fair_probability,
)
from w2.domain.profit import (
    REBATE_FORMULA_VERSION as REBATE_FORMULA_VERSION,
)
from w2.quant_research.track_b_lambda_level_fusion import (
    AhQuoteSideMissing,
    _distribution,
    _score_matrix,
    _validate_ah_quote_pair,
    five_state_cashflow,
    fuse_lambda_level,
)

FROZEN_TOTAL_SCALE = 1.0
FROZEN_REBATE = float(REBATE_RATE)
TRACK_D_APPROX_FORMULA_VERSION = "w2.track_d.binary_abs_profit_v2.v1"
TIER_PRIORITY = 0.05
TIER_GENERAL = 0.02
TIER_OBSERVE = 0.0
DISPLAY_STATES = frozenset({"ANALYSIS_PICK_ACTIVE", "NO_EDGE_CURRENT"})
FUSION_MARKET_MISSING = "FUSION_MARKET_MISSING"
QUOTE_PAIR_MISMATCH = "QUOTE_PAIR_MISMATCH"
NO_MARKET_ANCHOR_LABEL = "无市场锚·不参与档位"
# Candidate-kind taxonomy.  The Track D reversal candidate is an independent
# fade path (Pinnacle de-vig + FROZEN_FADE_DELTA) and is mutually exclusive with
# the OU intent gate: it must never re-enter the intent-signal threshold.  The
# Track B candidate is the factor-gate fusion path.
TRACK_B_FUSION = "TRACK_B_FUSION"
TRACK_D_FADE = "TRACK_D_FADE"
VALIDATION_SIGNAL = "VALIDATION_SIGNAL"
VALIDATION_SIGNAL_WATERMARK = "验证期信号 · 非正式推荐 · 不计入档位"


@dataclass(frozen=True)
class CapturedQuote:
    """A persisted market observation; fixture identity is provider_fixture_id."""

    provider_fixture_id: str
    capture_id: str
    bookmaker_id: str
    market: str
    selection: str
    line: float
    decimal_odds: float


@dataclass(frozen=True)
class Evaluation:
    fixture_id: str
    capture_id: str
    bookmaker_id: str
    market: str
    selection: str  # original, pre-fusion model direction
    line: float
    state: str
    model_lambda_home: float
    model_lambda_away: float
    channel_odds: float | None
    pinnacle_odds: Mapping[str, float] | None
    pinnacle_quote_pair: Mapping[str, object] | None = None


@dataclass(frozen=True)
class DisplayCandidate:
    fixture_id: str
    market: str
    selection: str
    line: float
    source: str
    tier: str
    fusion_ev: float | None
    pinnacle_fair_odds: float | None
    channel_odds: float | None
    channel_price_gap: float | None
    marker: str | None = None
    pure_model_probability: float | None = None
    market_anchor_note: str | None = None
    candidate_kind: str | None = None
    display_state: str = "ANALYSIS_PICK_ACTIVE"
    watermark: str | None = None
    official_recommendation: bool = False


def _price(value: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("odds must be numeric") from exc
    if not isfinite(result) or result <= 1.0:
        raise ValueError("odds must be finite and greater than 1")
    return result


def single_probability_cashflow(probability: float, decimal_odds: float) -> float:
    """Track D's registered binary approximation, not a five-state EV."""
    return track_d_binary_cashflow(probability, decimal_odds)


def _fair_probability(odds: Mapping[str, float], selection: str) -> float:
    return track_d_fair_probability(odds, selection)


def _tier(ev: float | None) -> str:
    if ev is None:
        return "不推"
    if ev >= TIER_PRIORITY:
        return "重点"
    if ev >= TIER_GENERAL:
        return "一般"
    if ev >= TIER_OBSERVE:
        return "观察"
    return "不推"


def _display(
    evaluation: Evaluation,
    *,
    selection: str,
    source: str,
    ev: float | None,
    odds: float | None,
    marker: str | None = None,
) -> DisplayCandidate:
    fair_odds = None
    if evaluation.market == "ASIAN_HANDICAP":
        if evaluation.pinnacle_quote_pair is not None:
            try:
                pair = _validate_ah_quote_pair(
                    evaluation.pinnacle_quote_pair,
                    selection=selection,
                    line=evaluation.line,
                )
                implied = {side: 1.0 / price for side, price in pair.items()}
                fair_odds = sum(implied.values()) / implied[selection]
            except AhQuoteSideMissing:
                marker = FUSION_MARKET_MISSING
                ev = None
            except ValueError:
                marker = QUOTE_PAIR_MISMATCH
                ev = None
    elif evaluation.pinnacle_odds is not None:
        try:
            fair_odds = 1.0 / _fair_probability(evaluation.pinnacle_odds, selection)
        except (KeyError, TypeError, ValueError):
            marker = FUSION_MARKET_MISSING
            ev = None
    if fair_odds is None:
        marker = marker or FUSION_MARKET_MISSING
        ev = None
    model_probability = None
    try:
        model_matrix = _score_matrix(
            evaluation.model_lambda_home,
            evaluation.model_lambda_away,
            rho=0.0,
            max_goals=12,
        )
        # Shared five-state settlement follows TOTAL_INFER_V2 (DRAFT): at an
        # integer total, UNDER x.25 is HALF_WIN and OVER x.25 is HALF_LOSS.
        model_distribution = _distribution(
            model_matrix, evaluation.market, selection, evaluation.line
        )
        model_probability = model_distribution["WIN"] + 0.5 * model_distribution["HALF_WIN"]
    except ValueError:
        pass
    is_fade = source == "TRACK_D"
    is_validation = is_fade and ev is not None and marker is None and odds is not None
    return DisplayCandidate(
        fixture_id=evaluation.fixture_id,
        market=evaluation.market,
        selection=selection,
        line=evaluation.line,
        source=source,
        # Validation signals never enter the official three-tier ladder.
        tier="不推" if is_fade else _tier(ev),
        fusion_ev=ev,
        pinnacle_fair_odds=fair_odds,
        channel_odds=odds,
        channel_price_gap=None if fair_odds is None or odds is None else odds - fair_odds,
        marker=marker,
        pure_model_probability=model_probability if marker is not None else None,
        market_anchor_note=NO_MARKET_ANCHOR_LABEL if marker is not None else None,
        candidate_kind=TRACK_D_FADE if is_fade else TRACK_B_FUSION,
        display_state=VALIDATION_SIGNAL if is_validation else "ANALYSIS_PICK_ACTIVE",
        watermark=VALIDATION_SIGNAL_WATERMARK if is_validation else None,
        official_recommendation=False,
    )


def assert_track_d_fade_exclusive(
    *,
    fade_triggered: bool,
    ou_intent_gate_passed: bool,
    totals_positive_recommendations: int,
) -> None:
    """Guard the R2 contract: fade is independent and OU emits zero picks."""
    if fade_triggered and ou_intent_gate_passed:
        raise AssertionError("TRACK_D_FADE_MUST_NOT_PASS_OU_INTENT_GATE")
    if totals_positive_recommendations != 0:
        raise AssertionError("TOTALS_INTENT_GATE_MUST_EMIT_ZERO_POSITIVE_RECOMMENDATIONS")


def _reverse_quote(e: Evaluation, observations: Sequence[CapturedQuote]) -> CapturedQuote | None:
    """Require the same snapshot, bookmaker, exact line and provider fixture ID."""
    matches = [
        quote for quote in observations
        if quote.provider_fixture_id == e.fixture_id
        and quote.capture_id == e.capture_id
        and quote.bookmaker_id == e.bookmaker_id
        and quote.market == "TOTALS"
        and quote.selection == "OVER"
        and quote.line == e.line
    ]
    if len(matches) > 1:
        raise ValueError("ambiguous reverse channel quote")
    return matches[0] if matches else None


def present_offline(
    evaluations: Sequence[Evaluation], observations: Sequence[CapturedQuote]
) -> list[DisplayCandidate]:
    """Return every factor-passed candidate, plus UNDER -> OVER fade candidates.

    No result, settlement, validation-sample, quota, or Top-N input is accepted.
    Missing market/channel data remains visible but cannot enter the priority tier.
    """
    displayed: list[DisplayCandidate] = []
    for e in evaluations:
        if e.state not in DISPLAY_STATES:
            continue
        if e.market not in {"TOTALS", "ASIAN_HANDICAP"}:
            raise ValueError("unsupported market")
        if e.selection not in ({"OVER", "UNDER"} if e.market == "TOTALS" else {"HOME", "AWAY"}):
            raise ValueError("invalid selection")
        original_odds = _price(e.channel_odds) if e.channel_odds is not None else None
        original_ev: float | None = None
        has_market = (
            e.pinnacle_quote_pair is not None if e.market == "ASIAN_HANDICAP"
            else e.pinnacle_odds is not None
        )
        original_marker: str | None = None
        if has_market and original_odds is not None:
            try:
                fused = fuse_lambda_level(
                    market=e.market, selection=e.selection, line=e.line,
                    model_lambda_home=e.model_lambda_home * FROZEN_TOTAL_SCALE,
                    model_lambda_away=e.model_lambda_away * FROZEN_TOTAL_SCALE,
                    market_odds=(
                        e.pinnacle_quote_pair if e.market == "ASIAN_HANDICAP"
                        else e.pinnacle_odds
                    ),
                )
                original_marker = fused.marker
                if original_marker is None:
                    # Keep Decimal arithmetic through the offline cashflow calculation;
                    # the display DTO remains float-based for its existing API contract.
                    original_ev = float(five_state_cashflow(fused.distribution, original_odds))
            except AhQuoteSideMissing:
                original_marker = FUSION_MARKET_MISSING
            except ValueError as exc:
                if "QUOTE_PAIR_MISMATCH" in str(exc):
                    original_marker = QUOTE_PAIR_MISMATCH
        displayed.append(_display(
            e, selection=e.selection, source="TRACK_B", ev=original_ev,
            odds=original_odds,
            marker=original_marker or (FUSION_MARKET_MISSING if original_ev is None else None),
        ))

        if e.market != "TOTALS" or e.selection != "UNDER":
            continue
        reverse = _reverse_quote(e, observations)
        reverse_odds = _price(reverse.decimal_odds) if reverse is not None else None
        fade_ev: float | None = None
        if reverse_odds is not None and e.pinnacle_odds is not None:
            try:
                p_over = _fair_probability(e.pinnacle_odds, "OVER")
                p_fade = min(0.99, max(0.01, p_over + FROZEN_FADE_DELTA))
                fade_ev = single_probability_cashflow(p_fade, reverse_odds)
            except (KeyError, TypeError, ValueError):
                pass
        displayed.append(_display(
            e, selection="OVER", source="TRACK_D", ev=fade_ev,
            odds=reverse_odds,
            marker=FUSION_MARKET_MISSING if fade_ev is None else None,
        ))
    return displayed
