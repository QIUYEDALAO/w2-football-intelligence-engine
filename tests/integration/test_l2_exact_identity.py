from __future__ import annotations

import json
import shutil
from pathlib import Path

from w2.audit.frozen_fixture_audit import build_frozen_fixture_audit
from w2.models.fair_market_estimate import FairMarketEstimate, FairMarketEstimateSnapshot
from w2.tracking.frozen_capture_identity import audit_capture_id
from w2.tracking.frozen_capture_lookup import find_frozen_capture


def _controlled_recapture() -> dict[str, object]:
    captured_at = "2026-07-17T01:00:00Z"
    snapshot = FairMarketEstimateSnapshot.create(
        fixture_id="1492140",
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
            artifact_hash="sanitized-artifact",
            artifact_version="test-v1",
        ),
        odds_snapshot={"ou": {"line": 2.5, "over_price": 1.9}},
        feature_snapshot={"home_xg": 1.5, "away_xg": 1.0},
        created_at=captured_at,
    ).as_dict()
    return {
        "fixture_id": "1492140",
        "football_day": "2026-07-17",
        "environment": "staging",
        "captured_at": captured_at,
        "capture_checkpoint": "CONTROLLED_CURRENT_CAPTURE",
        "record_type": "capture",
        "capture_hash": "sanitized-controlled-content",
        "decision_tier": "WATCH",
        "data_status": "READY",
        "pick": {"market": "TOTALS", "estimate_id": snapshot["estimate_id"]},
        "fair_market_estimate_ids": [snapshot["estimate_id"]],
        "fair_market_estimate_snapshots": [snapshot],
    }


def test_fixture_1492140_regression_resolves_exact_v2_identity(tmp_path: Path) -> None:
    source = (
        Path(__file__).parents[1]
        / "fixtures"
        / "frozen_audit"
        / "fixture_1492140_exact_identity_regression.jsonl"
    )
    ledger = tmp_path / "forward_outcome_ledger"
    ledger.mkdir()
    target = ledger / "records.jsonl"
    shutil.copyfile(source, target)
    recapture = _controlled_recapture()
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(recapture) + "\n")
    capture_id = audit_capture_id(recapture)
    estimate_id = str(recapture["fair_market_estimate_ids"][0])  # type: ignore[index]

    lookup = find_frozen_capture(
        tmp_path,
        fixture_id="1492140",
        capture_id=capture_id,
        capture_hash="sanitized-controlled-content",
        estimate_id=estimate_id,
    )
    audit = build_frozen_fixture_audit(lookup, requested_estimate_id=estimate_id)

    assert lookup.source_status == "PASS"
    assert audit["source_capture_id"] == capture_id
    assert audit["source_capture_hash"] == "sanitized-controlled-content"
    assert audit["source_estimate_id"] == estimate_id
    assert audit["corrected_evidence"] is True
    assert audit["integrity"]["status"] == "PASS"
