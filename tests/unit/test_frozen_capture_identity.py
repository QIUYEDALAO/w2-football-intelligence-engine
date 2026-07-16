from __future__ import annotations

from copy import deepcopy

from w2.models.fair_market_estimate import FairMarketEstimate, FairMarketEstimateSnapshot
from w2.tracking.frozen_capture_identity import (
    AUDIT_ESTIMATE_IDENTITY_MISMATCH,
    audit_capture_id,
    capture_estimate_identity,
)


def _snapshot(*, odds_line: float = 2.5) -> dict[str, object]:
    return FairMarketEstimateSnapshot.create(
        fixture_id="fixture-1",
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
        odds_snapshot={"ou": {"line": odds_line, "over_price": 1.9}},
        feature_snapshot={"home_xg": 1.5, "away_xg": 1.0},
        created_at="2026-07-17T00:00:00Z",
    ).as_dict()


def test_capture_identity_is_deterministic_and_time_specific() -> None:
    capture = {
        "fixture_id": "fixture-1",
        "football_day": "2026-07-17",
        "environment": "staging",
        "captured_at": "2026-07-17T00:00:00Z",
        "capture_hash": "same-content",
    }
    later = {**capture, "captured_at": "2026-07-17T00:01:00Z"}

    assert audit_capture_id(capture) == audit_capture_id(dict(reversed(list(capture.items()))))
    assert audit_capture_id(capture) != audit_capture_id(later)


def test_estimate_identity_requires_same_record_verified_v2_snapshot() -> None:
    snapshot = _snapshot()
    estimate_id = str(snapshot["estimate_id"])
    capture = {
        "pick": {"market": "TOTALS", "estimate_id": estimate_id},
        "fair_market_estimate_snapshots": [snapshot],
    }

    identity = capture_estimate_identity(capture)
    assert identity.status == "PASS"
    assert identity.estimate_id == estimate_id

    tampered = deepcopy(capture)
    tampered["fair_market_estimate_snapshots"][0]["fair_line"] = 9.0  # type: ignore[index]
    blocked = capture_estimate_identity(tampered)
    assert blocked.status == "BLOCKED"
    assert blocked.blocker == AUDIT_ESTIMATE_IDENTITY_MISMATCH


def test_non_pick_uses_top_level_or_analysis_gate_estimate_id() -> None:
    snapshot = _snapshot()
    estimate_id = str(snapshot["estimate_id"])

    top_level = capture_estimate_identity(
        {"estimate_id": estimate_id, "fair_market_estimate_snapshots": [snapshot]}
    )
    gate = capture_estimate_identity(
        {
            "analysis_gate": {"estimate_id": estimate_id},
            "fair_market_estimate_snapshots": [snapshot],
        }
    )

    assert top_level.estimate_id == estimate_id
    assert gate.estimate_id == estimate_id


def test_unique_eligible_snapshot_supplies_identity_and_multiple_fail_closed() -> None:
    first = _snapshot()
    second = _snapshot(odds_line=2.75)

    unique = capture_estimate_identity({"fair_market_estimate_snapshots": [first]})
    ambiguous = capture_estimate_identity(
        {"fair_market_estimate_snapshots": [first, second]}
    )

    assert unique.estimate_id == first["estimate_id"]
    assert unique.status == "PASS"
    assert ambiguous.status == "BLOCKED"
    assert ambiguous.estimate_id is None
