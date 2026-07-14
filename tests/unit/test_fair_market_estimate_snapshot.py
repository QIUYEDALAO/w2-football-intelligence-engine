from __future__ import annotations

from copy import deepcopy

import pytest

from w2.dashboard.scorelines import scoreline_reference_from_card
from w2.models.fair_market_estimate import (
    FairMarketEstimate,
    FairMarketEstimateSnapshot,
    canonical_estimate_hash,
    estimate_semantic_status,
    estimate_snapshot_by_id,
    verify_estimate_semantics,
    verify_estimate_snapshot,
)


def _estimate(
    *,
    fair_line: float = 2.75,
    fallback_reason: str | None = None,
    home_mu: float = 1.6,
    rho: float = 0.0,
) -> FairMarketEstimate:
    return FairMarketEstimate(
        market="TOTALS",
        status="READY",
        model_family="R4_1_CALIBRATED",
        fair_line=fair_line,
        probabilities={"OVER": 0.52, "UNDER": 0.48},
        home_mu=home_mu,
        away_mu=1.1,
        feature_as_of="2026-07-12T00:00:00Z",
        train_cutoff="2026-06-30T00:00:00Z",
        artifact_hash="artifact-hash",
        artifact_version="r4.1",
        fallback_reason=fallback_reason,
        dixon_coles_rho=rho,
    )


def _snapshot(
    *,
    fair_line: float = 2.75,
    odds_snapshot: dict[str, object] | None = None,
    created_at: str = "2026-07-12T00:00:00Z",
    fallback_reason: str | None = None,
    home_mu: float = 1.6,
    rho: float = 0.0,
) -> dict[str, object]:
    return FairMarketEstimateSnapshot.create(
        fixture_id="fixture-1",
        estimate=_estimate(
            fair_line=fair_line,
            fallback_reason=fallback_reason,
            home_mu=home_mu,
            rho=rho,
        ),
        odds_snapshot=odds_snapshot or {"ou": {"line": 2.5, "over_price": 1.95}},
        feature_snapshot={"home_xg": 1.6, "away_xg": 1.1},
        created_at=created_at,
    ).as_dict()


def test_estimate_id_is_deterministic_and_excludes_capture_time() -> None:
    first = _snapshot(created_at="2026-07-12T00:00:00Z")
    second = _snapshot(created_at="2026-07-12T00:01:00Z")

    assert first["estimate_id"] == second["estimate_id"]
    assert first["model_basis_id"] == second["model_basis_id"]
    assert first["estimate_hash"] == second["estimate_hash"]
    assert first["created_at"] != second["created_at"]
    assert verify_estimate_snapshot(first)
    assert verify_estimate_snapshot(second)


def test_estimate_id_changes_with_input_or_output() -> None:
    baseline = _snapshot()
    changed_input = _snapshot(
        odds_snapshot={"ou": {"line": 2.75, "over_price": 1.95}}
    )
    changed_output = _snapshot(home_mu=1.7)
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
    model_context = dict(snapshot["model_context"])  # type: ignore[arg-type]
    model_context.pop("dixon_coles_rho")
    payload: dict[str, object] = {
        key: snapshot[key]
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
        )
    }
    payload["model_context"] = model_context
    estimate_hash = canonical_estimate_hash(payload)
    legacy = {
        **payload,
        "estimate_id": f"fme_{estimate_hash}",
        "estimate_hash": estimate_hash,
        "integrity": {
            "estimate_hash": estimate_hash,
            "created_at": snapshot["created_at"],
        },
        "model_family": snapshot["model_family"],
        "artifact_hash": snapshot["artifact_hash"],
        "artifact_version": snapshot["artifact_version"],
        "train_cutoff": snapshot["train_cutoff"],
        "feature_as_of": snapshot["feature_as_of"],
        "odds_snapshot_hash": snapshot["odds_snapshot_hash"],
        "feature_snapshot_hash": snapshot["feature_snapshot_hash"],
    }

    assert verify_estimate_snapshot(legacy)
    assert estimate_semantic_status(legacy) == "LEGACY_DISTRIBUTION_CONTEXT_UNVERIFIED"


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
    assert snapshot["fair_line"] == snapshot["model_fair_ou"]
    assert reference["top_scorelines"][0]["probability"] == pytest.approx(
        max(snapshot["score_matrix"].values()),  # type: ignore[union-attr]
        abs=1e-6,
    )


def test_score_matrix_is_frozen_into_estimate_hash() -> None:
    snapshot = _snapshot()

    assert len(snapshot["score_matrix"]) == 169  # type: ignore[arg-type]
    assert sum(snapshot["score_matrix"].values()) == 1.0  # type: ignore[union-attr]
    assert verify_estimate_snapshot(snapshot)


