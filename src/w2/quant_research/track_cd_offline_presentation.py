"""Offline Track C presentation and one-way Track D totals fade.

Inputs are already captured records.  This module has no database, Provider,
recommendation, or validation-sample writer.  Its output is presentation only.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isfinite

from w2.quant_research.track_b_lambda_level_fusion import (
    five_state_cashflow,
    fuse_lambda_level,
)

FROZEN_TOTAL_SCALE = 1.0
FROZEN_FADE_DELTA = 0.05
FROZEN_REBATE = 0.025
TIER_PRIORITY = 0.05
TIER_GENERAL = 0.02
TIER_OBSERVE = 0.0
DISPLAY_STATES = frozenset({"ANALYSIS_PICK_ACTIVE", "NO_EDGE_CURRENT"})
FUSION_MARKET_MISSING = "FUSION_MARKET_MISSING"


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


def _price(value: float) -> float:
    result = float(value)
    if not isfinite(result) or result <= 1.0:
        raise ValueError("odds must be finite and greater than 1")
    return result


def _fair_probability(odds: Mapping[str, float], selection: str) -> float:
    sides = ("OVER", "UNDER") if selection in {"OVER", "UNDER"} else ("HOME", "AWAY")
    implied = {side: 1.0 / _price(odds[side]) for side in sides}
    return implied[selection] / sum(implied.values())


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
    if evaluation.pinnacle_odds is not None:
        try:
            fair_odds = 1.0 / _fair_probability(evaluation.pinnacle_odds, selection)
        except (KeyError, ValueError):
            marker = FUSION_MARKET_MISSING
            ev = None
    if fair_odds is None:
        marker = FUSION_MARKET_MISSING
        ev = None
    return DisplayCandidate(
        fixture_id=evaluation.fixture_id,
        market=evaluation.market,
        selection=selection,
        line=evaluation.line,
        source=source,
        tier=_tier(ev),
        fusion_ev=ev,
        pinnacle_fair_odds=fair_odds,
        channel_odds=odds,
        channel_price_gap=None if fair_odds is None or odds is None else odds - fair_odds,
        marker=marker,
    )


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
        if e.pinnacle_odds is not None and original_odds is not None:
            try:
                fused = fuse_lambda_level(
                    market=e.market, selection=e.selection, line=e.line,
                    model_lambda_home=e.model_lambda_home * FROZEN_TOTAL_SCALE,
                    model_lambda_away=e.model_lambda_away * FROZEN_TOTAL_SCALE,
                    market_odds=e.pinnacle_odds,
                )
                original_ev = five_state_cashflow(
                    fused.distribution, original_odds, rebate=FROZEN_REBATE
                )
            except (KeyError, ValueError):
                pass
        displayed.append(_display(
            e, selection=e.selection, source="TRACK_B", ev=original_ev,
            odds=original_odds,
            marker=FUSION_MARKET_MISSING if original_ev is None else None,
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
                fade_ev = p_fade * reverse_odds - 1.0 + FROZEN_REBATE
            except (KeyError, ValueError):
                pass
        displayed.append(_display(
            e, selection="OVER", source="TRACK_D", ev=fade_ev,
            odds=reverse_odds,
            marker=FUSION_MARKET_MISSING if fade_ev is None else None,
        ))
    return displayed
