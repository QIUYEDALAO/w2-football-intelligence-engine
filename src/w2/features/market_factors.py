from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from w2.competitions.registry import CoverageProfile
from w2.features.asof import assert_not_future
from w2.features.framework import (
    FeatureContext,
    FeatureContribution,
    FeatureStatus,
    TeamSide,
    coverage_or_unavailable,
)
from w2.markets.consensus import MarketConsensusBuilder, OddsQuote
from w2.markets.movement import MarketSnapshot, MovementFeatureBuilder


@dataclass(frozen=True, kw_only=True)
class BookmakerQuote:
    bookmaker: str
    market: str
    selection: str
    decimal_odds: Decimal
    captured_at: datetime
    provider_updated_at: datetime
    line: Decimal | None = None
    suspended: bool = False
    live: bool = False
    stale: bool = False


def market_movement_factor(
    *,
    context: FeatureContext,
    profile: CoverageProfile,
    snapshots: list[MarketSnapshot],
    weight: float = 0.16,
) -> FeatureContribution:
    blocked = coverage_or_unavailable(
        profile=profile,
        key="bookmaker_depth",
        feature_id="F1_MARKET_MOVEMENT",
        label="盘口变化",
        weight=weight,
    )
    if blocked is not None:
        return blocked
    try:
        for snapshot in snapshots:
            assert_not_future(snapshot.captured_at, context.as_of, label="market_movement")
    except ValueError as exc:
        return FeatureContribution(
            feature_id="F1_MARKET_MOVEMENT",
            label="盘口变化",
            status=FeatureStatus.LEAKAGE_BLOCKED,
            score=None,
            weight=weight,
            reason=str(exc),
            coverage_key="bookmaker_depth",
        )
    features = MovementFeatureBuilder().build(snapshots)
    if features.first_seen_to_current is None:
        return FeatureContribution(
            feature_id="F1_MARKET_MOVEMENT",
            label="盘口变化",
            status=FeatureStatus.INSUFFICIENT_DATA,
            score=None,
            weight=weight,
            reason="INSUFFICIENT_MARKET_SNAPSHOTS",
            coverage_key="bookmaker_depth",
            diagnostics=features.diagnostics,
        )
    score = max(min(-features.first_seen_to_current / 0.25, 1.0), -1.0)
    side = TeamSide.HOME if score > 0 else TeamSide.AWAY if score < 0 else TeamSide.NEUTRAL
    return FeatureContribution(
        feature_id="F1_MARKET_MOVEMENT",
        label="盘口变化",
        status=FeatureStatus.READY,
        score=score,
        weight=weight,
        side=side,
        reason="OPEN_TO_CURRENT_MOVE_CAPTURED",
        risk="盘口变化不是庄家意图证明，U2 再做意图判断。",
        coverage_key="bookmaker_depth",
        diagnostics=features.diagnostics,
        observed_at=max(snapshot.captured_at for snapshot in snapshots),
        inputs={
            "first_seen_to_current": features.first_seen_to_current,
            "recent_move": features.recent_move,
            "velocity": features.velocity,
            "acceleration": features.acceleration,
            "main_line_change": features.main_line_change,
        },
    )


def bookmaker_divergence_factor(
    *,
    context: FeatureContext,
    profile: CoverageProfile,
    quotes: list[BookmakerQuote],
    sharp_bookmakers: frozenset[str] = frozenset({"Pinnacle"}),
    weight: float = 0.12,
) -> FeatureContribution:
    blocked = coverage_or_unavailable(
        profile=profile,
        key="bookmaker_depth",
        feature_id="F2_BOOKMAKER_DIVERGENCE",
        label="庄家分歧",
        weight=weight,
    )
    if blocked is not None:
        return blocked
    try:
        for quote in quotes:
            assert_not_future(quote.provider_updated_at, context.as_of, label="bookmaker_quote")
    except ValueError as exc:
        return FeatureContribution(
            feature_id="F2_BOOKMAKER_DIVERGENCE",
            label="庄家分歧",
            status=FeatureStatus.LEAKAGE_BLOCKED,
            score=None,
            weight=weight,
            reason=str(exc),
            coverage_key="bookmaker_depth",
        )
    odds_quotes = [
        OddsQuote(
            bookmaker=quote.bookmaker,
            market=quote.market,
            selection=quote.selection,
            decimal_odds=quote.decimal_odds,
            captured_at=quote.captured_at,
            provider_updated_at=quote.provider_updated_at,
            line=quote.line,
            suspended=quote.suspended,
            live=quote.live,
            stale=quote.stale,
        )
        for quote in quotes
    ]
    consensus = MarketConsensusBuilder().build(odds_quotes, as_of_time=context.as_of)
    if consensus.fair_decimal_odds is None:
        return FeatureContribution(
            feature_id="F2_BOOKMAKER_DIVERGENCE",
            label="庄家分歧",
            status=FeatureStatus.INSUFFICIENT_DATA,
            score=None,
            weight=weight,
            reason="INSUFFICIENT_BOOKMAKERS",
            coverage_key="bookmaker_depth",
            diagnostics=consensus.diagnostics,
            inputs={"effective_bookmakers": consensus.effective_bookmakers},
        )
    sharp = [quote for quote in quotes if quote.bookmaker in sharp_bookmakers]
    soft = [quote for quote in quotes if quote.bookmaker not in sharp_bookmakers]
    sharp_soft_gap = None
    if sharp and soft:
        sharp_avg = sum(float(quote.decimal_odds) for quote in sharp) / len(sharp)
        soft_avg = sum(float(quote.decimal_odds) for quote in soft) / len(soft)
        sharp_soft_gap = sharp_avg - soft_avg
    dispersion = consensus.dispersion or 0.0
    score = max(min(dispersion / 0.30, 1.0), 0.0)
    return FeatureContribution(
        feature_id="F2_BOOKMAKER_DIVERGENCE",
        label="庄家分歧",
        status=FeatureStatus.READY if consensus.status == "READY" else FeatureStatus.DEGRADED,
        score=score,
        weight=weight,
        reason="CONSENSUS_DISPERSION_COMPUTED",
        risk="分歧只表示市场不一致，不单独构成推荐。",
        coverage_key="bookmaker_depth",
        diagnostics=consensus.diagnostics + tuple(f"OUTLIER:{item}" for item in consensus.outliers),
        observed_at=max(quote.provider_updated_at for quote in quotes),
        inputs={
            "effective_bookmakers": consensus.effective_bookmakers,
            "dispersion": consensus.dispersion,
            "coherence": consensus.coherence,
            "sharp_soft_gap": sharp_soft_gap,
        },
    )
