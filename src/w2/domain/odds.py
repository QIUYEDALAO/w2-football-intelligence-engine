from __future__ import annotations

from decimal import Decimal

from w2.domain.enums import MarketType, SettlementOutcome

QuarterParts = tuple[Decimal, Decimal]


def split_quarter_line(line: Decimal) -> QuarterParts:
    scaled = line * Decimal("4")
    if scaled != scaled.to_integral_value():
        raise ValueError("line must be a quarter-line increment")
    whole_half_steps = (line * Decimal("2")).to_integral_value(rounding="ROUND_FLOOR")
    lower = whole_half_steps / Decimal("2")
    upper = lower + Decimal("0.5")
    if line == lower:
        return (line, line)
    if line == upper:
        return (line, line)
    return (lower, upper)


def canonicalize_selection(market: MarketType, selection: str) -> str:
    selection_key = selection.strip().upper().replace(" ", "_").replace("-", "_")
    aliases = {
        MarketType.ONE_X_TWO: {
            "HOME": "HOME",
            "1": "HOME",
            "DRAW": "DRAW",
            "X": "DRAW",
            "AWAY": "AWAY",
            "2": "AWAY",
        },
        MarketType.ASIAN_HANDICAP: {"HOME": "HOME", "AWAY": "AWAY"},
        MarketType.TOTALS: {"OVER": "OVER", "O": "OVER", "UNDER": "UNDER", "U": "UNDER"},
        MarketType.BTTS: {"YES": "YES", "Y": "YES", "NO": "NO", "N": "NO"},
    }
    try:
        return aliases[market][selection_key]
    except KeyError as exc:
        raise ValueError(f"unsupported selection {selection!r} for {market}") from exc


def _single_ah(
    home_goals: int,
    away_goals: int,
    selection: str,
    line: Decimal,
) -> SettlementOutcome:
    goal_diff = Decimal(home_goals - away_goals)
    adjusted = goal_diff + line if selection == "HOME" else -goal_diff + line
    if adjusted > 0:
        return SettlementOutcome.WIN
    if adjusted == 0:
        return SettlementOutcome.PUSH
    return SettlementOutcome.LOSS


def _single_total(total_goals: int, selection: str, line: Decimal) -> SettlementOutcome:
    total = Decimal(total_goals)
    if selection == "OVER":
        adjusted = total - line
    else:
        adjusted = line - total
    if adjusted > 0:
        return SettlementOutcome.WIN
    if adjusted == 0:
        return SettlementOutcome.PUSH
    return SettlementOutcome.LOSS


def _combine(parts: tuple[SettlementOutcome, SettlementOutcome]) -> SettlementOutcome:
    if parts[0] == parts[1]:
        return parts[0]
    if set(parts) == {SettlementOutcome.WIN, SettlementOutcome.PUSH}:
        return SettlementOutcome.HALF_WIN
    if set(parts) == {SettlementOutcome.LOSS, SettlementOutcome.PUSH}:
        return SettlementOutcome.HALF_LOSS
    raise ValueError(f"unsupported split settlement combination: {parts}")


def settle_asian_handicap(
    home_goals: int,
    away_goals: int,
    selection: str,
    line: Decimal,
) -> SettlementOutcome:
    canonical = canonicalize_selection(MarketType.ASIAN_HANDICAP, selection)
    first, second = split_quarter_line(line)
    return _combine(
        (
            _single_ah(home_goals, away_goals, canonical, first),
            _single_ah(home_goals, away_goals, canonical, second),
        )
    )


def settle_total_goals(total_goals: int, selection: str, line: Decimal) -> SettlementOutcome:
    canonical = canonicalize_selection(MarketType.TOTALS, selection)
    first, second = split_quarter_line(line)
    return _combine(
        (
            _single_total(total_goals, canonical, first),
            _single_total(total_goals, canonical, second),
        )
    )
