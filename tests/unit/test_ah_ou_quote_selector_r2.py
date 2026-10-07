"""R2 报价选择器：来源内容闭合反例 + 主线选择正例（独立验收用）。"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

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
    ah = ah or [("Home -0.5", "1.80"), ("Away -0.5", "2.05")]
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
        _row(market="ASIAN_HANDICAP", selection="AWAY", line="0.5", odds="2.05", raw_payload=raw),
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


def test_non_pinnacle_same_bookmaker_is_accepted() -> None:
    """任务1：非 Pinnacle 但属主流主线的报价 → 正常准入（不再 QUOTE_NOT_PINNACLE）。"""
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
    assert result["status"] == "READY"
    assert result["ah"]["status"] == "READY"
    assert result["ou"]["status"] == "READY"


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
    raw = _raw(ah=[("Home -0.5", "1.80"), ("Away -0.25", "2.05")])
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


def test_ah_away_repeated_home_perspective_line_is_accepted() -> None:
    # API-Football 会在两侧重复 home 视角同线（away 值带 home 的盘口符号），
    # 采集归一后 away 落库为 team 视角（取反），canonical 仍是 home 视角 L。
    raw = _raw(ah=[("Home -0.5", "1.80"), ("Away -0.5", "2.05")])
    rows = _obs(raw)
    rows[1]["line"] = "0.5"  # away 归一为 team 视角（home -0.5 → away +0.5）
    result = select_v3_ah_ou_quotes(
        rows, fixture_id=FIXTURE_ID, decision_at=DECISION_AT,
        raw_payloads={CAPTURE_ID: raw},
    )
    assert result["ah"]["status"] == "READY"
    assert result["ah"]["quote"]["line"] == __import__("decimal").Decimal("-0.5")


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
                                {"value": f"Away {home_line}", "odd": "2.05"},
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
        rows.append(_row(market="ASIAN_HANDICAP", selection="AWAY", line="0.5",
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


def test_ah_multi_bookmaker_same_line_is_not_duplicate() -> None:
    """AH 同理：多 bookmaker 同盘口同侧各自配对，不再因跨 bookmaker 同侧判重。"""
    raw = _raw_multi_bookmaker_ou()
    result = select_v3_ah_ou_quotes(
        _rows_multi_bookmaker_ou(raw), fixture_id=FIXTURE_ID, decision_at=DECISION_AT,
        raw_payloads={CAPTURE_ID: raw},
    )
    assert result["ah"]["status"] == "READY"


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


def test_source_content_matches_empty_rows_returns_false() -> None:
    """隐患②：_source_content_matches 空 rows 返回 False（不 IndexError）。"""
    from w2.strategy.ah_ou_quote_selector import _source_content_matches

    assert _source_content_matches([], _raw(), capture_id=CAPTURE_ID) is False
