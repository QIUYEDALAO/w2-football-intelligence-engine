from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from w2.audit.frozen_fixture_audit import (
    FROZEN_AUDIT_SCHEMA_VERSION,
    MAX_AUDIT_RESPONSE_BYTES,
    build_frozen_fixture_audit,
)
from w2.models.fair_market_estimate import FairMarketEstimate, FairMarketEstimateSnapshot
from w2.tracking.frozen_capture_lookup import find_frozen_capture


def _snapshot() -> dict[str, object]:
    return FairMarketEstimateSnapshot.create(
        fixture_id="fixture-1",
        estimate=FairMarketEstimate(
            market="TOTALS",
            status="READY",
            model_family="R4_1_CALIBRATED",
            fair_line=2.5,
            probabilities={"OVER": 0.5, "UNDER": 0.5},
            home_mu=1.6,
            away_mu=1.1,
            feature_as_of="2026-07-01T00:00:00Z",
            train_cutoff="2026-06-30T00:00:00Z",
            artifact_hash="artifact",
            artifact_version="r4.1",
        ),
        odds_snapshot={"ou": {"line": 2.5, "over_price": 1.9}},
        feature_snapshot={"large_history_blob": ["must-not-leak"], "home_xg": 1.6},
        created_at="2026-07-01T00:00:00Z",
    ).as_dict()


def _capture(snapshot: dict[str, object]) -> dict[str, object]:
    estimate_id = str(snapshot["estimate_id"])
    return {
        "fixture_id": "fixture-1",
        "capture_hash": "capture-1",
        "captured_at": "2026-07-01T01:00:00Z",
        "kickoff_utc": "2026-07-01T10:00:00Z",
        "decision_tier": "ANALYSIS_PICK",
        "data_status": "READY",
        "reason_code": "PASS",
        "action": "TRACK",
        "outcome_tracked": True,
        "lock_eligible": False,
        "pick": {
            "market": "TOTALS",
            "selection": "OVER",
            "line": 2.5,
            "estimate_id": estimate_id,
        },
        "fair_market_estimate_ids": [estimate_id],
        "fair_market_estimate_snapshots": [snapshot],
        "analysis_gate": {"status": "PASS", "estimate_id": estimate_id},
    }


def _lookup(tmp_path: Path, capture: dict[str, object]):
    ledger = tmp_path / "forward_outcome_ledger"
    ledger.mkdir()
    (ledger / "ledger.jsonl").write_text(json.dumps(capture) + "\n", encoding="utf-8")
    return find_frozen_capture(
        tmp_path,
        fixture_id="fixture-1",
        capture_hash="capture-1",
        estimate_id=str(capture["fair_market_estimate_ids"][0]),  # type: ignore[index]
    )


def test_v2_projection_is_bounded_and_derived_only_from_frozen_snapshot(tmp_path: Path) -> None:
    snapshot = _snapshot()
    audit = build_frozen_fixture_audit(
        _lookup(tmp_path, _capture(snapshot)),
        requested_estimate_id=str(snapshot["estimate_id"]),
    )
    encoded = json.dumps(audit).encode()

    assert audit["schema_version"] == FROZEN_AUDIT_SCHEMA_VERSION
    assert audit["source"] == "FROZEN_FORWARD_CAPTURE"
    assert audit["source_capture_hash"] == "capture-1"
    assert audit["corrected_evidence"] is True
    assert audit["historical_compatibility"] is False
    assert len(audit["estimate_summaries"]) == 1
    assert len(audit["estimate_summaries"][0]["score_matrix"]) == 169
    assert len(audit["scoreline_explanation"]["global_scorelines"]) <= 10
    assert len(audit["scoreline_explanation"]["direction_scorelines"]) <= 10
    assert len(encoded) <= MAX_AUDIT_RESPONSE_BYTES
    assert "large_history_blob" not in encoded.decode()
    assert ("raw_provider_" + "payload") not in encoded.decode()


def test_projection_caps_estimates_at_two(tmp_path: Path) -> None:
    snapshots = [_snapshot() for _ in range(3)]
    for index, snapshot in enumerate(snapshots):
        snapshot["estimate_id"] = f"invalid-{index}"
    capture = _capture(_snapshot())
    capture["fair_market_estimate_snapshots"] = snapshots
    capture["fair_market_estimate_ids"] = [item["estimate_id"] for item in snapshots]
    capture["pick"]["estimate_id"] = snapshots[0]["estimate_id"]  # type: ignore[index]

    audit = build_frozen_fixture_audit(
        _lookup(tmp_path, capture), requested_estimate_id=str(snapshots[0]["estimate_id"])
    )

    assert len(audit["estimate_summaries"]) == 2
    assert "ESTIMATE_LIMIT_APPLIED" in audit["omitted_sections"]


def test_invalid_snapshot_is_visible_without_probability_derivation(tmp_path: Path) -> None:
    snapshot = deepcopy(_snapshot())
    snapshot["score_matrix"]["1-1"] = 0.99  # type: ignore[index]
    audit = build_frozen_fixture_audit(
        _lookup(tmp_path, _capture(snapshot)),
        requested_estimate_id=str(snapshot["estimate_id"]),
    )

    assert audit["source_status"] == "BLOCKED"
    assert audit["integrity"]["status"] == "BLOCKED"
    assert audit["estimate_summaries"][0]["score_matrix"] == []
    assert audit["scoreline_explanation"]["global_scorelines"] == []
    assert audit["settlement_distribution"] == {}


def test_legacy_oom_fixture_is_audit_visible_but_not_corrected() -> None:
    fixture_root = Path(__file__).parents[1] / "fixtures" / "frozen_audit"
    lookup = find_frozen_capture(
        fixture_root,
        fixture_id="1576804",
        capture_hash="0ceebd3db9a826d72cdafef626d64f54f7fdd837cca528a29188b3c1e93457bc",
    )

    audit = build_frozen_fixture_audit(lookup, requested_estimate_id=None)

    assert audit["historical_compatibility"] is True
    assert audit["corrected_evidence"] is False
    assert audit["decision"]["decision_tier"] == "ANALYSIS_PICK"
    assert audit["audit_outcome_summary"]["raw_outcome_count"] == 3
    assert audit["strict_gate"] == {}


def test_projection_over_limit_fails_closed(tmp_path: Path, monkeypatch) -> None:
    from w2.audit import frozen_fixture_audit

    snapshot = _snapshot()
    monkeypatch.setattr(frozen_fixture_audit, "MAX_AUDIT_RESPONSE_BYTES", 128)
    audit = build_frozen_fixture_audit(
        _lookup(tmp_path, _capture(snapshot)), requested_estimate_id=str(snapshot["estimate_id"])
    )

    assert audit["source_status"] == "BLOCKED"
    assert audit["integrity"]["reason"] == "AUDIT_PROJECTION_TOO_LARGE"
