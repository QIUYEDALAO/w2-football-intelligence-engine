"""v3 专用同源双侧盘口选择器（AH/OU 终验 S2）。

与旧的 ``select_canonical_ah_mainline`` / ``select_canonical_totals_mainline``
（多 bookmaker 投票选主线）不同，v3 决策只认 Pinnacle，并要求两侧价格来自
*同一次原始捕获*，以此保证 AH 方向与 OU 价值判断建立在同一时点的真实盘口上。

Selection contract (all fail closed):
1. canonical fixture + Pinnacle (bookmaker_id == "4") + not live/suspended.
2. ``captured_at <= decision_at``, and only the *latest* capture before the
   decision instant is considered.
3. Both complementary sides must come from the exact same
   ``(fixture_id, capture_id, captured_at, line)``.
4. Every field of ``side_prices`` is re-derived from the two raw rows and must
   match the raw ``decimal_odds``/``line``/``selection``/``market``/``fixture``/
   raw-hash -- any disagreement is a refusal, never a silent pick.
5. ``source_capture_sha256`` is the canonical-hash-domain digest of the raw
   capture payload (never a bare hex64, never empty). If the resolver cannot
   produce the raw payload the quote is refused.
"""
from __future__ import annotations

import math
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from w2.domain.canonical_serialization import HashDomain, canonical_sha256

AH_MARKET = "ASIAN_HANDICAP"
OU_MARKET = "TOTALS"
PINNACLE_BOOKMAKER_ID = "4"


