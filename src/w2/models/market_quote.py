from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

SCHEMA_VERSION = "w2.market_quote.v1"
AH_LINE_SEMANTICS = "HOME_CENTRIC_DIVERGENCE_SELECTION_LINE_SETTLEMENT"
TOTALS_LINE_SEMANTICS = "TOTAL_GOALS_SELECTION_LINE"
_HASH_FIELDS = (
    "schema_version",
    "fixture_id",
    "market",
    "bookmaker",
    "source",
    "home_centric_market_line",
    "home_line",
    "away_line",
    "home_price",
    "away_price",
    "selection_line",
    "selection_price",
    "captured_at",
    "source_hash",
    "line_semantics",
)


@dataclass(frozen=True, kw_only=True)
class MarketQuote:
    schema_version: str
    quote_id: str
    fixture_id: str
    market: str
    bookmaker: str
    source: str
    home_centric_market_line: float
    home_line: float | None
    away_line: float | None
    home_price: float | None
    away_price: float | None
    selection_line: float
    selection_price: float
    captured_at: str
    source_hash: str
    line_semantics: str
    quote_hash: str

    @classmethod
    def create(
        cls,
        *,
        fixture_id: str,
        market: str,
        selection: str,
        odds: Mapping[str, Any],
        captured_at: str,
        bookmaker: str | None = None,
        source: str | None = None,
        source_hash: str | None = None,
    ) -> MarketQuote:
        captured = _captured_at(captured_at)
        market_name = str(market).strip().upper()
        home_line: float | None
        away_line: float | None
        home_price: float | None
        away_price: float | None
        if market_name == "ASIAN_HANDICAP":
            home_line = _required_number(odds.get("home_line"), "home_line")
            away_line = _required_number(odds.get("away_line"), "away_line")
            home_price = _required_price(odds.get("home_price"), "home_price")
            away_price = _required_price(odds.get("away_price"), "away_price")
            if abs(home_line + away_line) > 1e-9:
                raise ValueError("MARKET_QUOTE_AH_LINES_NOT_OPPOSITES")
            if selection == "HOME_AH":
                selection_line, selection_price = home_line, home_price
            elif selection == "AWAY_AH":
                selection_line, selection_price = away_line, away_price
            else:
                raise ValueError("MARKET_QUOTE_UNSUPPORTED_SELECTION")
            home_centric = home_line
            semantics = AH_LINE_SEMANTICS
        elif market_name == "TOTALS":
            line = _required_number(odds.get("line"), "line")
            if selection == "OVER":
                selection_price = _required_price(odds.get("over_price"), "over_price")
            elif selection == "UNDER":
                selection_price = _required_price(odds.get("under_price"), "under_price")
            else:
                raise ValueError("MARKET_QUOTE_UNSUPPORTED_SELECTION")
            home_centric = selection_line = line
            home_line = away_line = home_price = away_price = None
            semantics = TOTALS_LINE_SEMANTICS
        else:
            raise ValueError("MARKET_QUOTE_UNSUPPORTED_MARKET")
        _require_quarter_line(selection_line)
        source_name = str(source or odds.get("source") or "read_model")
        bookmaker_name = str(
            bookmaker or odds.get("bookmaker") or odds.get("bookmaker_name") or "consensus"
        )
        resolved_source_hash = str(source_hash or odds.get("source_hash") or _hash(odds))
        payload = {
            "schema_version": SCHEMA_VERSION,
            "fixture_id": str(fixture_id),
            "market": market_name,
            "bookmaker": bookmaker_name,
            "source": source_name,
            "home_centric_market_line": home_centric,
            "home_line": home_line,
            "away_line": away_line,
            "home_price": home_price,
            "away_price": away_price,
            "selection_line": selection_line,
            "selection_price": selection_price,
            "captured_at": captured,
            "source_hash": resolved_source_hash,
            "line_semantics": semantics,
        }
        quote_hash = _hash(payload)
        return cls(
            schema_version=SCHEMA_VERSION,
            quote_id=f"mq_{quote_hash}",
            fixture_id=str(fixture_id),
            market=market_name,
            bookmaker=bookmaker_name,
            source=source_name,
            home_centric_market_line=home_centric,
            home_line=home_line,
            away_line=away_line,
            home_price=home_price,
            away_price=away_price,
            selection_line=selection_line,
            selection_price=selection_price,
            captured_at=captured,
            source_hash=resolved_source_hash,
            line_semantics=semantics,
            quote_hash=quote_hash,
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def verify_market_quote(quote: Mapping[str, Any]) -> bool:
    payload = {field: quote.get(field) for field in _HASH_FIELDS}
    quote_hash = str(quote.get("quote_hash") or "")
    return (
        quote.get("schema_version") == SCHEMA_VERSION
        and bool(quote_hash)
        and quote.get("quote_id") == f"mq_{quote_hash}"
        and _hash(payload) == quote_hash
    )


def _captured_at(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("MARKET_QUOTE_REQUIRES_CAPTURED_AT")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("MARKET_QUOTE_INVALID_CAPTURED_AT") from exc
    if parsed.tzinfo is None:
        raise ValueError("MARKET_QUOTE_INVALID_CAPTURED_AT")
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _required_number(value: Any, field: str) -> float:
    try:
        number = float(Decimal(str(value)))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"MARKET_QUOTE_REQUIRES_{field.upper()}") from exc
    return number


def _required_price(value: Any, field: str) -> float:
    price = _required_number(value, field)
    if price <= 1:
        raise ValueError("MARKET_QUOTE_PRICE_MUST_EXCEED_ONE")
    return price


def _require_quarter_line(value: float) -> None:
    if abs(value * 4 - round(value * 4)) > 1e-9:
        raise ValueError("MARKET_QUOTE_LINE_NOT_QUARTER_INCREMENT")


def _hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
