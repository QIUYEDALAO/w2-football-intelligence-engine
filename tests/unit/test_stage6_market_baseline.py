from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from w2.domain.enums import SettlementOutcome
from w2.domain.odds import settle_asian_handicap
from w2.markets.consensus import MarketConsensusBuilder, OddsQuote
from w2.markets.devig import DevigMethod, devig
from w2.markets.movement import MarketSnapshot, MovementFeatureBuilder
from w2.markets.poisson import DixonColesBaseline, fit_total_goals_mu
from w2.markets.quality import MarketQualityAssessor

NOW = datetime(2026, 6, 1, 12, tzinfo=UTC)


def quote(bookmaker: str, price: str, minutes_old: int = 1) -> OddsQuote:
    return OddsQuote(
        bookmaker=bookmaker,
        market="ONE_X_TWO",
        selection="HOME",
        decimal_odds=Decimal(price),
        captured_at=NOW,
        provider_updated_at=NOW - timedelta(minutes=minutes_old),
    )


def test_consensus_outlier_staleness_and_single_bookmaker_guard() -> None:
    single = MarketConsensusBuilder().build([quote("solo", "2.00")], as_of_time=NOW)
    assert single.status == "INSUFFICIENT_INPUT"
    assert "SINGLE_BOOKMAKER_NOT_FORMAL_CONSENSUS" in single.diagnostics
    consensus = MarketConsensusBuilder().build(
        [
            quote("a", "2.00"),
            quote("b", "2.02"),
            quote("c", "2.01", minutes_old=90),
            quote("outlier", "9.00"),
        ],
        as_of_time=NOW,
    )
    assert consensus.effective_bookmakers >= 2
    assert "outlier" in consensus.outliers
    assert consensus.status in {"READY", "WATCH_ONLY"}


def test_devig_methods_sum_to_one_and_handle_extreme_odds() -> None:
    odds = {"HOME": Decimal("1.01"), "DRAW": Decimal("34"), "AWAY": Decimal("99")}
    for method in DevigMethod:
        result = devig(odds, method)
        assert abs(sum(result.probabilities.values()) - 1.0) < 1e-9
        assert all(value > 0 for value in result.probabilities.values())
    with pytest.raises(ValueError):
        devig({"HOME": Decimal("1.0"), "AWAY": Decimal("2.0")}, DevigMethod.PROPORTIONAL)


def test_ou_ladder_fit_and_median_ab_are_available() -> None:
    fit = fit_total_goals_mu(
        {
            Decimal("1.5"): 0.25,
            Decimal("2.5"): 0.52,
            Decimal("3.5"): 0.76,
        }
    )
    assert fit.status in {"READY", "WATCH_ONLY"}
    assert 0.5 <= fit.mu <= 6.5
    assert set(fit.residuals) == {"1.5", "2.5", "3.5"}


def test_score_matrix_derives_markets_and_ah_quarter_settlement() -> None:
    output = DixonColesBaseline().build(
        one_x_two_probabilities={"HOME": 0.45, "DRAW": 0.28, "AWAY": 0.27},
        total_mu=Decimal("2.65"),
        asian_line=Decimal("-0.25"),
    )
    assert abs(sum(output.score_matrix.values()) - 1.0) < 1e-9
    assert abs(sum(output.one_x_two.values()) - 1.0) < 1e-9
    assert set(output.totals) == {"OVER", "UNDER"}
    assert set(output.btts) == {"YES", "NO"}
    assert settle_asian_handicap(1, 1, "HOME", Decimal("-0.25")) == SettlementOutcome.HALF_LOSS


def test_movement_semantic_guard_and_quality_status() -> None:
    blocked = MovementFeatureBuilder().build(
        [
            MarketSnapshot(
                fixture_id="fixture",
                market="ONE_X_TWO",
                selection="HOME",
                price=Decimal("2.0"),
                captured_at=NOW,
                snapshot_semantics="UNKNOWN_PREMATCH_AGGREGATE",
            )
        ]
    )
    assert blocked.status == "CALIBRATION_REQUIRED"
    assert "MOVEMENT_DISABLED_FOR_NON_CAPTURED_AT" in blocked.diagnostics
    movement = MovementFeatureBuilder().build(
        [
            MarketSnapshot(
                fixture_id="fixture",
                market="TOTALS",
                selection="OVER",
                price=Decimal("2.1"),
                captured_at=NOW - timedelta(hours=1),
                snapshot_semantics="CAPTURED_AT",
                line=Decimal("2.5"),
            ),
            MarketSnapshot(
                fixture_id="fixture",
                market="TOTALS",
                selection="OVER",
                price=Decimal("1.9"),
                captured_at=NOW,
                snapshot_semantics="CAPTURED_AT",
                line=Decimal("2.75"),
            ),
        ]
    )
    assert movement.status == "WARN_ONLY"
    assert movement.main_line_change == 0.25
    quality = MarketQualityAssessor().assess(
        bookmaker_count=5,
        stale_fraction=0.0,
        dispersion=0.05,
        coherence=0.95,
    )
    assert quality.status == "READY"
