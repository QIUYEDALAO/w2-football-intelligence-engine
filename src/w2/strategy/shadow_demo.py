from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from w2.domain.enums import MarketType
from w2.markets.value_engine import OddsFormat, OddsQuote
from w2.strategy.shadow import StrategyInput


def demo_quote(
    *,
    bookmaker: str,
    market: MarketType,
    selection: str,
    line: Decimal | None,
    odds: Decimal,
    now: datetime,
) -> OddsQuote:
    return OddsQuote(
        bookmaker_id=bookmaker.lower().replace(" ", "_"),
        bookmaker_name=bookmaker,
        market_type=market,
        selection=selection,
        line=line,
        raw_odds=odds,
        raw_odds_format=OddsFormat.DECIMAL,
        decimal_odds=odds,
        captured_at=now,
        provider_updated_at=now,
        suspended=False,
        live=False,
        provenance="stage9_runtime_demo",
    )


def demo_inputs() -> list[StrategyInput]:
    now = datetime(2026, 6, 22, 12, 0, tzinfo=UTC)
    score_matrix = {
        (0, 0): Decimal("0.08"),
        (1, 0): Decimal("0.19"),
        (2, 0): Decimal("0.18"),
        (2, 1): Decimal("0.17"),
        (1, 1): Decimal("0.14"),
        (0, 1): Decimal("0.08"),
        (1, 2): Decimal("0.06"),
        (3, 1): Decimal("0.06"),
        (3, 0): Decimal("0.04"),
    }
    return [
        StrategyInput(
            fixture_id="stage9a-france-iraq-demo",
            phase="RETROSPECTIVE_REPLAY",
            kickoff_utc=datetime(2026, 6, 22, 21, 0, tzinfo=UTC),
            as_of_time=now,
            score_matrix=score_matrix,
            independent_probabilities={
                "HOME": Decimal("0.62"),
                "DRAW": Decimal("0.23"),
                "AWAY": Decimal("0.15"),
                "YES": Decimal("0.49"),
                "NO": Decimal("0.51"),
            },
            quotes=[
                demo_quote(
                    bookmaker="Pinnacle",
                    market=MarketType.ONE_X_TWO,
                    selection="HOME",
                    line=None,
                    odds=Decimal("1.80"),
                    now=now,
                ),
                demo_quote(
                    bookmaker="Pinnacle",
                    market=MarketType.ASIAN_HANDICAP,
                    selection="AWAY",
                    line=Decimal("+2.75"),
                    odds=Decimal("2.02"),
                    now=now,
                ),
                demo_quote(
                    bookmaker="SBO",
                    market=MarketType.TOTALS,
                    selection="OVER",
                    line=Decimal("4"),
                    odds=Decimal("2.38"),
                    now=now,
                ),
                demo_quote(
                    bookmaker="Bet365",
                    market=MarketType.BTTS,
                    selection="NO",
                    line=None,
                    odds=Decimal("1.95"),
                    now=now,
                ),
            ],
            most_likely_outcome="HOME_WIN",
            evidence_refs=("offline_fixture_snapshot",),
        )
    ]