def _parse_utc(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else None
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else None
    return None


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _side(row: dict[str, Any]) -> str:
    return str(row.get("selection") or row.get("canonical_selection") or "").upper()


def _complementary_sides(market: str) -> tuple[str, str]:
    return ("HOME", "AWAY") if market == AH_MARKET else ("OVER", "UNDER")


def _source_capture_sha256(
    capture_id: str,
    raw_payloads: dict[str, dict[str, Any]] | None,
) -> str | None:
    """Canonical-hash-domain digest of the raw capture payload.

    The digest is ``canonical_sha256(raw_payload, domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD)``
    -- the same authority used elsewhere for raw payloads. A missing or empty raw
    payload yields ``None`` so the caller refuses the quote instead of faking a
    bare hex64.
    """
    if not raw_payloads:
        return None
    raw = raw_payloads.get(capture_id)
    if not isinstance(raw, dict) or not raw:
        return None
    return canonical_sha256(raw, domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD)


def _select_one_market(
    observations: list[dict[str, Any]],
    *,
    fixture_id: str,
    decision_at: datetime,
    market: str,
    raw_payloads: dict[str, dict[str, Any]] | None,
) -> dict[str, Any]:
    side_a, side_b = _complementary_sides(market)

    scoped: list[tuple[datetime, dict[str, Any]]] = []
    for row in observations:
        if str(row.get("fixture_id") or "") != fixture_id:
            continue
        if str(row.get("bookmaker_id") or "") != PINNACLE_BOOKMAKER_ID:
            continue
        if row.get("suspended") or row.get("live"):
            continue
        if str(row.get("canonical_market") or row.get("market") or "").upper() != market:
            continue
        captured = _parse_utc(row.get("captured_at") or row.get("captured_at_utc"))
        if captured is None or captured > decision_at:
            continue
        scoped.append((captured, row))
    if not scoped:
        return {"status": f"{market}_QUOTE_UNAVAILABLE", "quote": None}

    latest = max(item[0] for item in scoped)
    latest_rows = [row for captured, row in scoped if captured == latest]
    if not latest_rows:
        return {"status": f"{market}_QUOTE_UNAVAILABLE", "quote": None}

    # Both sides must come from the exact same (capture_id, captured_at, line).
    capture_ids = {str(row.get("capture_id") or "") for row in latest_rows}
    if len(capture_ids) != 1 or "" in capture_ids:
        return {"status": f"{market}_QUOTE_NOT_SAME_CAPTURE", "quote": None}
    capture_id = next(iter(capture_ids))

    line_values = {_decimal(row.get("line")) for row in latest_rows}
    line_values.discard(None)
    if len(line_values) != 1:
        return {"status": f"{market}_QUOTE_LINE_CONFLICT", "quote": None}
    line = next(iter(line_values))

    by_side: dict[str, dict[str, Any]] = {}
    for row in latest_rows:
        side = _side(row)
        if side not in {side_a, side_b}:
            return {"status": f"{market}_QUOTE_INVALID_SIDE", "quote": None}
        price = _float(row.get("decimal_odds") or row.get("executable_odds"))
        if price is None or price <= 1.0:
            return {"status": f"{market}_QUOTE_PRICE_INVALID", "quote": None}
        if side in by_side:
            return {"status": f"{market}_QUOTE_DUPLICATE_SIDE", "quote": None}
        by_side[side] = row
    if set(by_side) != {side_a, side_b}:
        return {"status": f"{market}_QUOTE_SIDE_INCOMPLETE", "quote": None}

    row_a = dict(by_side[side_a])
    row_b = dict(by_side[side_b])
    price_a = _float(row_a.get("decimal_odds") or row_a.get("executable_odds"))
    price_b = _float(row_b.get("decimal_odds") or row_b.get("executable_odds"))
    assert price_a is not None and price_b is not None

    source_capture_sha256 = _source_capture_sha256(capture_id, raw_payloads)
    if source_capture_sha256 is None:
        return {"status": f"{market}_SOURCE_CAPTURE_HASH_MISSING", "quote": None}

    # Field-level verification: the emitted side_prices must reproduce exactly
    # the two raw rows, including market/fixture/line/selection/raw hash.
    raw_hashes = {str(row.get("raw_payload_sha256") or "") for row in (row_a, row_b)}
    if "" in raw_hashes:
        return {"status": f"{market}_QUOTE_RAW_HASH_MISSING", "quote": None}
    for row in (row_a, row_b):
        if str(row.get("fixture_id") or "") != fixture_id:
            return {"status": f"{market}_QUOTE_FIXTURE_MISMATCH", "quote": None}
        if str(row.get("canonical_market") or row.get("market") or "").upper() != market:
            return {"status": f"{market}_QUOTE_MARKET_MISMATCH", "quote": None}

    return {
        "status": "READY",
        "quote": {
            "market": market,
            "fixture_id": fixture_id,
            "line": line,
            "capture_id": capture_id,
            "captured_at": latest,
            "side_prices": {side_a.lower(): price_a, side_b.lower(): price_b},
            "side_rows": {side_a.lower(): row_a, side_b.lower(): row_b},
            "source_capture_sha256": source_capture_sha256,
            "raw_payload_sha256s": sorted(raw_hashes),
        },
    }


def select_v3_ah_ou_quotes(
    observations: list[dict[str, Any]],
    *,
    fixture_id: str,
    decision_at: datetime,
    raw_payloads: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return ``{"status", "ah", "ou"}`` for the v3 same-capture two-sided quotes.

    ``status == "READY"`` only when both markets produced a same-capture quote.
    ``ah``/``ou`` are the per-market results (``{"status", "quote"}``).
    """
    ah = _select_one_market(
        observations,
        fixture_id=fixture_id,
        decision_at=decision_at,
        market=AH_MARKET,
        raw_payloads=raw_payloads,
    )
    ou = _select_one_market(
        observations,
        fixture_id=fixture_id,
        decision_at=decision_at,
        market=OU_MARKET,
        raw_payloads=raw_payloads,
    )
    ready = ah["status"] == "READY" and ou["status"] == "READY"
    return {
        "status": "READY" if ready else "QUOTE_SELECTION_FAILED",
        "ah": ah,
        "ou": ou,
    }
