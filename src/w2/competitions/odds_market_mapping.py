from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

NormalizedMarketType = Literal["AH", "OU", "OTHER"]


AH_MARKET_NAMES = frozenset(
    {
        "asian handicap",
        "handicap result",
        "asian handicap first half",
    }
)
OU_MARKET_NAMES = frozenset(
    {
        "goals over/under",
        "over/under",
        "total goals",
        "match goals",
        "totals",
    }
)
LINE_RE = re.compile(r"(?<!\d)[+-]?\d+(?:\.\d+)?(?!\d)")


@dataclass(frozen=True, kw_only=True)
class NormalizedOddsMarket:
    raw_market_name: str
    normalized_market_type: NormalizedMarketType
    bookmaker: str
    has_line: bool
    line_value: str


def normalize_market_name(name: Any) -> NormalizedMarketType:
    normalized = _norm(name)
    if normalized in AH_MARKET_NAMES or (
        "handicap" in normalized and "asian" in normalized
    ):
        return "AH"
    if normalized in OU_MARKET_NAMES or "over/under" in normalized:
        return "OU"
    return "OTHER"


def normalize_odds_markets(rows: Sequence[Mapping[str, Any]]) -> list[NormalizedOddsMarket]:
    markets: list[NormalizedOddsMarket] = []
    for row in rows:
        row_bookmakers = row.get("bookmakers")
        if isinstance(row_bookmakers, Sequence) and not isinstance(row_bookmakers, (str, bytes)):
            markets.extend(_nested_markets(row_bookmakers))
            continue
        market_name = _text(row.get("market") or row.get("market_name"))
        line = _extract_line(row)
        markets.append(
            NormalizedOddsMarket(
                raw_market_name=market_name,
                normalized_market_type=normalize_market_name(market_name),
                bookmaker=_text(row.get("bookmaker") or row.get("bookmaker_id")),
                has_line=bool(line),
                line_value=line,
            )
        )
    return markets


def bookmaker_observed_evidence(
    rows: Sequence[Mapping[str, Any]],
    *,
    lowercase_market_names: bool = False,
) -> dict[str, Any]:
    markets = normalize_odds_markets(rows)
    market_names = {
        item.raw_market_name.lower() if lowercase_market_names else item.raw_market_name
        for item in markets
        if item.raw_market_name
    }
    bookmakers = {item.bookmaker for item in markets if item.bookmaker}
    return {
        "observed_bookmaker_count": len(bookmakers),
        "observed_ah_ou_market_names": sorted(market_names),
        "observed_has_ah": any(item.normalized_market_type == "AH" for item in markets),
        "observed_has_ou": any(item.normalized_market_type == "OU" for item in markets),
        "observed_has_line": any(item.has_line for item in markets),
    }


def _nested_markets(bookmakers: Sequence[Any]) -> list[NormalizedOddsMarket]:
    markets: list[NormalizedOddsMarket] = []
    for bookmaker in bookmakers:
        if not isinstance(bookmaker, Mapping):
            continue
        bookmaker_name = _text(bookmaker.get("name") or bookmaker.get("id"))
        bets = bookmaker.get("bets")
        if not isinstance(bets, Sequence) or isinstance(bets, (str, bytes)):
            continue
        for bet in bets:
            if not isinstance(bet, Mapping):
                continue
            market_name = _text(bet.get("name"))
            values = bet.get("values")
            line = _extract_line(bet)
            if not line and isinstance(values, Sequence) and not isinstance(values, (str, bytes)):
                for value in values:
                    if isinstance(value, Mapping):
                        line = _extract_line(value)
                    else:
                        line = _line_from_text(value)
                    if line:
                        break
            markets.append(
                NormalizedOddsMarket(
                    raw_market_name=market_name,
                    normalized_market_type=normalize_market_name(market_name),
                    bookmaker=bookmaker_name,
                    has_line=bool(line),
                    line_value=line,
                )
            )
    return markets


def _extract_line(row: Mapping[str, Any]) -> str:
    for key in ("line", "handicap", "total"):
        value = _text(row.get(key))
        if value:
            return value
    return _line_from_text(row.get("value") or row.get("label") or row.get("name"))


def _line_from_text(value: Any) -> str:
    text = _text(value)
    if not text:
        return ""
    match = LINE_RE.search(text)
    return match.group(0) if match else ""


def _norm(value: Any) -> str:
    return _text(value).strip().lower()


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
