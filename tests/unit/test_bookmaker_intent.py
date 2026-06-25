from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from w2.competitions.registry import CompetitionRegistry
from w2.features.framework import FeatureContext, TeamSide
from w2.features.market_factors import BookmakerQuote
from w2.markets.movement import MarketSnapshot
from w2.strategy.bookmaker_intent import (
    IntentComponent,
    IntentSignal,
    infer_bookmaker_intent,
)

NOW = datetime(2026, 6, 25, 12, 0, tzinfo=UTC)


def context() -> FeatureContext:
    return FeatureContext(
        fixture_id="1489404",
        competition_id="world_cup_2026",
        home_team_id="10",
        away_team_id="20",
        kickoff_at=NOW + timedelta(hours=6),
        as_of=NOW,
    )


def profile():
    return CompetitionRegistry().require_enabled("world_cup_2026").coverage_profile


def snapshot(hours_ago: int, price: str) -> MarketSnapshot:
    return MarketSnapshot(
        fixture_id="1489404",
        market="ASIAN_HANDICAP",
        selection="Home -0.5",
        price=Decimal(price),
        captured_at=NOW - timedelta(hours=hours_ago),
        snapshot_semantics="CAPTURED_AT",
        line=Decimal("-0.5"),
    )


def quote(bookmaker: str, odds: str) -> BookmakerQuote:
    return BookmakerQuote(
        bookmaker=bookmaker,
        market="ASIAN_HANDICAP",
        selection="Home -0.5",
        decimal_odds=Decimal(odds),
        captured_at=NOW - timedelta(minutes=2),
        provider_updated_at=NOW - timedelta(minutes=2),
        line=Decimal("-0.5"),
    )


def test_open_to_current_home_lean_is_deterministic() -> None:
    first = infer_bookmaker_intent(
        context=context(),
        profile=profile(),
        market_kind="AH",
        snapshots=[snapshot(12, "2.15"), snapshot(1, "1.88")],
        quotes=[quote("Pinnacle", "1.88"), quote("SoftBook", "1.91")],
    )
    second = infer_bookmaker_intent(
        context=context(),
        profile=profile(),
        market_kind="AH",
        snapshots=[snapshot(12, "2.15"), snapshot(1, "1.88")],
        quotes=[quote("Pinnacle", "1.88"), quote("SoftBook", "1.91")],
    )

    assert first == second
    assert first.intent == IntentSignal.HOME_LEAN
    assert first.implied_side == TeamSide.HOME
    assert first.confidence > 0.5
    assert first.candidate is False
    assert first.formal_recommendation is False


def test_late_reversal_changes_intent_evidence() -> None:
    intent = infer_bookmaker_intent(
        context=context(),
        profile=profile(),
        market_kind="AH",
        snapshots=[
            snapshot(12, "2.10"),
            snapshot(4, "1.82"),
            snapshot(1, "1.96"),
        ],
        quotes=[quote("Pinnacle", "1.96"), quote("SoftBook", "1.98")],
    )

    assert intent.intent in {IntentSignal.HOME_LEAN, IntentSignal.BALANCED}
    assert any(item.component == IntentComponent.LATE_REVERSAL for item in intent.evidence)


def test_high_divergence_without_direction_is_conflicted() -> None:
    intent = infer_bookmaker_intent(
        context=context(),
        profile=profile(),
        market_kind="AH",
        snapshots=[snapshot(12, "2.00"), snapshot(1, "2.00")],
        quotes=[quote("Pinnacle", "1.65"), quote("SoftBook", "2.20")],
    )

    assert intent.intent == IntentSignal.CONFLICTED
    assert any(item.component == IntentComponent.BOOKMAKER_DIVERGENCE for item in intent.evidence)


def test_sharp_soft_gap_contributes_to_intent() -> None:
    intent = infer_bookmaker_intent(
        context=context(),
        profile=profile(),
        market_kind="OU",
        snapshots=[snapshot(12, "1.95"), snapshot(1, "1.95")],
        quotes=[quote("Pinnacle", "1.82"), quote("SoftBook", "1.96")],
    )

    assert intent.intent == IntentSignal.OVER_LEAN
    assert intent.implied_side == TeamSide.HOME
    assert any(item.component == IntentComponent.SHARP_SOFT_DIVERGENCE for item in intent.evidence)


def test_future_snapshot_blocks_intent_as_leakage() -> None:
    intent = infer_bookmaker_intent(
        context=context(),
        profile=profile(),
        market_kind="AH",
        snapshots=[
            MarketSnapshot(
                fixture_id="1489404",
                market="ASIAN_HANDICAP",
                selection="Home -0.5",
                price=Decimal("1.90"),
                captured_at=NOW + timedelta(minutes=1),
                snapshot_semantics="CAPTURED_AT",
                line=Decimal("-0.5"),
            )
        ],
        quotes=[quote("Pinnacle", "1.90"), quote("SoftBook", "1.92")],
    )

    assert intent.intent == IntentSignal.LEAKAGE_BLOCKED
    assert intent.confidence == 0.0
