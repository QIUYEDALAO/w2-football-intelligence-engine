from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from w2.domain.enums import MarketType, SettlementOutcome
from w2.domain.odds import settle_asian_handicap, settle_total_goals
from w2.markets.value_engine import (
    MarketValueEngine,
    OddsFormat,
    OddsQuote,
    decimal_to_hong_kong,
    expected_value,
    fair_decimal_odds,
    hong_kong_to_decimal,
    pair_bookmaker_quotes,
    settlement_distribution_ah,
    settlement_distribution_totals,
)

NOW = datetime(2026, 6, 22, 12, tzinfo=UTC)


def test_hong_kong_decimal_conversion() -> None:
    assert hong_kong_to_decimal(Decimal("0.79")) == Decimal("1.7900")
    assert hong_kong_to_decimal(Decimal("1.07")) == Decimal("2.0700")
    assert decimal_to_hong_kong(Decimal("1.79")) == Decimal("0.7900")
    assert decimal_to_hong_kong(Decimal("2.07")) == Decimal("1.0700")


def test_asian_handicap_settlement_cases() -> None:
    assert settle_asian_handicap(1, 0, "HOME", Decimal("-1")) == SettlementOutcome.PUSH
    assert settle_asian_handicap(1, 0, "HOME", Decimal("-1.25")) == SettlementOutcome.HALF_LOSS
    assert settle_asian_handicap(0, 1, "HOME", Decimal("+1")) == SettlementOutcome.PUSH
    assert settle_asian_handicap(0, 1, "HOME", Decimal("+1.25")) == SettlementOutcome.HALF_WIN
    assert settle_asian_handicap(1, 0, "HOME", Decimal("-0.75")) == SettlementOutcome.HALF_WIN
    assert settle_asian_handicap(0, 1, "HOME", Decimal("+0.75")) == SettlementOutcome.HALF_LOSS


def test_totals_settlement_cases() -> None:
    assert settle_total_goals(2, "OVER", Decimal("2.25")) == SettlementOutcome.HALF_LOSS
    assert settle_total_goals(2, "UNDER", Decimal("2.25")) == SettlementOutcome.HALF_WIN
    assert settle_total_goals(3, "OVER", Decimal("2.75")) == SettlementOutcome.HALF_WIN
    assert settle_total_goals(3, "UNDER", Decimal("2.75")) == SettlementOutcome.HALF_LOSS
    assert settle_total_goals(2, "OVER", Decimal("2.0")) == SettlementOutcome.PUSH
    assert settle_total_goals(2, "UNDER", Decimal("2.0")) == SettlementOutcome.PUSH


def test_distribution_ev_and_fair_odds_zero_ev() -> None:
    matrix = {
        (1, 0): Decimal("0.50"),
        (1, 1): Decimal("0.25"),
        (0, 1): Decimal("0.25"),
    }
    distribution = settlement_distribution_ah(matrix, selection="HOME", line=Decimal("-0.25"))
    assert distribution.full_win_probability == Decimal("0.50")
    assert distribution.half_loss_probability == Decimal("0.25")
    assert distribution.full_loss_probability == Decimal("0.25")
    assert (
        distribution.full_win_probability
        + distribution.half_win_probability
        + distribution.push_probability
        + distribution.half_loss_probability
        + distribution.full_loss_probability
    ) == Decimal("1")
    fair = fair_decimal_odds(distribution)
    assert abs(expected_value(fair, distribution)) <= Decimal("0.0001")


def test_totals_distribution_quarter_lines() -> None:
    matrix = {
        (1, 0): Decimal("0.25"),
        (1, 1): Decimal("0.25"),
        (2, 1): Decimal("0.25"),
        (3, 1): Decimal("0.25"),
    }
    over = settlement_distribution_totals(matrix, selection="OVER", line=Decimal("2.75"))
    under = settlement_distribution_totals(matrix, selection="UNDER", line=Decimal("2.75"))
    assert over.full_loss_probability == Decimal("0.50")
    assert over.half_win_probability == Decimal("0.25")
    assert over.full_win_probability == Decimal("0.25")
    assert under.full_win_probability == Decimal("0.50")
    assert under.half_loss_probability == Decimal("0.25")
    assert under.full_loss_probability == Decimal("0.25")


def quote(bookmaker_id: str, market: MarketType, selection: str, line: Decimal | None) -> OddsQuote:
    return OddsQuote(
        bookmaker_id=bookmaker_id,
        bookmaker_name=f"book-{bookmaker_id}",
        market_type=market,
        selection=selection,
        line=line,
        raw_odds=Decimal("1.95"),
        raw_odds_format=OddsFormat.DECIMAL,
        decimal_odds=Decimal("1.95"),
        captured_at=NOW,
        provider_updated_at=NOW,
        suspended=False,
        live=False,
        provenance="test",
    )


def test_bookmaker_pair_rejections() -> None:
    home = quote("pinnacle", MarketType.ASIAN_HANDICAP, "HOME", Decimal("-1"))
    away = quote("pinnacle", MarketType.ASIAN_HANDICAP, "AWAY", Decimal("-1"))
    assert pair_bookmaker_quotes(home, away, tolerance_seconds=5).pair_valid
    assert not pair_bookmaker_quotes(
        home,
        quote("bet365", MarketType.ASIAN_HANDICAP, "AWAY", Decimal("-1")),
        tolerance_seconds=5,
    ).pair_valid
    assert not pair_bookmaker_quotes(
        home,
        quote("pinnacle", MarketType.ASIAN_HANDICAP, "AWAY", Decimal("-1.25")),
        tolerance_seconds=5,
    ).pair_valid
    late = OddsQuote(
        **{
            **away.__dict__,
            "captured_at": NOW + timedelta(seconds=30),
        }
    )
    assert not pair_bookmaker_quotes(home, late, tolerance_seconds=5).pair_valid


def test_cross_market_ranking_and_gate4_grade_cap() -> None:
    matrix = {(1, 0): Decimal("0.55"), (1, 1): Decimal("0.25"), (0, 1): Decimal("0.20")}
    quotes = [
        quote("pinnacle", MarketType.ONE_X_TWO, "HOME", None),
        quote("pinnacle", MarketType.ASIAN_HANDICAP, "HOME", Decimal("-1")),
        quote("pinnacle", MarketType.TOTALS, "UNDER", Decimal("2.25")),
        quote("pinnacle", MarketType.BTTS, "NO", None),
    ]
    probabilities = {"HOME": Decimal("0.55"), "NO": Decimal("0.80")}
    ranked = MarketValueEngine(uncertainty_margin=Decimal("0.01")).evaluate(
        score_matrix=matrix,
        independent_probabilities=probabilities,
        quotes=quotes,
        gate4_pending=True,
    )
    assert {candidate.market_type for candidate in ranked} == {
        MarketType.ONE_X_TWO,
        MarketType.ASIAN_HANDICAP,
        MarketType.TOTALS,
        MarketType.BTTS,
    }
    assert all(candidate.published_grade not in {"A", "B"} for candidate in ranked)
    assert ranked[0].risk_adjusted_ev is not None
