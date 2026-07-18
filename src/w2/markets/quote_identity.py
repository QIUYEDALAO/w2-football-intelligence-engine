from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any

QUOTE_IDENTITY_SCHEMA_VERSION = "w2.quote_identity.v1"

_REQUIRED_FIELDS = (
    "observation_id",
    "fixture_id",
    "provider",
    "bookmaker_id",
    "bookmaker_name",
    "canonical_market",
    "selection",
    "line",
    "decimal_odds",
    "captured_at",
    "raw_payload_sha256",
    "source_revision",
)


def project_quote_identity(
    *,
    market: str,
    selected_line: Any,
    authoritative_rows: Mapping[str, Mapping[str, Any]] | None,
) -> dict[str, Any]:
    sides = _side_names(market)
    blockers: list[str] = []
    rows = dict(authoritative_rows or {})
    if sides is None:
        blockers.append("UNSUPPORTED_MARKET")
        return _payload(
            market=market,
            selected_line=selected_line,
            status="INCOMPLETE",
            blockers=blockers,
            quotes={},
        )

    quotes: dict[str, dict[str, Any]] = {}
    for side in sides:
        raw = rows.get(side.lower()) or rows.get(side)
        if not isinstance(raw, Mapping):
            blockers.append(f"MISSING_{side}_AUTHORITATIVE_QUOTE")
            continue
        quote = {field: raw.get(field) for field in _REQUIRED_FIELDS}
        quote["side"] = side
        quotes[side.lower()] = quote
        for field in _REQUIRED_FIELDS:
            if quote.get(field) in {None, ""}:
                blockers.append(f"{side}_MISSING_{field.upper()}")

    if len(quotes) != 2:
        return _payload(
            market=market,
            selected_line=selected_line,
            status="INCOMPLETE",
            blockers=blockers,
            quotes=quotes,
        )
    if blockers:
        return _payload(
            market=market,
            selected_line=selected_line,
            status="INCOMPLETE",
            blockers=blockers,
            quotes=quotes,
        )

    first, second = (quotes[side.lower()] for side in sides)
    _require_equal(first, second, "fixture_id", "FIXTURE_MISMATCH", blockers)
    _require_equal(first, second, "provider", "PROVIDER_MISMATCH", blockers)
    _require_equal(first, second, "bookmaker_id", "BOOKMAKER_MISMATCH", blockers)
    _require_equal(first, second, "canonical_market", "MARKET_MISMATCH", blockers)
    _require_equal(first, second, "captured_at", "CAPTURE_TIME_MISMATCH", blockers)
    if str(first["canonical_market"]) != market or str(second["canonical_market"]) != market:
        blockers.append("SELECTED_MARKET_MISMATCH")
    if str(first["observation_id"]) == str(second["observation_id"]):
        blockers.append("DUPLICATE_OBSERVATION_ID")
    if _normalized_side(market, first.get("selection")) != sides[0]:
        blockers.append(f"INVALID_{sides[0]}_SELECTION")
    if _normalized_side(market, second.get("selection")) != sides[1]:
        blockers.append(f"INVALID_{sides[1]}_SELECTION")
    if not _lines_match(market, selected_line, first.get("line"), second.get("line")):
        blockers.append("LINE_MISMATCH")

    return _payload(
        market=market,
        selected_line=selected_line,
        status="CONFLICT" if blockers else "COMPLETE",
        blockers=blockers,
        quotes=quotes,
    )


def unavailable_quote_identity(*, market: str, blocker: str) -> dict[str, Any]:
    return _payload(
        market=market,
        selected_line=None,
        status="INCOMPLETE",
        blockers=[blocker],
        quotes={},
    )


def _payload(
    *,
    market: str,
    selected_line: Any,
    status: str,
    blockers: list[str],
    quotes: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    ordered_blockers = sorted(set(blockers))
    quote_payload = {key: dict(value) for key, value in sorted(quotes.items())}
    observation_ids = {
        key: value.get("observation_id")
        for key, value in quote_payload.items()
        if value.get("observation_id") not in {None, ""}
    }
    complete_quotes = list(quote_payload.values())
    return {
        "schema_version": QUOTE_IDENTITY_SCHEMA_VERSION,
        "market": market,
        "selected_line": None if selected_line is None else str(selected_line),
        "identity_status": status,
        "blockers": ordered_blockers,
        "observation_ids": observation_ids,
        "provider": _common_value(complete_quotes, "provider"),
        "bookmaker_id": _common_value(complete_quotes, "bookmaker_id"),
        "captured_at": _common_value(complete_quotes, "captured_at"),
        "quotes": quote_payload,
    }


def _common_value(rows: Sequence[Mapping[str, Any]], field: str) -> Any:
    values = {row.get(field) for row in rows if row.get(field) not in {None, ""}}
    return next(iter(values)) if len(values) == 1 else None


def _require_equal(
    first: Mapping[str, Any],
    second: Mapping[str, Any],
    field: str,
    blocker: str,
    blockers: list[str],
) -> None:
    if str(first.get(field)) != str(second.get(field)):
        blockers.append(blocker)


def _side_names(market: str) -> tuple[str, str] | None:
    if market == "ASIAN_HANDICAP":
        return "HOME", "AWAY"
    if market == "TOTALS":
        return "OVER", "UNDER"
    return None


def _normalized_side(market: str, value: Any) -> str:
    text = str(value or "").upper().replace(" ", "_")
    if market == "ASIAN_HANDICAP":
        if text == "HOME" or text.startswith("HOME_"):
            return "HOME"
        if text == "AWAY" or text.startswith("AWAY_"):
            return "AWAY"
    if market == "TOTALS":
        if text == "OVER" or text.startswith("OVER_"):
            return "OVER"
        if text == "UNDER" or text.startswith("UNDER_"):
            return "UNDER"
    return text


def _lines_match(market: str, selected: Any, first: Any, second: Any) -> bool:
    selected_line = _decimal(selected)
    first_line = _decimal(first)
    second_line = _decimal(second)
    if selected_line is None or first_line is None or second_line is None:
        return False
    if market == "ASIAN_HANDICAP":
        return abs(first_line) == abs(selected_line) and first_line == -second_line
    return first_line == selected_line and second_line == selected_line


def _decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
