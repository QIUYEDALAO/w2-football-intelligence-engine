from __future__ import annotations

import json
from pathlib import Path

from w2.models.fair_market_estimate import FairMarketEstimate, FairMarketEstimateSnapshot
from w2.tracking.day_view_capture_index import (
    MAX_DAY_VIEW_CAPTURE_SUMMARY_BYTES,
    build_day_view_capture_index,
    clear_day_view_capture_index_cache,
)


def _write(root: Path, rows: list[dict[str, object]]) -> None:
    ledger = root / "forward_outcome_ledger"
    ledger.mkdir()
    (ledger / "records.jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8"
    )


def test_index_exposes_same_record_capture_hash_and_estimate_identity(tmp_path: Path) -> None:
    snapshot = FairMarketEstimateSnapshot.create(
        fixture_id="7",
        estimate=FairMarketEstimate(
            market="TOTALS",
            status="READY",
            model_family="R4_1_CALIBRATED",
            fair_line=2.5,
            probabilities={"OVER": 0.52, "UNDER": 0.48},
            home_mu=1.5,
            away_mu=1.0,
            feature_as_of="2026-07-17T00:00:00Z",
            train_cutoff="2026-06-30T00:00:00Z",
            artifact_hash="artifact",
            artifact_version="v1",
        ),
        odds_snapshot={"ou": {"line": 2.5, "over_price": 1.9}},
        feature_snapshot={"home_xg": 1.5, "away_xg": 1.0},
        created_at="2026-07-17T00:00:00Z",
    ).as_dict()
    capture = {
        "fixture_id": "7",
        "football_day": "2026-07-17",
        "environment": "staging",
        "captured_at": "2026-07-17T00:00:00Z",
        "kickoff_utc": "2026-07-17T12:00:00Z",
        "capture_hash": "content-hash",
        "pick": {"market": "TOTALS", "estimate_id": snapshot["estimate_id"]},
        "fair_market_estimate_ids": [snapshot["estimate_id"]],
        "fair_market_estimate_snapshots": [snapshot],
    }
    _write(tmp_path, [capture])

    card = build_day_view_capture_index(tmp_path).summaries["7"].as_card_fields()

    assert card["audit_capture_id"].startswith("aci_")
    assert card["audit_capture_hash"] == "content-hash"
    assert card["audit_estimate_id"] == snapshot["estimate_id"]
    assert card["audit_identity_status"] == "PASS"
    assert card["audit_available"] is True


def test_index_keeps_latest_prematch_capture_and_omits_full_payloads(tmp_path: Path) -> None:
    base = {
        "fixture_id": "7",
        "kickoff_utc": "2026-07-16T12:00:00Z",
        "decision_tier": "ANALYSIS_PICK",
        "data_status": "READY",
        "pick": {"market": "TOTALS", "selection": "OVER", "estimate_id": "fme-1"},
        "fair_market_estimate_snapshots": [
            {"estimate_id": "fme-1", "market": "TOTALS", "score_matrix": [[1] * 50] * 50}
        ],
        "pricing_shadow": {"huge": "x" * 10000},
        "raw_provider_payload": {"sensitive": "omitted"},
    }
    _write(
        tmp_path,
        [
            {**base, "captured_at": "2026-07-16T09:00:00Z", "capture_hash": "old"},
            {**base, "captured_at": "2026-07-16T10:00:00Z", "capture_hash": "new"},
            {**base, "captured_at": "2026-07-16T13:00:00Z", "capture_hash": "live"},
        ],
    )
    clear_day_view_capture_index_cache()
    result = build_day_view_capture_index(tmp_path)
    card = result.summaries["7"].as_card_fields()
    encoded = json.dumps(card).encode()
    assert card["audit_capture_hash"] == "new"
    assert len(encoded) <= MAX_DAY_VIEW_CAPTURE_SUMMARY_BYTES
    for forbidden in (
        "fair_market_estimate_snapshots",
        "score_matrix",
        "pricing_shadow",
        "raw_provider_payload",
    ):
        assert forbidden not in encoded.decode()


def test_corrupt_tail_is_degraded_and_oversized_line_fails_closed(tmp_path: Path) -> None:
    ledger = tmp_path / "forward_outcome_ledger"
    ledger.mkdir()
    path = ledger / "records.jsonl"
    path.write_text(
        '{"fixture_id":"1","captured_at":"2026-07-16T09:00:00Z","capture_hash":"x"}\n{',
        encoding="utf-8",
    )
    clear_day_view_capture_index_cache()
    assert build_day_view_capture_index(tmp_path).source_status == "DEGRADED"
    clear_day_view_capture_index_cache()
    assert build_day_view_capture_index(tmp_path, max_line_bytes=3).source_status == "BLOCKED"
