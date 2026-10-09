"""R2 报价选择器：来源内容闭合反例 + 主线选择正例（独立验收用）。"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from w2.domain.canonical_serialization import (
    HashDomain,
    SerializerVersion,
    canonical_sha256,
)
from w2.strategy.ah_ou_quote_selector import select_v3_ah_ou_quotes

FIXTURE_ID = "FIX1"
DECISION_AT = datetime(2026, 8, 1, 10, 0, tzinfo=UTC)
CAPTURE_ID = "cap-1"


def _raw(*, fixture: str = FIXTURE_ID, ah: list[tuple[str, str]] | None = None,
          ou: list[tuple[str, str]] | None = None) -> dict:
    ah = ah or [("Home -0.5", "1.80"), ("Away +0.5", "2.05")]
    ou = ou or [("Over 2.5", "1.90"), ("Under 2.5", "1.90")]
    return {
        "response": [
            {
                "fixture": {"id": fixture},
                "bookmakers": [
                    {
                        "id": 4,
                        "name": "Pinnacle",
                        "bets": [
                            {"id": 1, "name": "Asian Handicap", "values": [
                                {"value": value, "odd": odd} for value, odd in ah
                            ]},
                            {"id": 2, "name": "Goals Over/Under", "values": [
                                {"value": value, "odd": odd} for value, odd in ou
                            ]},
                        ],
                    }
                ],
            }
        ]
    }


def _row(*, market, selection, line, odds, capture_id=CAPTURE_ID, raw_payload, **overrides) -> dict:
    row = {
        "fixture_id": FIXTURE_ID,
        "bookmaker_id": "4",
        "capture_id": capture_id,
        "canonical_market": market,
        "canonical_selection": selection,
        "selection": selection,
        "line": line,
        "decimal_odds": odds,
        "suspended": False,
        "live": False,
        "captured_at": (DECISION_AT - timedelta(minutes=30)).isoformat(),
        "raw_payload_sha256": canonical_sha256(
            raw_payload,
            domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD,
            version=SerializerVersion.LEGACY_V1,
        ),
    }
    row.update(overrides)
    return row


def _obs(raw: dict) -> list[dict]:
    return [
        _row(market="ASIAN_HANDICAP", selection="HOME", line="-0.5", odds="1.80", raw_payload=raw),
        _row(market="ASIAN_HANDICAP", selection="AWAY", line="-0.5", odds="2.05", raw_payload=raw),
        _row(market="TOTALS", selection="OVER", line="2.5", odds="1.90", raw_payload=raw),
        _row(market="TOTALS", selection="UNDER", line="2.5", odds="1.90", raw_payload=raw),
    ]


def test_ready_with_matching_raw() -> None:
    raw = _raw()
    result = select_v3_ah_ou_quotes(
        _obs(raw), fixture_id=FIXTURE_ID, decision_at=DECISION_AT,
        raw_payloads={CAPTURE_ID: raw},
    )
    assert result["status"] == "READY"


def test_projection_only_duplicate_side_is_refused_after_ready_control() -> None:
    raw = _raw()
    rows = _obs(raw)
    assert select_v3_ah_ou_quotes(rows, fixture_id=FIXTURE_ID, decision_at=DECISION_AT,
                                  raw_payloads={CAPTURE_ID: raw})["status"] == "READY"
    rows.insert(1, dict(rows[0]))
    result = select_v3_ah_ou_quotes(rows, fixture_id=FIXTURE_ID,
                                    decision_at=DECISION_AT, raw_payloads={CAPTURE_ID: raw})
    assert result["ah"]["status"] == "ASIAN_HANDICAP_QUOTE_DUPLICATE_SIDE"


@pytest.mark.parametrize("price", [None, "NaN", "Inf", "-Inf"])
def test_nonfinite_or_missing_price_is_refused_after_ready_control(price) -> None:
    raw = _raw()
    rows = _obs(raw)
    assert select_v3_ah_ou_quotes(rows, fixture_id=FIXTURE_ID, decision_at=DECISION_AT,
                                  raw_payloads={CAPTURE_ID: raw})["status"] == "READY"
    rows[0]["decimal_odds"] = price
    result = select_v3_ah_ou_quotes(rows, fixture_id=FIXTURE_ID,
                                    decision_at=DECISION_AT, raw_payloads={CAPTURE_ID: raw})
    assert result["ah"]["status"] == "ASIAN_HANDICAP_QUOTE_PRICE_INVALID"


def test_cross_fixture_raw_is_refused() -> None:
    # 投影行指向 FIX1，但 raw payload 内容是别的 fixture
    raw = _raw(fixture="OTHER")
    result = select_v3_ah_ou_quotes(
        _obs(raw), fixture_id=FIXTURE_ID, decision_at=DECISION_AT,
        raw_payloads={CAPTURE_ID: raw},
    )
    assert result["ah"]["status"] == "ASIAN_HANDICAP_QUOTE_SOURCE_CONTENT_MISMATCH"


def test_tampered_price_in_raw_is_refused() -> None:
    raw = _raw()
    # 改 raw 里的价格，投影行仍引旧价
    raw["response"][0]["bookmakers"][0]["bets"][0]["values"][0]["odd"] = "2.50"
    result = select_v3_ah_ou_quotes(
        _obs(raw), fixture_id=FIXTURE_ID, decision_at=DECISION_AT,
        raw_payloads={CAPTURE_ID: raw},
    )
    assert result["ah"]["status"] == "ASIAN_HANDICAP_QUOTE_SOURCE_CONTENT_MISMATCH"


def test_tampered_hash_in_row_is_refused() -> None:
    raw = _raw()
    rows = _obs(raw)
    rows[0]["raw_payload_sha256"] = "f" * 64  # 投影行 hash 与 raw 内容不符
    result = select_v3_ah_ou_quotes(
        rows, fixture_id=FIXTURE_ID, decision_at=DECISION_AT,
        raw_payloads={CAPTURE_ID: raw},
    )
    assert result["ah"]["status"] == "ASIAN_HANDICAP_QUOTE_SOURCE_CONTENT_MISMATCH"


def test_missing_side_is_refused() -> None:
    raw = _raw()
    rows = _obs(raw)
    rows.pop(1)
    result = select_v3_ah_ou_quotes(
        rows, fixture_id=FIXTURE_ID, decision_at=DECISION_AT,
        raw_payloads={CAPTURE_ID: raw},
    )
    assert result["ah"]["status"] == "ASIAN_HANDICAP_QUOTE_SIDE_INCOMPLETE"


def test_cross_capture_is_refused() -> None:
    raw = _raw()
    rows = _obs(raw)
    rows[1]["capture_id"] = "cap-2"
    result = select_v3_ah_ou_quotes(
        rows, fixture_id=FIXTURE_ID, decision_at=DECISION_AT,
        raw_payloads={CAPTURE_ID: raw},
    )
    assert result["ah"]["status"] == "ASIAN_HANDICAP_QUOTE_NOT_SAME_CAPTURE"


def test_late_price_is_refused() -> None:
    raw = _raw()
    rows = _obs(raw)
    for row in rows[:2]:
        row["captured_at"] = (DECISION_AT + timedelta(minutes=5)).isoformat()
    result = select_v3_ah_ou_quotes(
        rows, fixture_id=FIXTURE_ID, decision_at=DECISION_AT,
        raw_payloads={CAPTURE_ID: raw},
    )
    assert result["ah"]["status"] == "ASIAN_HANDICAP_QUOTE_CAPTURED_AFTER_DECISION"


def test_non_pinnacle_accepted_for_ou_only() -> None:
    """指令书 C：AH/OU 口径分叉的定点回归。

    非 Pinnacle 同 bookmaker 报价 → **OU 准入**（保持现口径不动），**AH 拒绝**
    （AH 只认 Pinnacle）。2026-10-06 把两个市场一起放宽到任意 bookmaker，导致 AH
    取价群体迁移而阈值 0.043468 未迁移、让球通道被构造性关闭；本次只把 AH 收回来。
    """
    raw = _raw()
    raw["response"][0]["bookmakers"][0]["id"] = 8
    raw["response"][0]["bookmakers"][0]["name"] = "Bet365"
    rows = _obs(raw)
    for row in rows:
        row["bookmaker_id"] = "8"
    result = select_v3_ah_ou_quotes(
        rows, fixture_id=FIXTURE_ID, decision_at=DECISION_AT,
        raw_payloads={CAPTURE_ID: raw},
    )
    assert result["ah"]["status"] == "ASIAN_HANDICAP_QUOTE_NOT_PINNACLE"
    assert result["ou"]["status"] == "READY"
    assert result["status"] == "QUOTE_SELECTION_FAILED"


def test_cross_bookmaker_pair_is_refused() -> None:
    """任务1 验收③：两侧不同 bookmaker → 拒绝，不引入跨 bookmaker 报价漂移。"""
    raw = _raw()
    rows = _obs(raw)
    rows[1]["bookmaker_id"] = "8"  # AH away 改成另一 bookmaker，home 仍是 4
    result = select_v3_ah_ou_quotes(
        rows, fixture_id=FIXTURE_ID, decision_at=DECISION_AT,
        raw_payloads={CAPTURE_ID: raw},
    )
    # AH 双侧 bookmaker 不一致 → 配不出对 → SIDE_INCOMPLETE；OU 仍 READY（同 bookmaker）。
    assert result["ah"]["status"] == "ASIAN_HANDICAP_QUOTE_SIDE_INCOMPLETE"
    assert result["ou"]["status"] == "READY"


def test_ah_wrong_line_is_refused() -> None:
    raw = _raw(ah=[("Home -0.5", "1.80"), ("Away +0.25", "2.05")])
    rows = _obs(raw)
    rows[1]["line"] = "0.25"  # away 线与 home 线既不相等也不互补
    result = select_v3_ah_ou_quotes(
        rows, fixture_id=FIXTURE_ID, decision_at=DECISION_AT,
        raw_payloads={CAPTURE_ID: raw},
    )
    assert result["ah"]["status"] == "ASIAN_HANDICAP_QUOTE_SIDE_INCOMPLETE"


def test_same_capture_two_ou_lines_selects_mainline() -> None:
    # 同 capture 两条合法 OU 线（2.5 平衡、3.5 失衡），应稳定选到平衡主线 2.5
    raw = _raw(ou=[
        ("Over 2.5", "1.90"), ("Under 2.5", "1.90"),
        ("Over 3.5", "1.40"), ("Under 3.5", "2.80"),
    ])
    rows = _obs(raw)
    rows += [
        _row(market="TOTALS", selection="OVER", line="3.5", odds="1.40", raw_payload=raw),
        _row(market="TOTALS", selection="UNDER", line="3.5", odds="2.80", raw_payload=raw),
    ]
    result = select_v3_ah_ou_quotes(
        rows, fixture_id=FIXTURE_ID, decision_at=DECISION_AT,
        raw_payloads={CAPTURE_ID: raw},
    )
    assert result["ou"]["status"] == "READY"
    assert result["ou"]["quote"]["line"] == __import__("decimal").Decimal("2.5")
    assert result["ou"]["quote"]["side_prices"] == {"over": 1.90, "under": 1.90}


def test_ah_cross_line_pair_is_never_accepted() -> None:
    """指令书 C 补充裁定①：AH 双侧必须来自**同一条 canonical 线**，禁止跨线配对。

    本用例原为 `test_ah_away_repeated_home_perspective_line_is_accepted`，断言「取负
    形状合法」。该契约经两方独立复算证伪并**锁定的是一个 bug 而非设计意图**：
      · 生产 50,992 个 Pinnacle fixture/capture 组：仅同线 50,022 / 两种都有 970 /
        **仅取负 0**；
      · 研究报价池 6,999 组：仅同线 1,080 / 两种都有 5,919 / **仅取负 0**。
    取负分支从不承担配对，只制造跨线伪配对——把 +L 的 HOME 价与 −L 的 AWAY 价拼成
    一对，其两侧价天然更接近 1.90/1.90，会被排序键优先选中，把 |q−0.5| 压到 0.02
    量级，AH 阈值永远够不到（通道即使恢复 Pinnacle 与 .5 线仍被构造性关闭）。
    故按裁定改为同线契约：不同线的两侧配不出对 → SIDE_INCOMPLETE。
    """
    raw = _raw(ah=[("Home -0.5", "1.80"), ("Away -0.5", "2.05")])
    rows = _obs(raw)
    rows[1]["line"] = "0.5"  # away 与 home 不同线（跨线形状）
    result = select_v3_ah_ou_quotes(
        rows, fixture_id=FIXTURE_ID, decision_at=DECISION_AT,
        raw_payloads={CAPTURE_ID: raw},
    )
    assert result["ah"]["status"] == "ASIAN_HANDICAP_QUOTE_SIDE_INCOMPLETE"


def test_t3_stale_quote_over_24h_is_refused() -> None:
    # T3 报价新鲜度上界：7 天前报价不得进入主线（STALE_QUOTE）。
    raw = _raw()
    rows = _obs(raw)
    for row in rows:
        row["captured_at"] = (DECISION_AT - timedelta(days=7)).isoformat()
    result = select_v3_ah_ou_quotes(
        rows, fixture_id=FIXTURE_ID, decision_at=DECISION_AT,
        raw_payloads={CAPTURE_ID: raw},
    )
    assert result["ah"]["status"] == "ASIAN_HANDICAP_STALE_QUOTE"
    assert result["ou"]["status"] == "TOTALS_STALE_QUOTE"
    assert result["status"] == "QUOTE_SELECTION_FAILED"


def test_t3_quote_within_24h_is_selected() -> None:
    # T3：阈值内（23h）报价正常入选。
    raw = _raw()
    rows = _obs(raw)
    for row in rows:
        row["captured_at"] = (DECISION_AT - timedelta(hours=23)).isoformat()
    result = select_v3_ah_ou_quotes(
        rows, fixture_id=FIXTURE_ID, decision_at=DECISION_AT,
        raw_payloads={CAPTURE_ID: raw},
    )
    assert result["status"] == "READY"


def test_t3_quote_exactly_24h_is_selected_boundary() -> None:
    # T3 边界：恰好 24h 视为「≤ 阈值」，准入（> 24h 才 STALE_QUOTE）。
    raw = _raw()
    rows = _obs(raw)
    for row in rows:
        row["captured_at"] = (DECISION_AT - timedelta(hours=24)).isoformat()
    result = select_v3_ah_ou_quotes(
        rows, fixture_id=FIXTURE_ID, decision_at=DECISION_AT,
        raw_payloads={CAPTURE_ID: raw},
    )
    assert result["status"] == "READY"


def _raw_multi_bookmaker_ou(*, home_line: str = "-0.5") -> dict:
    """两个 bookmaker（32/8）各带一条同盘口 TOTALS 双侧，复现 1490326 回归。"""
    return {
        "response": [
            {
                "fixture": {"id": FIXTURE_ID},
                "bookmakers": [
                    {
                        "id": 32,
                        "name": "Bookmaker32",
                        "bets": [
                            {"id": 1, "name": "Asian Handicap", "values": [
                                {"value": f"Home {home_line}", "odd": "1.80"},
                                {"value": f"Away {(-Decimal(home_line)) if home_line.startswith("-") else "+" + home_line}", "odd": "2.05"},
                            ]},
                            {"id": 2, "name": "Goals Over/Under", "values": [
                                {"value": "Over 0.5", "odd": "1.03"},
                                {"value": "Under 0.5", "odd": "9.00"},
                            ]},
                        ],
                    },
                    {
                        "id": 8,
                        "name": "Bookmaker8",
                        "bets": [
                            {"id": 1, "name": "Asian Handicap", "values": [
                                {"value": f"Home {home_line}", "odd": "1.82"},
                                {"value": f"Away {home_line}", "odd": "2.02"},
                            ]},
                            {"id": 2, "name": "Goals Over/Under", "values": [
                                {"value": "Over 0.5", "odd": "1.01"},
                                {"value": "Under 0.5", "odd": "11.00"},
                            ]},
                        ],
                    },
                ],
            }
        ]
    }


def _rows_multi_bookmaker_ou(raw: dict) -> list[dict]:
    rows: list[dict] = []
    for bookmaker, over, under, ah_home, ah_away in (
        ("32", "1.03", "9.00", "1.80", "2.05"),
        ("8", "1.01", "11.00", "1.82", "2.02"),
    ):
        rows.append(_row(market="ASIAN_HANDICAP", selection="HOME", line="-0.5",
                         odds=ah_home, raw_payload=raw, bookmaker_id=bookmaker))
        rows.append(_row(market="ASIAN_HANDICAP", selection="AWAY", line="-0.5",
                         odds=ah_away, raw_payload=raw, bookmaker_id=bookmaker))
        rows.append(_row(market="TOTALS", selection="OVER", line="0.5",
                         odds=over, raw_payload=raw, bookmaker_id=bookmaker))
        rows.append(_row(market="TOTALS", selection="UNDER", line="0.5",
                         odds=under, raw_payload=raw, bookmaker_id=bookmaker))
    return rows


def test_totals_multi_bookmaker_same_line_is_not_duplicate() -> None:
    """任务回归修复：多 bookmaker 同盘口同侧（32+8 的 OVER@0.5）各自独立成对，
    不再误判 DUPLICATE_SIDE；推荐恢复（OU READY）。"""
    raw = _raw_multi_bookmaker_ou()
    result = select_v3_ah_ou_quotes(
        _rows_multi_bookmaker_ou(raw), fixture_id=FIXTURE_ID, decision_at=DECISION_AT,
        raw_payloads={CAPTURE_ID: raw},
    )
    assert result["ou"]["status"] == "READY"
    # 选到价格最接近 1.90/1.90 的 bookmaker 32 主线（OVER 1.03 / UNDER 9.00）。
    assert result["ou"]["quote"]["side_prices"] == {"over": 1.03, "under": 9.00}


def test_ah_multi_bookmaker_regime_is_refused_under_pinnacle_only() -> None:
    """指令书 C：AH 只认 Pinnacle，「多 bookmaker 同盘口同侧各自配对」在 AH 上已不可达
    —— 直接以 NOT_PINNACLE 拒绝；同一份数据在 OU 上仍各自成对（保持现口径）。"""
    raw = _raw_multi_bookmaker_ou()
    result = select_v3_ah_ou_quotes(
        _rows_multi_bookmaker_ou(raw), fixture_id=FIXTURE_ID, decision_at=DECISION_AT,
        raw_payloads={CAPTURE_ID: raw},
    )
    assert result["ah"]["status"] == "ASIAN_HANDICAP_QUOTE_NOT_PINNACLE"
    assert result["ou"]["status"] == "READY"


def test_totals_same_bookmaker_duplicate_side_still_refused() -> None:
    """验收②：同一 bookmaker 内同盘口同侧真重复仍拒绝 QUOTE_DUPLICATE_SIDE。"""
    raw = _raw_multi_bookmaker_ou()
    rows = _rows_multi_bookmaker_ou(raw)
    # 复制 bookmaker 32 的 OVER@0.5 一行（同 bookmaker 同盘口同侧真重复）。
    rows.append(_row(market="TOTALS", selection="OVER", line="0.5", odds="1.03",
                     raw_payload=raw, bookmaker_id="32"))
    result = select_v3_ah_ou_quotes(
        rows, fixture_id=FIXTURE_ID, decision_at=DECISION_AT,
        raw_payloads={CAPTURE_ID: raw},
    )
    assert result["ou"]["status"] == "TOTALS_QUOTE_DUPLICATE_SIDE"


def test_totals_empty_bookmaker_is_skipped_not_duplicate() -> None:
    """隐患①：空 bookmaker 跳过（与 AH 一致），两条空 bookmaker 同盘口同侧不再误判
    DUPLICATE_SIDE（而是无有效双侧 → SIDE_INCOMPLETE）。"""
    raw = _raw()
    rows = [
        _row(market="TOTALS", selection="OVER", line="0.5", odds="1.50",
             raw_payload=raw, bookmaker_id=""),
        _row(market="TOTALS", selection="OVER", line="0.5", odds="1.40",
             raw_payload=raw, bookmaker_id=""),
    ]
    result = select_v3_ah_ou_quotes(
        rows, fixture_id=FIXTURE_ID, decision_at=DECISION_AT,
        raw_payloads={CAPTURE_ID: raw},
    )
    assert result["ou"]["status"] == "TOTALS_QUOTE_SIDE_INCOMPLETE"


def test_ah_empty_bookmaker_is_refused_as_not_pinnacle() -> None:
    """指令书 C：空 bookmaker 在 AH 上不再是「跳过参与配对」，而是直接 NOT_PINNACLE。

    AH 只认 Pinnacle，空 bookmaker 天然不合格，拒绝理由比 SIDE_INCOMPLETE 更准确。
    （「空 bookmaker 不误判 DUPLICATE_SIDE」的语义仍由 OU 侧覆盖。）
    """
    raw = _raw()
    rows = [
        _row(market="ASIAN_HANDICAP", selection="HOME", line="-0.5", odds="1.80",
             raw_payload=raw, bookmaker_id=""),
        _row(market="ASIAN_HANDICAP", selection="HOME", line="-0.5", odds="1.85",
             raw_payload=raw, bookmaker_id=""),
    ]
    result = select_v3_ah_ou_quotes(
        rows, fixture_id=FIXTURE_ID, decision_at=DECISION_AT,
        raw_payloads={CAPTURE_ID: raw},
    )
    assert result["ah"]["status"] == "ASIAN_HANDICAP_QUOTE_NOT_PINNACLE"


# ─────────────────────────────────────────────────────────────────────────────
# 指令书 C §一（AH 通道恢复）：Pinnacle 准入 + 只收半球线 + 非半球线留档
# ─────────────────────────────────────────────────────────────────────────────


def _ah_rows(raw: dict, values: list[tuple[str, str]]) -> list[dict]:
    """按 raw 的 AH values 构造对应的投影行（bookmaker 固定 Pinnacle = "4"）。

    provider 的 away 侧线以 away 视角给出，投影到 canonical（home 视角）时取负：
    与 ``_obs`` 一致（raw ``Away -0.5`` ↔ 行 ``line="0.5"``）。
    """
    rows: list[dict] = []
    for value, odds in values:
        side, _, line = value.partition(" ")
        canonical_line = line if side == "Home" else str(-Decimal(line))
        rows.append(
            _row(
                market="ASIAN_HANDICAP",
                selection="HOME" if side == "Home" else "AWAY",
                line=canonical_line,
                odds=odds,
                raw_payload=raw,
            )
        )
    return rows


def test_ah_selects_only_half_line_and_archives_the_others() -> None:
    """指令书 C §一（核心）：AH 选线范围只收小数部分 = .5 的线。

    raw 同时挂四分之一球线（-0.25/+0.25）与半球线（-0.5/+0.5）：只从半球线选，
    四分之一线以 ``UNSUPPORTED_AH_LINE_V1`` 留档，不参与选线。
    """
    values = [("Home -0.25", "1.60"), ("Away 0.25", "2.30"),
              ("Home -0.5", "1.80"), ("Away 0.5", "2.05")]
    raw = _raw(ah=values)
    result = select_v3_ah_ou_quotes(
        _ah_rows(raw, values), fixture_id=FIXTURE_ID, decision_at=DECISION_AT,
        raw_payloads={CAPTURE_ID: raw},
    )
    assert result["ah"]["status"] == "READY"
    assert result["ah"]["quote"]["line"] == -0.5
    assert {item["archive_code"] for item in result["ah"]["archived"]} == {
        "UNSUPPORTED_AH_LINE_V1"
    }
    # 两条四分之一球线（home -0.25 与 away 归一到 -0.25）都在留档里
    assert [item["line"] for item in result["ah"]["archived"]] == ["-0.25", "-0.25"]
    assert {item["selection"] for item in result["ah"]["archived"]} == {"HOME", "AWAY"}


@pytest.mark.parametrize(
    "values",
    [
        [("Home -0.25", "1.90"), ("Away 0.25", "1.90")],   # 只有四分之一线
        [("Home -1", "1.90"), ("Away 1", "1.90")],          # 只有整数线
        [("Home 0", "1.90"), ("Away 0", "1.90")],           # 只有平手盘（整数）
    ],
)
def test_ah_without_any_half_line_skips_as_unsupported(values) -> None:
    """指令书 C §一 fail-closed：有 Pinnacle 报价但无一条半球线 → SKIP 留档。

    绝不 fallback 到 f9 快照报价（那是口径分裂的根源）。
    """
    raw = _raw(ah=values)
    result = select_v3_ah_ou_quotes(
        _ah_rows(raw, values), fixture_id=FIXTURE_ID, decision_at=DECISION_AT,
        raw_payloads={CAPTURE_ID: raw},
    )
    assert result["ah"]["status"] == "UNSUPPORTED_AH_LINE_V1"
    assert result["ah"]["quote"] is None
    assert len(result["ah"]["archived"]) == len(values)
    assert result["status"] == "QUOTE_SELECTION_FAILED"


def test_ah_picks_the_half_line_closest_to_1_9_1_9() -> None:
    """指令书 C §一 选线键：在 .5 线集合内取 |home−1.9|+|away−1.9| 最小者。

    −0.5 挂 (1.90, 1.90) → 距离和 0.00；−1.5 挂 (1.85, 1.95) → 0.05+0.05。
    严格取小者 → −0.5。
    """
    values = [("Home -1.5", "1.85"), ("Away 1.5", "1.95"),
              ("Home -0.5", "1.90"), ("Away 0.5", "1.90")]
    raw = _raw(ah=values)
    result = select_v3_ah_ou_quotes(
        _ah_rows(raw, values), fixture_id=FIXTURE_ID, decision_at=DECISION_AT,
        raw_payloads={CAPTURE_ID: raw},
    )
    assert result["ah"]["status"] == "READY"
    assert result["ah"]["quote"]["line"] == -0.5


def test_pair_sort_key_primary_dominates_then_absolute_line() -> None:
    """指令书 C §一 排序键逐层验证（与研究口径逐字一致）。

    ``(primary, |line|, price_gap, |line|)``：主键 ``|p1−1.9|+|p2−1.9|`` 优先于
    |line|；主键完全相同时才由 |line| 决定。
    """
    from w2.strategy.ah_ou_quote_selector import _pair_sort_key

    def key(price_a, price_b, line, gap=0.0):
        return _pair_sort_key(
            {"price_a": price_a, "price_b": price_b, "line": line, "price_gap": gap},
            market="ASIAN_HANDICAP",
        )

    # 主键优先：A（0.02，|line|=1.5）胜过 B（0.03，|line|=0.5）
    assert key(1.91, 1.91, -1.5) < key(1.93, 1.90, -0.5)
    # 主键完全相同（同价格）→ 次键 |line| 取小
    assert key(1.95, 1.95, -0.5) < key(1.95, 1.95, -1.5)
    # 价格完全相同时才落到 |line|，与 line 符号无关（取绝对值）
    assert key(1.95, 1.95, 0.5) == key(1.95, 1.95, -0.5)


@pytest.mark.parametrize(
    "line,expected",
    [
        ("-0.5", True), ("0.5", True), ("-1.5", True), ("2.5", True),
        ("-0.25", False), ("0.75", False), ("-1", False), ("0", False), ("1", False),
        ("-2.25", False),
    ],
)
def test_is_half_line(line, expected) -> None:
    """半球线判定：小数部分恰为 .5。整数线有走盘、四分之一线半赢半输，都不可用。"""
    from decimal import Decimal

    from w2.strategy.ah_ou_quote_selector import _is_half_line

    assert _is_half_line(Decimal(line)) is expected
    assert _is_half_line(None) is False


def test_unsupported_ah_line_status_blames_ah_only() -> None:
    """``UNSUPPORTED_AH_LINE_V1`` 不带 AH_ 前缀，必须显式登记为 AH-only。

    否则它会走「共同状态」分支把 OU 也标成阻断，让只属于 AH 的线型问题把两条
    通道一起 SKIP。
    """
    from w2.strategy.ah_ou_decision import market_reasons_for_status

    reasons = market_reasons_for_status("UNSUPPORTED_AH_LINE_V1")
    assert reasons["ASIAN_HANDICAP"] == "UNSUPPORTED_AH_LINE_V1"
    assert reasons["TOTALS"] == "DEPENDENCY_BLOCKED"


def test_source_content_matches_empty_rows_returns_false() -> None:
    """隐患②：_source_content_matches 空 rows 返回 False（不 IndexError）。"""
    from w2.strategy.ah_ou_quote_selector import _source_content_matches

    assert _source_content_matches([], _raw(), capture_id=CAPTURE_ID) is False
