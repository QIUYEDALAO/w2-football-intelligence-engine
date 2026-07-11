from __future__ import annotations

from copy import deepcopy

import pytest

from w2.dashboard.scorelines import scoreline_reference_from_card
from w2.models.fair_market_estimate import (
    FairMarketEstimate,
    FairMarketEstimateSnapshot,
    estimate_snapshot_by_id,
    verify_estimate_snapshot,
)


def _estimate(
    *, fair_line: float = 2.75, fallback_reason: str | None = None
) -> FairMarketEstimate:
    return FairMarketEstimate(
        market="TOTALS",
        status="READY",
        model_family="R4_1_CALIBRATED",
        fair_line=fair_line,
        probabilities={"OVER": 0.52, "UNDER": 0.48},
        home_mu=1.6,
        away_mu=1.1,
        feature_as_of="2026-07-12T00:00:00Z",
        train_cutoff="2026-06-30T00:00:00Z",
        artifact_hash="artifact-hash",
        artifact_version="r4.1",
        fallback_reason=fallback_reason,
    )


def _snapshot(
    *,
    fair_line: float = 2.75,
    odds_snapshot: dict[str, object] | None = None,
    created_at: str = "2026-07-12T00:00:00Z",
    fallback_reason: str | None = None,
) -> dict[str, object]:
    return FairMarketEstimateSnapshot.create(
        fixture_id="fixture-1",
        estimate=_estimate(fair_line=fair_line, fallback_reason=fallback_reason),
        odds_snapshot=odds_snapshot or {"ou": {"line": 2.5, "over_price": 1.95}},
        feature_snapshot={"home_xg": 1.6, "away_xg": 1.1},
        created_at=created_at,
    ).as_dict()


def test_estimate_id_is_deterministic_and_excludes_capture_time() -> None:
    first = _snapshot(created_at="2026-07-12T00:00:00Z")
    second = _snapshot(created_at="2026-07-12T00:01:00Z")

    assert first["estimate_id"] == second["estimate_id"]
    assert first["estimate_hash"] == second["estimate_hash"]
    assert first["created_at"] != second["created_at"]
    assert verify_estimate_snapshot(first)
    assert verify_estimate_snapshot(second)


def test_estimate_id_changes_with_input_or_output() -> None:
    baseline = _snapshot()
    changed_input = _snapshot(
        odds_snapshot={"ou": {"line": 2.75, "over_price": 1.95}}
    )
    changed_output = _snapshot(fair_line=3.0)
    changed_diagnostic = _snapshot(fallback_reason="R4_1_FEATURE_HISTORY_INSUFFICIENT")

    assert len(
        {
            baseline["estimate_id"],
            changed_input["estimate_id"],
            changed_output["estimate_id"],
            changed_diagnostic["estimate_id"],
        }
    ) == 4


def test_fallback_reason_is_integrity_protected() -> None:
    snapshot = _snapshot(fallback_reason="R4_1_FEATURE_HISTORY_INSUFFICIENT")
    assert verify_estimate_snapshot(snapshot)

    tampered = deepcopy(snapshot)
    tampered["fallback_reason"] = "OTHER_REASON"
    assert verify_estimate_snapshot(tampered) is False


def test_snapshot_without_fallback_reason_keeps_legacy_hash_compatibility() -> None:
    snapshot = _snapshot()
    legacy = deepcopy(snapshot)
    legacy.pop("fallback_reason")
    from w2.models.fair_market_estimate import canonical_estimate_hash

    payload = {
        key: legacy[key]
        for key in (
            "fixture_id",
            "market",
            "status",
            "fair_line",
            "probabilities",
            "home_mu",
            "away_mu",
            "score_matrix",
            "input_context",
            "model_context",
        )
    }
    estimate_hash = canonical_estimate_hash(payload)
    legacy["estimate_id"] = f"fme_{estimate_hash}"
    legacy["estimate_hash"] = estimate_hash
    legacy["integrity"]["estimate_hash"] = estimate_hash  # type: ignore[index]

    assert verify_estimate_snapshot(legacy)


def test_snapshot_integrity_detects_tampering_and_resolves_only_by_id() -> None:
    snapshot = _snapshot()
    card = {
        "fair_market_estimate_ids": [snapshot["estimate_id"]],
        "fair_market_estimate_snapshots": [snapshot],
    }

    assert estimate_snapshot_by_id(card, snapshot["estimate_id"]) == snapshot
    assert estimate_snapshot_by_id(card, "fme_missing") is None

    tampered = deepcopy(snapshot)
    tampered["fair_line"] = 4.0
    assert verify_estimate_snapshot(tampered) is False

    tampered_compatibility = deepcopy(snapshot)
    tampered_compatibility["artifact_hash"] = "other-artifact"
    assert verify_estimate_snapshot(tampered_compatibility) is False

    tampered_input = deepcopy(snapshot)
    tampered_input["input_context"]["odds_snapshot"]["ou"]["line"] = 4.0  # type: ignore[index]
    assert verify_estimate_snapshot(tampered_input) is False

    tampered_matrix = deepcopy(snapshot)
    tampered_matrix["score_matrix"]["1-1"] = 0.99  # type: ignore[index]
    assert verify_estimate_snapshot(tampered_matrix) is False


def test_runtime_fingerprint_is_not_part_of_estimate_entity() -> None:
    snapshot = _snapshot()

    assert "release_sha" not in snapshot
    assert "runtime_image" not in snapshot
    assert "dependency_hash" not in snapshot
    assert "runtime_fingerprint" not in snapshot


def test_one_estimate_id_drives_fair_line_scorelines_and_settlement() -> None:
    snapshot = _snapshot()
    estimate_id = snapshot["estimate_id"]
    card = {
        "decision_tier": "ANALYSIS_PICK",
        "fair_market_estimate_ids": [estimate_id],
        "fair_market_estimate_snapshots": [snapshot],
        "decision_contract": {
            "pick": {
                "market": "TOTALS",
                "selection": "OVER",
                "line": 2.5,
                "estimate_id": estimate_id,
            }
        },
    }

    reference = scoreline_reference_from_card(card)

    assert reference is not None
    assert reference["estimate_id"] == estimate_id
    assert reference["market_settlement"]["estimate_id"] == estimate_id
    assert all(row["estimate_id"] == estimate_id for row in reference["direction_scorelines"])
    assert reference["distribution_provenance"]["estimate_id"] == estimate_id
    assert snapshot["fair_line"] == 2.75
    assert reference["top_scorelines"][0]["probability"] == pytest.approx(
        max(snapshot["score_matrix"].values()),  # type: ignore[union-attr]
        abs=1e-6,
    )


def test_score_matrix_is_frozen_into_estimate_hash() -> None:
    snapshot = _snapshot()

    assert len(snapshot["score_matrix"]) == 169  # type: ignore[arg-type]
    assert sum(snapshot["score_matrix"].values()) == 1.0  # type: ignore[union-attr]
    assert verify_estimate_snapshot(snapshot)
