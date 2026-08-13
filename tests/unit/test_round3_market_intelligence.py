from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from w2.markets.round3_intelligence import (
    MODEL_LAB_STATUSES,
    MOVEMENT_STATUSES,
    _movement,
    build_round3_intelligence,
    eligible_observations,
)

AS_OF = datetime(2026, 8, 8, 8, 0, tzinfo=UTC)
KICKOFF = AS_OF + timedelta(hours=2)
FIXTURE_ID = "api_football:123"
COMPETITION_ID = "allsvenskan"


def _quote(
    *,
    capture: str,
    captured_at: datetime,
    bookmaker: str,
    market: str,
    selection: str,
    line: str,
    price: str,
) -> dict[str, Any]:
    return {
        "observation_id": f"{capture}:{bookmaker}:{market}:{selection}:{line}",
        "fixture_id": FIXTURE_ID,
        "provider_fixture_id": "123",
        "competition_id": COMPETITION_ID,
        "provider": "api_football",
        "bookmaker_id": bookmaker,
        "bookmaker_name": f"Book {bookmaker}",
        "capture_id": capture,
        "raw_market_label": "Asian Handicap" if market == "ASIAN_HANDICAP" else "Goals Over/Under",
        "canonical_market": market,
        "canonical_selection": selection,
        "line": line,
        "decimal_odds": price,
        "suspended": False,
        "live": False,
        "captured_at": captured_at,
        "raw_payload_sha256": f"raw-{capture}",
        "source_revision": "provider-capture-v1",
        "raw_storage_uri": f"raw://{capture}",
        "raw_lineage_present": True,
        "capture_lineage_present": True,
        "fixture_identity_present": True,
        "runtime_whitelist_member": True,
        "capture_identity_conflict": False,
        "identity_conflict": False,
    }


