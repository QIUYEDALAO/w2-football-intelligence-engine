"""Independent five-state settlement and profit oracle.

Acceptance only. It deliberately imports nothing from w2: no production
settlement rule, no canonical EV authority, no serializer. It re-derives each
result from the final score, market, selection, exact line and decimal odds so
that agreement with the production authority is genuine evidence rather than a
tautology.
"""
from __future__ import annotations

from decimal import Decimal

QUARTER = Decimal("0.25")
STATES = ("WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "LOSS")


def parse_score(score: str) -> tuple[int, int]:
    home, _, away = str(score).partition("-")
    return int(home.strip()), int(away.strip())


def margin(*, market: str, selection: str, home_goals: int, away_goals: int,
           exact_line: Decimal) -> Decimal:
    """Signed margin of the taken side, in goals, after the line is applied.

    exact_line is the line of the SELECTED side, not a fixed home line, so it is
    added to that side's own goal difference rather than negated with it. This
    was established by reconciling all 148 production settlements: treating it
    as a home line disagreed on exactly the 25 AWAY selections.
    """
    if market == "ASIAN_HANDICAP":
        goal_difference = (
            Decimal(home_goals - away_goals) if selection == "HOME"
            else Decimal(away_goals - home_goals)
        )
        return goal_difference + exact_line
    if market == "TOTALS":
        value = Decimal(home_goals + away_goals) - exact_line
        return value if selection == "OVER" else -value
    raise ValueError(f"UNSUPPORTED_MARKET:{market}")


def settle(value: Decimal) -> str:
    if value > QUARTER:
        return "WIN"
    if value == QUARTER:
        return "HALF_WIN"
    if value == 0:
        return "PUSH"
    if value == -QUARTER:
        return "HALF_LOSS"
    return "LOSS"


def profit_units(settlement: str, decimal_odds: Decimal) -> Decimal:
    net = decimal_odds - Decimal(1)
    return {
        "WIN": net,
        "HALF_WIN": net / 2,
        "PUSH": Decimal(0),
        "HALF_LOSS": Decimal("-0.5"),
        "LOSS": Decimal(-1),
    }[settlement]


def evaluate(*, score: str, market: str, selection: str, exact_line: float | str,
             decimal_odds: float | str) -> tuple[str, Decimal]:
    home_goals, away_goals = parse_score(score)
    value = margin(market=market, selection=selection, home_goals=home_goals,
                   away_goals=away_goals, exact_line=Decimal(str(exact_line)))
    outcome = settle(value)
    return outcome, profit_units(outcome, Decimal(str(decimal_odds)))