def test_v2_snapshot_closes_distribution_semantics() -> None:
    snapshot = _snapshot(rho=-0.05)

    assert snapshot["schema_version"] == "w2.fme_snapshot.v2"
    assert snapshot["semantic_status"] == "VERIFIED"
    assert snapshot["evidence_eligible"] is True
    assert verify_estimate_snapshot(snapshot)
    assert verify_estimate_semantics(snapshot)
    assert estimate_semantic_status(snapshot) == "VERIFIED"
    assert snapshot["score_matrix"] == snapshot["model_score_distribution"]
    assert snapshot["distribution_context"]["dixon_coles_rho"] == "-0.05"  # type: ignore[index]
    assert snapshot["distribution_context"]["max_goals"] == 12  # type: ignore[index]
    assert snapshot["distribution_context"]["tail_policy"] == (  # type: ignore[index]
        "TRUNCATE_AND_RENORMALIZE"
    )
    assert snapshot["distribution_context"]["probability_quantization"] == (  # type: ignore[index]
        "DECIMAL_12_HALF_EVEN"
    )
    assert snapshot["distribution_context"]["score_matrix_hash"]  # type: ignore[index]
    assert "market_implied_probabilities" not in snapshot
    assert "win_probability" not in snapshot


def test_effective_cover_index_is_derived_from_five_state_distribution() -> None:
    snapshot = _snapshot()
    totals = snapshot["model_settlement_distributions"]["TOTALS"]  # type: ignore[index]
    over = totals["at_fair_line"]["OVER"]
    expected = (
        over["WIN"]
        + 0.75 * over["HALF_WIN"]
        + 0.5 * over["PUSH"]
        + 0.25 * over["HALF_LOSS"]
    )

    assert snapshot["effective_cover_index"]["TOTALS"]["OVER"] == pytest.approx(  # type: ignore[index]
        expected,
        abs=1e-12,
    )
    assert snapshot["effective_cover_index_semantics"] == (
        "WIN_1_HALF_WIN_0.75_PUSH_0.5_HALF_LOSS_0.25_LOSS_0"
    )
    assert totals["quote_line"] == 2.5
    assert sum(totals["at_quote_line"]["OVER"].values()) == pytest.approx(1.0)
    ah_index = snapshot["effective_cover_index"]["ASIAN_HANDICAP"]  # type: ignore[index]
    assert ah_index["HOME"] + ah_index["AWAY"] == pytest.approx(1.0, abs=1e-12)


def test_score_matrix_uses_fixed_decimal12_quantization_and_mass_audit() -> None:
    snapshot = _snapshot(rho=-0.05)
    probabilities = snapshot["score_matrix"].values()  # type: ignore[union-attr]

    assert all(len(str(value).partition(".")[2]) <= 12 for value in probabilities)
    assert sum(snapshot["score_matrix"].values()) == pytest.approx(1.0)  # type: ignore[union-attr]
    assert snapshot["distribution_context"]["matrix_mass_before_normalization"]  # type: ignore[index]


def test_quote_change_keeps_model_basis_but_changes_estimate_id() -> None:
    first = _snapshot(odds_snapshot={"ou": {"line": 2.5, "over_price": 1.95}})
    second = _snapshot(odds_snapshot={"ou": {"line": 2.75, "over_price": 1.91}})

    assert first["model_basis_id"] == second["model_basis_id"]
    assert first["estimate_id"] != second["estimate_id"]


def test_semantic_verifier_rejects_rehashed_distribution_tampering() -> None:
    snapshot = deepcopy(_snapshot())
    snapshot["model_fair_ou"] = 7.5
    payload = {
        key: snapshot[key]
        for key in (
            "schema_version",
            "model_basis_id",
            "fixture_id",
            "market",
            "status",
            "fallback_reason",
            "fair_line",
            "probabilities",
            "home_mu",
            "away_mu",
            "score_matrix",
            "distribution_context",
            "model_one_x_two_probabilities",
            "model_fair_ah",
            "model_fair_ou",
            "model_score_distribution",
            "model_settlement_distributions",
            "effective_cover_index",
            "effective_cover_index_semantics",
            "semantic_status",
            "evidence_eligible",
            "input_context",
            "model_context",
        )
    }
    estimate_hash = canonical_estimate_hash(payload)
    snapshot["estimate_id"] = f"fme_{estimate_hash}"
    snapshot["estimate_hash"] = estimate_hash
    snapshot["integrity"]["estimate_hash"] = estimate_hash  # type: ignore[index]

    assert verify_estimate_snapshot(snapshot)
    assert verify_estimate_semantics(snapshot) is False


def test_v2_insufficient_estimate_fails_closed_without_fake_distribution() -> None:
    snapshot = FairMarketEstimateSnapshot.create(
        fixture_id="fixture-insufficient",
        estimate=FairMarketEstimate(
            market="ASIAN_HANDICAP",
            status="INSUFFICIENT",
            model_family="R4_1_CALIBRATED",
            fair_line=None,
            probabilities={},
            home_mu=None,
            away_mu=None,
            feature_as_of=None,
            train_cutoff=None,
            fallback_reason="FME_PROVENANCE_INCOMPLETE",
        ),
        odds_snapshot={"ah": {"home_line": 0, "away_line": 0}},
        feature_snapshot={},
        created_at="2026-07-12T00:00:00Z",
    ).as_dict()

    assert verify_estimate_snapshot(snapshot)
    assert verify_estimate_semantics(snapshot) is False
    assert snapshot["semantic_status"] == "INSUFFICIENT"
    assert snapshot["evidence_eligible"] is False
    assert snapshot["score_matrix"] == {}
    assert snapshot["model_settlement_distributions"] == {}