def _market_rows(
    *, capture: str, captured_at: datetime, ah_prices: tuple[str, str], ou_prices: tuple[str, str]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for bookmaker in ("1", "2", "3"):
        rows.extend(
            [
                _quote(
                    capture=capture,
                    captured_at=captured_at,
                    bookmaker=bookmaker,
                    market="ASIAN_HANDICAP",
                    selection="HOME",
                    line="-0.5",
                    price=ah_prices[0],
                ),
                _quote(
                    capture=capture,
                    captured_at=captured_at,
                    bookmaker=bookmaker,
                    market="ASIAN_HANDICAP",
                    selection="AWAY",
                    line="0.5",
                    price=ah_prices[1],
                ),
                _quote(
                    capture=capture,
                    captured_at=captured_at,
                    bookmaker=bookmaker,
                    market="TOTALS",
                    selection="OVER",
                    line="2.5",
                    price=ou_prices[0],
                ),
                _quote(
                    capture=capture,
                    captured_at=captured_at,
                    bookmaker=bookmaker,
                    market="TOTALS",
                    selection="UNDER",
                    line="2.5",
                    price=ou_prices[1],
                ),
            ]
        )
    return rows


def _simulation(*, calibration_status: str = "READY") -> dict[str, Any]:
    return {
        "status": "READY",
        "model_version": "model-v1",
        "calibration_version": "calibration-v1",
        "calibration_status": calibration_status,
        "lambda_home": 2.5,
        "lambda_away": 0.5,
        "lambda_sigma_home": 0.1,
        "lambda_sigma_away": 0.1,
    }


def _payload(rows: list[dict[str, Any]], simulation: dict[str, Any] | None = None):
    return build_round3_intelligence(
        rows,
        fixture_id="123",
        competition_id=COMPETITION_ID,
        kickoff_utc=KICKOFF,
        simulation=simulation or _simulation(),
        as_of=AS_OF,
    )


def test_real_same_line_timeline_builds_market_radar_and_movement() -> None:
    rows = _market_rows(
        capture="capture-1",
        captured_at=AS_OF - timedelta(minutes=30),
        ah_prices=("1.90", "1.96"),
        ou_prices=("1.92", "1.94"),
    )
    rows += _market_rows(
        capture="capture-2",
        captured_at=AS_OF - timedelta(minutes=10),
        ah_prices=("1.84", "2.02"),
        ou_prices=("1.88", "1.98"),
    )

    payload = _payload(rows)
    markets = payload["market_radar"]["markets"]

    assert markets["ASIAN_HANDICAP"]["snapshot_count"] == 2
    assert markets["TOTALS"]["snapshot_count"] == 2
    assert all(
        market["timeline"]["status"] == "MOVEMENT_COMPARISON_ELIGIBLE"
        and market["timeline"]["valid_snapshot_count"] == 2
        and len(market["timeline"]["points"]) == 2
        for market in markets.values()
    )
    assert markets["ASIAN_HANDICAP"]["movement"]["status"] == "PRICE_MOVEMENT"
    assert markets["TOTALS"]["movement"]["status"] == "PRICE_MOVEMENT"
    assert markets["TOTALS"]["current"]["bookmaker_count"] == 3
    assert markets["TOTALS"]["current"]["lineage"]["capture_ids"] == ["capture-2"]
    assert markets["TOTALS"]["movement"]["status"] in MOVEMENT_STATUSES


def test_ah_depth_reuses_canonical_pairs_when_provider_exposes_mirrored_lines() -> None:
    captured_at = AS_OF - timedelta(minutes=10)
    rows: list[dict[str, Any]] = []
    for index in range(1, 12):
        bookmaker = str(index)
        if index <= 7:
            rows.extend(
                [
                    _quote(
                        capture="capture-1",
                        captured_at=captured_at,
                        bookmaker=bookmaker,
                        market="ASIAN_HANDICAP",
                        selection=side,
                        line=line,
                        price=price,
                    )
                    for side, line, price in (
                        ("HOME", "-0.25", "1.80"),
                        ("AWAY", "-0.25", "2.00"),
                        ("HOME", "0.25", "1.35"),
                        ("AWAY", "0.25", "2.90"),
                    )
                ]
            )
        rows.extend(
            [
                _quote(
                    capture="capture-1",
                    captured_at=captured_at,
                    bookmaker=bookmaker,
                    market="TOTALS",
                    selection=side,
                    line="2.5",
                    price=price,
                )
                for side, price in (("OVER", "1.94"), ("UNDER", "1.80"))
            ]
        )

    markets = _payload(rows)["market_radar"]["markets"]

    assert markets["ASIAN_HANDICAP"]["current"]["canonical_line"] == "-0.25"
    assert markets["ASIAN_HANDICAP"]["current"]["bookmaker_count"] == 7
    assert markets["TOTALS"]["current"]["canonical_line"] == "2.5"
    assert markets["TOTALS"]["current"]["bookmaker_count"] == 11


@pytest.mark.parametrize(
    ("before_line", "after_line", "before_price", "after_price", "expected"),
    [
        ("-0.5", "-0.5", 1.9, 1.9, "STABLE"),
        ("-0.5", "-0.5", 1.9, 1.91, "PRICE_MOVEMENT"),
        ("-0.5", "-0.25", 1.9, 1.9, "LINE_MOVEMENT"),
        ("-0.5", "-0.25", 1.9, 1.91, "LINE_AND_PRICE_MOVEMENT"),
    ],
)
def test_movement_contract_uses_only_line_and_side_price_medians(
    before_line: str,
    after_line: str,
    before_price: float,
    after_price: float,
    expected: str,
) -> None:
    previous = {
        "captured_at": "2026-08-02T16:03:23Z",
        "canonical_line": before_line,
        "bookmaker_count": 4,
        "prices": {"HOME": {"median": before_price}, "AWAY": {"median": 1.95}},
        "probabilities": {"HOME": {"median": 0.5}, "AWAY": {"median": 0.5}},
    }
    current = deepcopy(previous)
    current.update(
        captured_at="2026-08-03T06:53:58Z",
        canonical_line=after_line,
        bookmaker_count=5,
    )
    current["prices"]["HOME"]["median"] = after_price

    movement = _movement(previous, current)

    assert movement["status"] == expected


def test_one_snapshot_is_explicitly_insufficient_for_movement() -> None:
    payload = _payload(
        _market_rows(
            capture="capture-1",
            captured_at=AS_OF - timedelta(minutes=10),
            ah_prices=("1.90", "1.96"),
            ou_prices=("1.92", "1.94"),
        )
    )

    for market in payload["market_radar"]["markets"].values():
        assert market["movement"]["status"] == "INSUFFICIENT"
        assert market["movement"]["reason_code"] == "INSUFFICIENT_SINGLE_SNAPSHOT"
        assert market["timeline"]["status"] == "INSUFFICIENT_SINGLE_SNAPSHOT"
        assert len(market["timeline"]["points"]) == 1


def test_zero_snapshot_timeline_has_no_fabricated_points_for_ah_or_ou() -> None:
    payload = _payload([])

    for market in payload["market_radar"]["markets"].values():
        assert market["movement"]["reason_code"] == "INSUFFICIENT_NO_TIMELINE_EVIDENCE"
        assert market["timeline"] == {
            "status": "INSUFFICIENT_NO_TIMELINE_EVIDENCE",
            "valid_snapshot_count": 0,
            "distinct_captured_at_count": 0,
            "earliest_captured_at": None,
            "latest_captured_at": None,
            "same_line_comparable_snapshot_count": 0,
            "raw_payload_lineage_complete": False,
            "endpoint_capture_lineage_complete": False,
            "points": [],
        }


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"synthetic": True}, "SYNTHETIC_EVIDENCE"),
        ({"raw_lineage_present": False}, "RAW_PAYLOAD_MISSING"),
        ({"capture_lineage_present": False}, "ENDPOINT_CAPTURE_MISSING"),
        ({"fixture_identity_present": False}, "FIXTURE_IDENTITY_MISSING"),
        ({"runtime_whitelist_member": False}, "OUT_OF_RUNTIME_WHITELIST"),
        ({"canonical_market": "1X2"}, "UNSUPPORTED_MARKET"),
        ({"line": "bad"}, "INVALID_LINE"),
        ({"decimal_odds": "1"}, "INVALID_PRICE"),
        ({"identity_conflict": True}, "IDENTITY_CONFLICT"),
        ({"live": True}, "LIVE_OR_SUSPENDED"),
        ({"captured_at": KICKOFF}, "POST_KICKOFF_OBSERVATION"),
    ],
)
def test_evidence_contract_rejects_with_explicit_reason(
    change: dict[str, Any], reason: str
) -> None:
    row = _quote(
        capture="capture-1",
        captured_at=AS_OF,
        bookmaker="1",
        market="TOTALS",
        selection="OVER",
        line="2.5",
        price="1.90",
    )
    row.update(change)

    accepted, rejected = eligible_observations(
        [row],
        fixture_id=FIXTURE_ID,
        competition_id=COMPETITION_ID,
        kickoff_utc=KICKOFF,
    )

    assert accepted == []
    assert rejected == {reason: 1}


