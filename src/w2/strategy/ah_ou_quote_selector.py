"""v3 专用同源双侧盘口选择器（AH/OU 终验 S2）。

对齐回测「主流 bookmaker 主线」（``select_canonical_ah_mainline`` /
``select_canonical_totals_mainline``）——不再只认 Pinnacle：任一双侧来自同一
bookmaker 且同一时点（同 capture）的报价都可准入，避免「回测多 bookmaker 投票、
生产只认 Pinnacle」的报价源自相矛盾。

Selection contract (all fail closed):
1. canonical fixture + any bookmaker + not live/suspended.
2. ``captured_at <= decision_at``, and only the *latest* capture before the
   decision instant is considered.
3. Both complementary sides must come from the exact same
   ``(fixture_id, capture_id, captured_at, bookmaker_id, line)``.
4. Every field of ``side_prices`` is re-derived from the two raw rows and must
   match the raw ``decimal_odds``/``line``/``selection``/``market``/``fixture``/
   raw-hash -- any disagreement is a refusal, never a silent pick.
5. ``source_capture_sha256`` is the canonical-hash-domain digest of the raw
   capture payload (never a bare hex64, never empty). If the resolver cannot
   produce the raw payload the quote is refused.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from w2.domain.canonical_serialization import (
    HashDomain,
    SerializerVersion,
    canonical_sha256,
)
from w2.markets.devig import devig_balance_distance
from w2.matchday.intake_v2 import normalize_matchday_odds_payload

AH_MARKET = "ASIAN_HANDICAP"
OU_MARKET = "TOTALS"
# T3 报价新鲜度上界：决策点前「最新」报价不能太旧（Owner 拍板 24h），否则
# 7 天前的报价也会被当成当前可执行盘口进入决策。超阈值按 STALE_QUOTE SKIP。
QUOTE_MAX_AGE = timedelta(hours=24)


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
        parsed = value
    else:
        try:
            parsed = Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None
    # C: NaN/Inf are never a valid line; refuse rather than letting a non-finite
    # Decimal flow into comparisons and arithmetic.
    if not parsed.is_finite():
        return None
    return parsed


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


def _has_duplicate_line(rows: list[dict[str, Any]]) -> bool:
    """True when the same side carries two rows on the same line (a duplicate
    side that must be refused, never silently deduplicated)."""
    seen: set[str] = set()
    for row in rows:
        line = _decimal(row.get("line"))
        if line is None:
            continue
        key = str(line.normalize())
        if key in seen:
            return True
        seen.add(key)
    return False


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


def _decimal_text(value: Any) -> str:
    parsed = _decimal(value)
    return "" if parsed is None else str(parsed)


def _source_content_matches(
    rows: list[dict[str, Any]],
    raw_payload: dict[str, Any],
    *,
    capture_id: str,
) -> bool:
    """Verify the projection rows reproduce from the raw capture payload.

    This closes the source-content loop: the raw payload is re-normalized with the
    production intake parser and every projection row must match a normalized row
    on fixture/bookmaker/market/selection/line/price. A raw payload swapped for a
    different fixture (or tampered price/hash/line) therefore fails -- it is not
    enough that the raw payload merely exists.
    """
    first = rows[0]
    captured = _parse_utc(first.get("captured_at") or first.get("captured_at_utc"))
    ingested = _parse_utc(first.get("ingested_at")) or captured
    if captured is None or ingested is None:
        return False
    # V8/C: EVERY projection row's raw hash must equal the LEGACY_V1 canonical hash
    # of the raw payload (the authority intake uses) -- not just the first side.
    expected_hash = canonical_sha256(
        raw_payload,
        domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD,
        version=SerializerVersion.LEGACY_V1,
    )
    for row in rows:
        if str(row.get("raw_payload_sha256") or "") != expected_hash:
            return False
    try:
        normalized, _ = normalize_matchday_odds_payload(
            raw_payload,
            captured_at=captured,
            ingested_at=ingested,
            raw_payload_sha256=expected_hash,
            source_revision=str(first.get("source_revision") or ""),
            capture_id=capture_id,
            provider=str(first.get("provider") or "api_football"),
            competition_id=str(first.get("competition_id") or "UNKNOWN"),
        )
    except Exception:
        return False
    # Compare multisets in exactly the same fixture/bookmaker/capture/market scope.
    # Other fixtures and companies in a batch response are independent facts.
    from collections import Counter

    fixture = str(first.get("fixture_id") or "").removeprefix("api_football:")
    market = str(first.get("canonical_market") or first.get("market") or "").upper()
    def signature(row: dict[str, Any]) -> tuple[Any, ...]:
        return (
            str(row.get("fixture_id") or "").removeprefix("api_football:"),
            str(row.get("bookmaker_id") or ""),
            str(row.get("canonical_market") or row.get("market") or "").upper(),
            _side(row), _decimal(row.get("line")),
            _decimal(row.get("decimal_odds") or row.get("executable_odds")),
            _parse_utc(row.get("captured_at") or row.get("captured_at_utc")),
            str(row.get("capture_id") or ""), str(row.get("raw_payload_sha256") or ""),
        )
    scoped = [n for n in normalized
              if str(n.get("fixture_id") or "").removeprefix("api_football:") == fixture
              and str(n.get("canonical_market") or "").upper() == market
              and str(n.get("capture_id") or "") == capture_id]
    return Counter(map(signature, scoped)) == Counter(map(signature, rows))


def _pair_sort_key(
    pair: dict[str, Any], *, market: str
) -> tuple[float, float, float, float]:
    # C: frozen mainline ranking is |odds_side1−1.9|+|odds_side2−1.9| (the pair
    # closest to a 1.90/1.90 two-way book), NOT the devigged balance distance.
    primary = abs(pair["price_a"] - 1.90) + abs(pair["price_b"] - 1.90)
    line = abs(float(pair["line"]))
    # AH secondary: |line|; OU secondary: distance to 2.5. Both then fall back to
    # price gap and |line| for a deterministic tie-break.
    secondary = line if market == AH_MARKET else abs(float(pair["line"]) - 2.5)
    return (primary, secondary, float(pair["price_gap"]), line)


def _make_pair(
    *,
    side_a: str,
    side_b: str,
    line: Decimal,
    row_a: dict[str, Any],
    row_b: dict[str, Any],
) -> dict[str, Any] | None:
    price_a = _float(row_a.get("decimal_odds") or row_a.get("executable_odds"))
    price_b = _float(row_b.get("decimal_odds") or row_b.get("executable_odds"))
    if price_a is None or price_a <= 1.0 or price_b is None or price_b <= 1.0:
        return None
    return {
        "line": float(line),
        "decimal_line": line,
        "price_a": price_a,
        "price_b": price_b,
        "balance_distance": devig_balance_distance([price_a, price_b]),
        "price_gap": round(abs(price_a - price_b), 6),
        "mid_distance": round(abs(((price_a + price_b) / 2) - 1.90), 6),
        "row_a": dict(row_a),
        "row_b": dict(row_b),
    }


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
    saw_live_suspended = False
    saw_late = False
    for row in observations:
        if str(row.get("fixture_id") or "") != fixture_id:
            continue
        if str(row.get("canonical_market") or row.get("market") or "").upper() != market:
            continue
        if row.get("suspended") or row.get("live"):
            saw_live_suspended = True
            continue
        if str(row.get("canonical_market") or row.get("market") or "").upper() != market:
            continue
        captured = _parse_utc(row.get("captured_at") or row.get("captured_at_utc"))
        if captured is None or captured > decision_at:
            saw_late = True
            continue
        scoped.append((captured, row))
    if not scoped:
        # 包3(C): a targeted refusal reason, not a blanket QUOTE_UNAVAILABLE.
        if saw_late:
            return {"status": f"{market}_QUOTE_CAPTURED_AFTER_DECISION", "quote": None}
        if saw_live_suspended:
            return {"status": f"{market}_QUOTE_LIVE_OR_SUSPENDED", "quote": None}
        return {"status": f"{market}_QUOTE_UNAVAILABLE", "quote": None}

    latest = max(item[0] for item in scoped)
    # T3: 报价新鲜度上界——决策点前最新报价若早于 24h，按 STALE_QUOTE SKIP，
    # 不进入主线选择（修复「7 天前报价合法变推荐」）。
    if decision_at - latest > QUOTE_MAX_AGE:
        return {"status": f"{market}_STALE_QUOTE", "quote": None}
    latest_rows = [row for captured, row in scoped if captured == latest]
    if not latest_rows:
        return {"status": f"{market}_QUOTE_UNAVAILABLE", "quote": None}

    # Both sides must come from the exact same (capture_id, captured_at).
    capture_ids = {str(row.get("capture_id") or "") for row in latest_rows}
    if len(capture_ids) != 1 or "" in capture_ids:
        return {"status": f"{market}_QUOTE_NOT_SAME_CAPTURE", "quote": None}
    capture_id = next(iter(capture_ids))

    # 3. Pair exact two-sided lines within the same capture. AH pairs a home row
    #    with an away row whose provider line is the home line or its negative
    #    (the two legitimate API shapes); TOTALS pairs equal lines. The emitted
    #    line is always the home/over perspective. A capture may carry multiple
    #    legal lines; they are ranked below, never refused as DUPLICATE_SIDE.
    pairs: list[dict[str, Any]] = []
    if market == AH_MARKET:
        home_rows = [row for row in latest_rows if _side(row) == side_a]
        away_rows = [row for row in latest_rows if _side(row) == side_b]
        # C: a duplicate side on the same line (even same price) is a refusal.
        if _has_duplicate_line(home_rows) or _has_duplicate_line(away_rows):
            return {"status": f"{market}_QUOTE_DUPLICATE_SIDE", "quote": None}
        for home_row in home_rows:
            home_price = _float(home_row.get("decimal_odds") or home_row.get("executable_odds"))
            if home_price is None or home_price <= 1.0:
                return {"status": f"{market}_QUOTE_PRICE_INVALID", "quote": None}
            home_line = _decimal(home_row.get("line"))
            if home_line is None:
                return {"status": f"{market}_QUOTE_LINE_INVALID", "quote": None}
            home_bookmaker = str(home_row.get("bookmaker_id") or "")
            for away_row in away_rows:
                away_price = _float(away_row.get("decimal_odds") or away_row.get("executable_odds"))
                if away_price is None or away_price <= 1.0:
                    return {"status": f"{market}_QUOTE_PRICE_INVALID", "quote": None}
                away_line = _decimal(away_row.get("line"))
                if away_line is None:
                    return {"status": f"{market}_QUOTE_LINE_INVALID", "quote": None}
                # 对齐回测 per-bookmaker 双侧配对：两侧必须来自同一 bookmaker，
                # 且 bookmaker 非空（避免跨 bookmaker 报价漂移）。
                if not home_bookmaker or home_bookmaker != str(away_row.get("bookmaker_id") or ""):
                    continue
                if away_line not in {home_line, -home_line}:
                    continue
                pair = _make_pair(
                    side_a=side_a, side_b=side_b, line=home_line,
                    row_a=home_row, row_b=away_row,
                )
                if pair is not None:
                    pairs.append(pair)
    else:
        line_groups: dict[str, dict[str, dict[str, Any]]] = {}
        for row in latest_rows:
            side = _side(row)
            if side not in {side_a, side_b}:
                return {"status": f"{market}_QUOTE_INVALID_SIDE", "quote": None}
            price = _float(row.get("decimal_odds") or row.get("executable_odds"))
            if price is None or price <= 1.0:
                return {"status": f"{market}_QUOTE_PRICE_INVALID", "quote": None}
            line = _decimal(row.get("line"))
            if line is None:
                return {"status": f"{market}_QUOTE_LINE_INVALID", "quote": None}
            group = line_groups.setdefault(str(line.normalize()), {})
            if side in group:
                # C: a duplicate OVER/UNDER row on the same line (even same price)
                # must be refused, never silently deduplicated.
                return {"status": f"{market}_QUOTE_DUPLICATE_SIDE", "quote": None}
            group[side] = row
        for group in line_groups.values():
            if set(group) != {side_a, side_b}:
                continue
            # 对齐回测 per-bookmaker 双侧配对：两侧必须来自同一 bookmaker。
            if not str(group[side_a].get("bookmaker_id") or "") or str(
                group[side_a].get("bookmaker_id") or ""
            ) != str(group[side_b].get("bookmaker_id") or ""):
                continue
            line = _decimal(group[side_a].get("line"))
            if line is None:
                continue
            pair = _make_pair(
                side_a=side_a, side_b=side_b,
                line=line,
                row_a=group[side_a], row_b=group[side_b],
            )
            if pair is not None:
                pairs.append(pair)
    if not pairs:
        return {"status": f"{market}_QUOTE_SIDE_INCOMPLETE", "quote": None}
    # Frozen mainline: |odds−1.9| sum first (C), then market-specific secondary.
    pairs.sort(key=lambda pair: _pair_sort_key(pair, market=market))
    selected = pairs[0]
    row_a = selected["row_a"]
    row_b = selected["row_b"]
    price_a = selected["price_a"]
    price_b = selected["price_b"]
    line = selected["decimal_line"]

    # 4. Source-content closure: the raw payload must reproduce these exact rows.
    source_capture_sha256 = _source_capture_sha256(capture_id, raw_payloads)
    if source_capture_sha256 is None:
        return {"status": f"{market}_SOURCE_CAPTURE_HASH_MISSING", "quote": None}
    raw_hashes = {str(row.get("raw_payload_sha256") or "") for row in (row_a, row_b)}
    if "" in raw_hashes:
        return {"status": f"{market}_QUOTE_RAW_HASH_MISSING", "quote": None}
    for row in (row_a, row_b):
        if str(row.get("fixture_id") or "") != fixture_id:
            return {"status": f"{market}_QUOTE_FIXTURE_MISMATCH", "quote": None}
        if str(row.get("canonical_market") or row.get("market") or "").upper() != market:
            return {"status": f"{market}_QUOTE_MARKET_MISMATCH", "quote": None}
    if raw_payloads and capture_id in raw_payloads:
        # V8/C: prove the FULL projection set (every row of this capture for this
        # market) reproduces from the raw payload one-to-one -- not just the two
        # selected sides (which would let a raw-only duplicate survive).
        if not _source_content_matches(
            latest_rows, raw_payloads[capture_id], capture_id=capture_id
        ):
            return {"status": f"{market}_QUOTE_SOURCE_CONTENT_MISMATCH", "quote": None}

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
