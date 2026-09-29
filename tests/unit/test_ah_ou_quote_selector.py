"""v3 同源双侧盘口选择器单测（S2）。"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from w2.domain.canonical_serialization import (
    HashDomain,
    SerializerVersion,
    canonical_sha256,
)
from w2.strategy.ah_ou_quote_selector import select_v3_ah_ou_quotes

FIXTURE_ID = "FIX1"
DECISION_AT = datetime(2026, 8, 1, 10, 0, tzinfo=UTC)
CAPTURE_ID = "cap-1"
RAW_PAYLOAD = {
    "response": [
        {
            "fixture": {"id": FIXTURE_ID},
            "bookmakers": [
                {
                    "id": 4,
                    "name": "Pinnacle",
                    "bets": [
                        {
                            "id": 1,
                            "name": "Asian Handicap",
                            "values": [
                                {"value": "Home -0.5", "odd": "1.80"},
                                {"value": "Away +0.5", "odd": "2.05"},
                            ],
                        },
                        {
                            "id": 2,
                            "name": "Goals Over/Under",
                            "values": [
                                {"value": "Over 2.5", "odd": "1.90"},
                                {"value": "Under 2.5", "odd": "1.90"},
                            ],
                        },
                    ],
                }
            ],
        }
    ]
}
RAW_PAYLOADS = {CAPTURE_ID: RAW_PAYLOAD}
LEGACY_RAW_HASH = canonical_sha256(
    RAW_PAYLOAD,
    domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD,
    version=SerializerVersion.LEGACY_V1,
)


def _row(*, market, selection, line, odds, capture_id=CAPTURE_ID, **overrides) -> dict:
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
        "raw_payload_sha256": LEGACY_RAW_HASH,
    }
    row.update(overrides)
    return row


def _observations() -> list[dict]:
    return [
        _row(market="ASIAN_HANDICAP", selection="HOME", line="-0.5", odds="1.80"),
        _row(market="ASIAN_HANDICAP", selection="AWAY", line="0.5", odds="2.05"),
        _row(market="TOTALS", selection="OVER", line="2.5", odds="1.90"),
        _row(market="TOTALS", selection="UNDER", line="2.5", odds="1.90"),
    ]


def test_same_capture_two_sided_quotes_ready() -> None:
    result = select_v3_ah_ou_quotes(
        _observations(),
        fixture_id=FIXTURE_ID,
        decision_at=DECISION_AT,
        raw_payloads=RAW_PAYLOADS,
    )
    assert result["status"] == "READY"
    ah = result["ah"]["quote"]
    ou = result["ou"]["quote"]
    assert ah["side_prices"] == {"home": 1.80, "away": 2.05}
    assert ou["side_prices"] == {"over": 1.90, "under": 1.90}
    assert ah["capture_id"] == CAPTURE_ID == ou["capture_id"]
    # source_capture_sha256 是 canonical hash 域，非 hex64、非空
    expected = canonical_sha256(RAW_PAYLOAD, domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD)
    assert ah["source_capture_sha256"] == expected
    assert ou["source_capture_sha256"] == expected


def test_non_pinnacle_is_refused() -> None:
    rows = _observations()
    for row in rows[:2]:  # AH 两侧都非 Pinnacle
        row["bookmaker_id"] = "8"
    result = select_v3_ah_ou_quotes(rows, fixture_id=FIXTURE_ID, decision_at=DECISION_AT,
                                     raw_payloads=RAW_PAYLOADS)
    assert result["ah"]["status"] == "ASIAN_HANDICAP_QUOTE_NOT_PINNACLE"


def test_live_is_refused() -> None:
    rows = _observations()
    for row in rows[:2]:  # AH 两侧都 live
        row["live"] = True
    result = select_v3_ah_ou_quotes(rows, fixture_id=FIXTURE_ID, decision_at=DECISION_AT,
                                     raw_payloads=RAW_PAYLOADS)
    assert result["ah"]["status"] == "ASIAN_HANDICAP_QUOTE_LIVE_OR_SUSPENDED"


def test_captured_after_decision_is_refused() -> None:
    rows = _observations()
    for row in rows[:2]:  # AH 两侧都晚于 decision_at
        row["captured_at"] = (DECISION_AT + timedelta(minutes=5)).isoformat()
    result = select_v3_ah_ou_quotes(rows, fixture_id=FIXTURE_ID, decision_at=DECISION_AT,
                                     raw_payloads=RAW_PAYLOADS)
    assert result["ah"]["status"] == "ASIAN_HANDICAP_QUOTE_CAPTURED_AFTER_DECISION"


def test_different_capture_is_refused() -> None:
    rows = _observations()
    rows[1]["capture_id"] = "cap-2"
    result = select_v3_ah_ou_quotes(rows, fixture_id=FIXTURE_ID, decision_at=DECISION_AT,
                                     raw_payloads=RAW_PAYLOADS)
    assert result["ah"]["status"] == "ASIAN_HANDICAP_QUOTE_NOT_SAME_CAPTURE"


def test_missing_side_is_refused() -> None:
    rows = _observations()
    rows.pop(1)  # 缺 AWAY 侧
    result = select_v3_ah_ou_quotes(rows, fixture_id=FIXTURE_ID, decision_at=DECISION_AT,
                                     raw_payloads=RAW_PAYLOADS)
    assert result["ah"]["status"] == "ASIAN_HANDICAP_QUOTE_SIDE_INCOMPLETE"


def test_missing_source_capture_hash_is_refused() -> None:
    result = select_v3_ah_ou_quotes(
        _observations(), fixture_id=FIXTURE_ID, decision_at=DECISION_AT, raw_payloads=None
    )
    assert result["ah"]["status"] == "ASIAN_HANDICAP_SOURCE_CAPTURE_HASH_MISSING"


def test_fixture_mismatch_is_refused() -> None:
    rows = _observations()
    rows[1]["fixture_id"] = "OTHER"
    result = select_v3_ah_ou_quotes(rows, fixture_id=FIXTURE_ID, decision_at=DECISION_AT,
                                     raw_payloads=RAW_PAYLOADS)
    # 该行被 canonical fixture 筛掉 → 缺一侧
    assert result["ah"]["status"] == "ASIAN_HANDICAP_QUOTE_SIDE_INCOMPLETE"


def test_non_finite_price_is_refused() -> None:
    rows = _observations()
    rows[0]["decimal_odds"] = "nan"
    result = select_v3_ah_ou_quotes(rows, fixture_id=FIXTURE_ID, decision_at=DECISION_AT,
                                     raw_payloads=RAW_PAYLOADS)
    assert result["ah"]["status"] == "ASIAN_HANDICAP_QUOTE_PRICE_INVALID"