def test_conflicting_duplicate_observation_is_rejected_without_coercion() -> None:
    row = _quote(
        capture="capture-1",
        captured_at=AS_OF,
        bookmaker="1",
        market="TOTALS",
        selection="OVER",
        line="2.5",
        price="1.90",
    )
    conflict = deepcopy(row)
    conflict["decimal_odds"] = "2.10"

    accepted, rejected = eligible_observations(
        [row, conflict],
        fixture_id=FIXTURE_ID,
        competition_id=COMPETITION_ID,
        kickoff_utc=KICKOFF,
    )

    assert accepted == []
    assert rejected == {"DUPLICATE_CONFLICTING_OBSERVATION": 2}


def test_model_lab_requires_ready_calibration_and_three_books() -> None:
    rows = _market_rows(
        capture="capture-1",
        captured_at=AS_OF - timedelta(minutes=10),
        ah_prices=("1.90", "1.96"),
        ou_prices=("1.92", "1.94"),
    )
    not_calibrated = _payload(rows, _simulation(calibration_status="BASELINE_PRIOR"))
    for market in not_calibrated["model_lab"]["markets"].values():
        assert market["status"] == "MODEL_NOT_READY"
        assert market["status"] in MODEL_LAB_STATUSES

    two_books = [row for row in rows if row["bookmaker_id"] != "3"]
    shallow = _payload(two_books)
    for market in shallow["model_lab"]["markets"].values():
        assert market["status"] == "INSUFFICIENT_BOOKMAKER_DEPTH"


def test_model_disagreement_requires_probability_outside_real_range() -> None:
    rows = _market_rows(
        capture="capture-1",
        captured_at=AS_OF - timedelta(minutes=10),
        ah_prices=("1.90", "1.96"),
        ou_prices=("1.92", "1.94"),
    )

    payload = _payload(rows)

    assert any(
        market["status"] == "MODEL_OUTSIDE_MARKET_RANGE"
        for market in payload["model_lab"]["markets"].values()
    )
    outside = next(
        market
        for market in payload["model_lab"]["markets"].values()
        if market["status"] == "MODEL_OUTSIDE_MARKET_RANGE"
    )
    assert any(row["distance_outside_market_range"] != 0 for row in outside["diagnostics"])


def test_round3_payload_isolated_from_legacy_action_semantics() -> None:
    payload = _payload(
        _market_rows(
            capture="capture-1",
            captured_at=AS_OF - timedelta(minutes=10),
            ah_prices=("1.90", "1.96"),
            ou_prices=("1.92", "1.94"),
        )
    )
    forbidden = {
        "expected_value",
        "ev_eligible",
        "formal_eligible",
        "lock_eligible",
        "cashflow_price_edge",
        "analysis_direction_allowed",
        "MODEL_MARKET_EDGE_READY",
        "MODEL_MARKET_EDGE_INSUFFICIENT",
        "MIN_MARKET_ANCHOR_DIVERGENCE",
    }

    def keys(value: Any) -> set[str]:
        if isinstance(value, dict):
            return set(value) | set().union(*(keys(item) for item in value.values()))
        if isinstance(value, list):
            return set().union(*(keys(item) for item in value))
        return set()

    assert keys(payload).isdisjoint(forbidden)
    assert payload["market_radar"]["statistical_anomaly"] == {
        "calibration_status": "NOT_CALIBRATED",
        "detected": False,
    }
    assert payload["model_lab"]["historical_validation"] == {
        "protocol": "W2_PHASE_0_5_AH_OU_EDGE_EXISTENCE_PROTOCOL_V1_RC3",
        "final_verdict": "NO_EDGE",
        "v_continuation_gate": "FAIL",
        "ou_close_best_predictive_lift": -0.0000758,
        "ah_close_best_predictive_lift": -0.0006467,
        "ou_pre_best_frozen_selections": 7566,
        "ou_pre_best_frozen_strategy_roi": "-5.32%",
        "historical_incremental_edge": "NOT_PROVEN",
        "h_result_access": "PERMANENTLY_CLOSED",
        "reexecuted": False,
    }
