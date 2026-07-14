from __future__ import annotations

import pytest

from w2.models.market_quote import AH_LINE_SEMANTICS, MarketQuote, verify_market_quote


def _ah_quote(*, selection: str = "AWAY_AH") -> MarketQuote:
    return MarketQuote.create(
        fixture_id="fixture-1",
        market="ASIAN_HANDICAP",
        selection=selection,
        odds={
            "home_line": -0.75,
            "away_line": 0.75,
            "home_price": 1.94,
            "away_price": 1.92,
            "source": "market_timeline",
        },
        captured_at="2026-07-14T00:00:00Z",
    )


def test_away_quote_separates_home_centric_divergence_from_selection_line() -> None:
    quote = _ah_quote()

    assert quote.quote_id == f"mq_{quote.quote_hash}"
    assert quote.home_centric_market_line == -0.75
    assert quote.selection_line == 0.75
    assert quote.selection_price == 1.92
    assert quote.line_semantics == AH_LINE_SEMANTICS
    assert _ah_quote().quote_id == quote.quote_id
    assert verify_market_quote(quote.as_dict())

    tampered = quote.as_dict()
    tampered["selection_line"] = 1.0
    assert verify_market_quote(tampered) is False


@pytest.mark.parametrize(
    ("odds", "error"),
    [
        (
            {"home_line": -0.75, "away_line": 0.5, "home_price": 1.9, "away_price": 1.9},
            "LINES_NOT_OPPOSITES",
        ),
        (
            {"home_line": -0.3, "away_line": 0.3, "home_price": 1.9, "away_price": 1.9},
            "LINE_NOT_QUARTER_INCREMENT",
        ),
        (
            {"home_line": -0.75, "away_line": 0.75, "home_price": 1.0, "away_price": 1.9},
            "PRICE_MUST_EXCEED_ONE",
        ),
    ],
)
def test_market_quote_rejects_invalid_ah_contract(
    odds: dict[str, float], error: str
) -> None:
    with pytest.raises(ValueError, match=error):
        MarketQuote.create(
            fixture_id="fixture-1",
            market="ASIAN_HANDICAP",
            selection="HOME_AH",
            odds=odds,
            captured_at="2026-07-14T00:00:00Z",
        )


def test_market_quote_requires_captured_at() -> None:
    with pytest.raises(ValueError, match="REQUIRES_CAPTURED_AT"):
        MarketQuote.create(
            fixture_id="fixture-1",
            market="TOTALS",
            selection="OVER",
            odds={"line": 2.75, "over_price": 1.92},
            captured_at="",
        )
