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


def test_non_pinnacle_is_refused() -> None:
    raw = _raw()
    rows = _obs(raw)
    for row in rows[:2]:
        row["bookmaker_id"] = "8"
    result = select_v3_ah_ou_quotes(
        rows, fixture_id=FIXTURE_ID, decision_at=DECISION_AT,
        raw_payloads={CAPTURE_ID: raw},
    )
    assert result["ah"]["status"] == "ASIAN_HANDICAP_QUOTE_NOT_PINNACLE"


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


def test_ah_away_repeated_home_perspective_line_is_accepted() -> None:
    # AH 线语义：away 侧也可以是 home 视角同线（重复 L），canonical 仍是 home 视角 L
    raw = _raw(ah=[("Home -0.5", "1.80"), ("Away -0.5", "2.05")])
    rows = _obs(raw)
    rows[1]["line"] = "-0.5"  # away 重复 home 视角同线
    result = select_v3_ah_ou_quotes(
        rows, fixture_id=FIXTURE_ID, decision_at=DECISION_AT,
        raw_payloads={CAPTURE_ID: raw},
    )
    assert result["ah"]["status"] == "READY"
    assert result["ah"]["quote"]["line"] == __import__("decimal").Decimal("-0.5")
