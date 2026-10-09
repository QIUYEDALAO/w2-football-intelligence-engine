"""v3 专用同源双侧盘口选择器（AH/OU 终验 S2）。

**AH 与 OU 的报价准入口径不同（指令书 C，2026-10-10）：**

- **AH**：只认 Pinnacle（``bookmaker_id == "4"``），且只接受**半球线**（小数部分
  恰为 ``.5``）。阈值 ``0.04346830297815201`` 是在「Pinnacle 半球线群体」上定标的
  （``|q−0.5|`` 中位 0.066）；2026-10-06 把报价源放宽到任意 bookmaker 后，选线规则
  「挑最平衡那条」必然挑到 Pinnacle 自己挂的四分之一球线（``|q−0.5|`` 被压到 0.017），
  阈值就此够不到 —— 取价群体迁移而未同步迁移阈值，通道被构造性关闭（136 行 0 入选）。
  非半球线按 ``UNSUPPORTED_AH_LINE_V1`` 留档，不参与选线。无合规 Pinnacle 半球报价
  即 SKIP 留档，**绝不 fallback 到 f9 快照报价**（那是口径分裂的根源）。
- **OU**：保持现口径（任一双侧来自同一 bookmaker 且同一时点即可准入）不动 —— OU 当前
  为正单位，整体回退会把它一起改掉。

Selection contract (all fail closed):
1. canonical fixture + not live/suspended. AH 额外要求 Pinnacle 且线型为半球线.
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

# 指令书 C §一：AH 报价准入只认 Pinnacle；阈值 0.04346830297815201 的定标群体就是它。
# OU 不受此约束（保持现口径，见模块 docstring）。
AH_PINNACLE_BOOKMAKER_ID = "4"
# 指令书 C §一：非半球线（整数线有走盘、四分之一线半赢半输，而模型按二元赢盘/输盘训练）
# 的留档码。它必须以 AH_ 前缀之外的形式进入 status，故在 ah_ou_decision 的
# market_reasons_for_status 里显式登记为「只怪 AH」。
UNSUPPORTED_AH_LINE_V1 = "UNSUPPORTED_AH_LINE_V1"


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
    """True when the same side carries two rows on the same line *within the
    same bookmaker* (a true duplicate side that must be refused, never silently
    deduplicated). Cross-bookmaker rows on the same line are independent facts
    (each bookmaker pairs its own two sides), so they are not duplicates."""
    seen: set[tuple[str, str]] = set()
    for row in rows:
        bookmaker = str(row.get("bookmaker_id") or "")
        if not bookmaker:
            # 空 bookmaker 跳过（与 TOTALS 分支及 AH 配对一致）：空 bookmaker 行
            # 无法成对，不应因两条空 bookmaker 同盘口同侧而误判 DUPLICATE_SIDE。
            continue
        line = _decimal(row.get("line"))
        if line is None:
            continue
        key = (bookmaker, str(line.normalize()))
        if key in seen:
            return True
        seen.add(key)
    return False


def _is_half_line(line: Decimal | None) -> bool:
    """True only for a hemisphere line: the fractional part is exactly ``.5``.

    ``−0.5 / +0.5 / −1.5 / +1.5 …`` qualify. Integer lines (``−1 / 0 / +1``) can
    push and quarter lines (``−0.25 / +0.75``) split the stake in half; the frozen
    model is trained on a binary win/lose label, so neither is admissible. A
    non-finite or missing line is never a hemisphere line (fail closed).
    """
    if line is None or not line.is_finite():
        return False
    doubled = line * 2
    return doubled == doubled.to_integral_value() and line != line.to_integral_value()


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
    if not rows:
        return False
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
    archived: list[dict[str, Any]] = []
    if market == AH_MARKET:
        # 指令书 C §一：AH 报价准入只认 Pinnacle（bookmaker_id == "4"）。
        # 无合规 Pinnacle 报价 → SKIP 留档，绝不 fallback 到 f9 快照报价。
        pinnacle_rows = [
            row
            for row in latest_rows
            if str(row.get("bookmaker_id") or "") == AH_PINNACLE_BOOKMAKER_ID
        ]
        if not pinnacle_rows:
            return {"status": f"{market}_QUOTE_NOT_PINNACLE", "quote": None, "archived": []}
        # 指令书 C §一：选线范围只收小数部分 = .5 的线；其他线型留档，不参与选线。
        candidate_rows = [
            row for row in pinnacle_rows if _is_half_line(_decimal(row.get("line")))
        ]
        archived = [
            {
                "bookmaker_id": AH_PINNACLE_BOOKMAKER_ID,
                "line": _decimal_text(row.get("line")),
                "selection": _side(row),
                "archive_code": UNSUPPORTED_AH_LINE_V1,
            }
            for row in pinnacle_rows
            if not _is_half_line(_decimal(row.get("line")))
        ]
        if not candidate_rows:
            # 有 Pinnacle 报价但无一条半球线：原因就是线型，直接以留档码 SKIP。
            return {"status": UNSUPPORTED_AH_LINE_V1, "quote": None, "archived": archived}
        home_rows = [row for row in candidate_rows if _side(row) == side_a]
        away_rows = [row for row in candidate_rows if _side(row) == side_b]
        # C: a duplicate side on the same line (even same price) is a refusal.
        if _has_duplicate_line(home_rows) or _has_duplicate_line(away_rows):
            return {"status": f"{market}_QUOTE_DUPLICATE_SIDE", "quote": None}
        # 按 bookmaker 分组 away，同 bookmaker 内配对（避免 O(H×A) 跨 bookmaker 无效比较）。
        away_by_bookmaker: dict[str, list[dict[str, Any]]] = {}
        for away_row in away_rows:
            away_by_bookmaker.setdefault(
                str(away_row.get("bookmaker_id") or ""), []
            ).append(away_row)
        for home_row in home_rows:
            home_price = _float(home_row.get("decimal_odds") or home_row.get("executable_odds"))
            if home_price is None or home_price <= 1.0:
                return {"status": f"{market}_QUOTE_PRICE_INVALID", "quote": None}
            home_line = _decimal(home_row.get("line"))
            if home_line is None:
                return {"status": f"{market}_QUOTE_LINE_INVALID", "quote": None}
            home_bookmaker = str(home_row.get("bookmaker_id") or "")
            if not home_bookmaker:
                continue
            for away_row in away_by_bookmaker.get(home_bookmaker, []):
                away_price = _float(away_row.get("decimal_odds") or away_row.get("executable_odds"))
                if away_price is None or away_price <= 1.0:
                    return {"status": f"{market}_QUOTE_PRICE_INVALID", "quote": None}
                away_line = _decimal(away_row.get("line"))
                if away_line is None:
                    return {"status": f"{market}_QUOTE_LINE_INVALID", "quote": None}
                # ⚠️ 已登记的缺陷（2026-10-10，指令书 C 实施期发现，未修，待 Owner 裁定）：
                # `-home_line` 这一支允许**跨线伪配对**——把 +0.5 的 HOME 价与 −0.5 的
                # AWAY 价拼成一对。那不是任何一条线的双侧报价，且两侧价格天然更接近
                # 1.90/1.90，会被排序键优先选中，使 |q−0.5| 塌到 0.02 量级、AH 阈值永远
                # 够不到。生产实测（50992 个 Pinnacle fixture/capture 组）：50,022 组只
                # 有同线形状、970 组两种都有、**0 组仅取负形状** ⇒ 取负分支从不承担配对。
                # 727 场生产选择器回放：允许跨线 达阈值 122/642 = 19.0%（与研究选线同线
                # 89.3%）；只收同线 达阈值 241/642 = 37.5%（同线率 100.0%）。
                if away_line not in {home_line, -home_line}:
                    continue
                pair = _make_pair(
                    side_a=side_a, side_b=side_b, line=home_line,
                    row_a=home_row, row_b=away_row,
                )
                if pair is not None:
                    pairs.append(pair)
    else:
        line_groups: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
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
            bookmaker = str(row.get("bookmaker_id") or "")
            if not bookmaker:
                # 空 bookmaker 跳过（与 AH 分支一致）：不参与分组，避免两条空
                # bookmaker 同盘口同侧被误判 DUPLICATE_SIDE。
                continue
            # 按 (bookmaker, line) 独立分组：每个 bookmaker 各自配自己的 OVER/UNDER，
            # 跨 bookmaker 的同盘口同侧不是重复（bookmaker 32 和 8 的 OVER@0.5 各自成对）。
            group = line_groups.setdefault((bookmaker, str(line.normalize())), {})
            if side in group:
                # C: 同一 bookmaker 内同盘口同侧（即使同价）才是真重复，必须拒绝。
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
        # AH：本次 capture 内被排除（非半球线）的 Pinnacle 行留档，供诊断与
        # 「为什么选到这条线」回溯；OU 恒为空列表。
        "archived": archived,
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
