from __future__ import annotations

from copy import deepcopy

from w2.backtest.ah_formal_evidence import (
    AhFormalEvidenceProtocol,
    evaluate_ah_formal_evidence,
)
from w2.backtest.historical_replay import build_calibration_artifact, build_historical_replay_row
from w2.formal.readiness import evaluate_formal_ah_readiness
from w2.markets.analysis_evidence import build_analysis_market_evidence
from w2.markets.score_baseline import build_market_score_baseline, fair_decimal_odds
from w2.markets.settlement_probability import effective_settlement_probability
from w2.tracking.forward_shadow_evidence import (
    FORWARD_TARGET_COUNT,
    build_forward_shadow_evidence,
    evaluate_forward_shadow_evidence,
)


def test_shared_effective_probability_push_semantics() -> None:
    assert effective_settlement_probability(_dist(win=1)) == 1
    assert effective_settlement_probability(_dist(push=1)) == 0.5
    assert effective_settlement_probability(_dist(loss=1)) == 0
    assert effective_settlement_probability(_dist(half_win=1)) == 0.5
    assert effective_settlement_probability(_dist(half_loss=1)) == 0
    mixed = _dist(win=0.2, half_win=0.2, push=0.2, half_loss=0.2, loss=0.2)
    assert effective_settlement_probability(mixed) == 0.4


def test_runtime_and_offline_scalar_probability_are_equal() -> None:
    simulation = {
        "status": "READY",
        "lambda_home": 1.4,
        "lambda_away": 1.0,
        "lambda_sigma_home": 0.08,
        "lambda_sigma_away": 0.07,
        "calibration": {
            "lambda_uncertainty_method": "deterministic_three_point",
            "params": {},
        },
    }
    evidence = build_analysis_market_evidence(
        fixture_id="f1",
        competition_id="c1",
        market="ASIAN_HANDICAP",
        selection="HOME",
        line="0",
        quote_identity_audit={
            "ah": {
                "identity_status": "COMPLETE",
                "freshness_status": "COMPLETE",
                "provider": "p",
                "bookmaker_id": "b",
                "captured_at": "2026-01-01T00:00:00Z",
                "observation_ids": {"home": "h", "away": "a"},
                "quotes": {
                    "home": {"line": "0", "decimal_odds": "1.95"},
                    "away": {"line": "0", "decimal_odds": "1.95"},
                },
            }
        },
        simulation=simulation,
    )
    distribution = evidence["model_probability"]["settlement_distribution"]
    runtime_probability = evidence["model_probability"]["effective_probability"]
    assert runtime_probability == effective_settlement_probability(distribution)


def test_multiclass_ece_clv_candidate_and_mixed_blockers() -> None:
    rows = [_evidence_row(kickoff="2026-02-01T00:00:00Z")]
    report = evaluate_ah_formal_evidence(
        rows,
        protocol=_protocol(minimum_holdout_samples=1),
        data_source="unit",
    )
    holdout = report["all_holdout_metrics"]
    assert holdout["ece_method"] == "CLASSWISE_MULTICLASS_ECE_10_EQUAL_WIDTH_BINS"
    assert holdout["per_class_ece"]["model"]["LOSS"] >= 0
    assert holdout["mean_clv_probability_delta"] == 0.04
    assert report["candidate_holdout_metrics"]["sample_count"] == 0

    mixed = deepcopy(rows)
    mixed.append({**_evidence_row(kickoff="2026-03-01T00:00:00Z"), "model_version": "m2"})
    mixed_report = evaluate_ah_formal_evidence(
        mixed,
        protocol=_protocol(minimum_holdout_samples=1),
        data_source="unit",
    )
    assert "MIXED_MODEL_VERSION" in mixed_report["blockers"]


def test_zero_row_evidence_fails_closed() -> None:
    report = evaluate_ah_formal_evidence([], protocol=_protocol(), data_source="empty")
    assert report["conclusion"] == "INSUFFICIENT_EVIDENCE"
    assert "INSUFFICIENT_EVIDENCE" in report["blockers"]


def test_market_score_baseline_batch_and_unvalidated_residual_gate() -> None:
    ready_like = build_market_score_baseline(_quotes(), entry_checkpoint="2026-01-01T12:00:00Z")
    assert ready_like["status"] == "UNVALIDATED"
    assert ready_like["optimizer_status"] == "CONVERGED_DIAGNOSTIC"
    assert ready_like["model_fair_odds"]["ASIAN_HANDICAP"]["HOME"] > 1
    assert ready_like["market_fair_odds"]["TOTALS"]["OVER"] > 1
    assert ready_like["zero_ev_residuals_by_market"]["ASIAN_HANDICAP"] >= 0
    assert ready_like["baseline_hash"]

    mismatch = _quotes()
    mismatch[0]["bookmaker_id"] = "other"
    assert (
        build_market_score_baseline(mismatch, entry_checkpoint="2026-01-01T12:00:00Z")[
            "status"
        ]
        == "INCOMPLETE"
    )

    missing_ou = [row for row in _quotes() if row["market"] != "TOTALS"]
    assert (
        build_market_score_baseline(missing_ou, entry_checkpoint="2026-01-01T12:00:00Z")[
            "status"
        ]
        == "INCOMPLETE"
    )

    only_ah = [row for row in _quotes() if row["market"] == "ASIAN_HANDICAP"]
    assert (
        build_market_score_baseline(only_ah, entry_checkpoint="2026-01-01T12:00:00Z")[
            "status"
        ]
        == "INSUFFICIENT_MARKET_DIMENSIONS"
    )


def test_fair_decimal_odds_uses_five_state_zero_ev_formula() -> None:
    assert fair_decimal_odds(_dist(win=0.5, half_loss=0.5)) == 1.5


def test_replay_and_calibration_artifact_fail_closed_and_deterministic() -> None:
    row = build_historical_replay_row(
        {
            "fixture_id": "f1",
            "competition_id": "c1",
            "kickoff_utc": "2026-01-01T00:00:00Z",
            "as_of_utc": "2026-01-01T00:01:00Z",
            "f5_status": "PROXY",
            "f8_status": "INCOMPLETE",
            "market_baseline_status": "UNVALIDATED",
        }
    )
    assert "ASOF_NOT_STRICTLY_PREMATCH" in row["blockers"]
    assert "F5_PROXY_OR_NOT_READY" in row["blockers"]
    assert "MISSING_CALIBRATION_VERSION" in row["blockers"]
    artifact = build_calibration_artifact(
        [],
        code_sha="code",
        model_version="model",
        factor_registry_sha="factor",
        historical_manifest_sha="hist",
        f5_manifest_sha="f5",
        f8_manifest_sha="f8",
        evaluator_version="eval",
    )
    assert artifact["status"] == "INSUFFICIENT_EVIDENCE"
    assert artifact == build_calibration_artifact(
        [],
        code_sha="code",
        model_version="model",
        factor_registry_sha="factor",
        historical_manifest_sha="hist",
        f5_manifest_sha="f5",
        f8_manifest_sha="f8",
        evaluator_version="eval",
    )
    blocked_artifact = build_calibration_artifact(
        [row],
        code_sha="code",
        model_version="model",
        factor_registry_sha="factor",
        historical_manifest_sha="hist",
        f5_manifest_sha="f5",
        f8_manifest_sha="f8",
        evaluator_version="eval",
    )
    assert blocked_artifact["accepted_row_count"] == 0
    assert blocked_artifact["rejected_row_count"] == 1
    assert blocked_artifact["holdout_count"] == 0
    assert blocked_artifact["exclusion_report"]["F5_PROXY_OR_NOT_READY"] == 1


def test_formal_readiness_blockers_and_approval_hash_mismatch() -> None:
    readiness = evaluate_formal_ah_readiness(
        calibration={"status": "INSUFFICIENT_EVIDENCE"},
        f5_historical_ah={"status": "SOURCE_NOT_AVAILABLE"},
        f8_identity_value={"status": "SOURCE_NOT_AVAILABLE"},
        offline_evidence={"conclusion": "INSUFFICIENT_EVIDENCE"},
        forward_shadow={"conclusion": "INSUFFICIENT_EVIDENCE"},
        approval_manifest={
            "schema_version": "w2.formal_ah_approval_manifest.v1",
            "approved": True,
            "reviewed_by": "reviewer",
            "reviewed_at": "2026-07-20T00:00:00Z",
            "accepted_hashes": {
                "calibration_artifact": "bad",
                "f5_manifest": "bad",
                "f8_manifest": "bad",
                "offline_evidence_report": "bad",
                "forward_shadow_report": "bad",
                "code_sha": "bad",
                "factor_registry_sha": "bad",
            },
            "accepted_hash_manifest_sha256": "bad",
        },
    )
    assert readiness["admission_ready"] is False
    assert "FORMAL_CALIBRATION_NOT_VALIDATED" in readiness["blockers"]
    assert "FORMAL_APPROVED_HASH_MISMATCH" in readiness["blockers"]
    assert "FORMAL_ACTUAL_ARTIFACT_HASH_MISSING" in readiness["blockers"]
    assert readiness["recommendation_id"] is None


def test_forward_shadow_scope_and_exclusion_from_formal_count() -> None:
    capture = build_forward_shadow_evidence(
        {
            "model_five_state_distribution": _dist(win=1),
            "market_baseline_status": "UNVALIDATED",
            "test_only": True,
        }
    )
    assert capture["shadow"] is False
    assert capture["not_a_recommendation"] is True
    assert capture["formal_evidence_eligible"] is False
    report = evaluate_forward_shadow_evidence([capture])
    assert report["target_count"] == FORWARD_TARGET_COUNT == 200
    assert report["real_formal_evidence_count"] == 0
    assert report["conclusion"] == "INSUFFICIENT_EVIDENCE"
    assert report["shadow_to_validation_count"] == 0
    assert report["shadow_to_official_count"] == 0


def _dist(
    *,
    win: float = 0,
    half_win: float = 0,
    push: float = 0,
    half_loss: float = 0,
    loss: float = 0,
) -> dict[str, float]:
    return {
        "WIN": win,
        "HALF_WIN": half_win,
        "PUSH": push,
        "HALF_LOSS": half_loss,
        "LOSS": loss,
    }


def _protocol(**overrides: int) -> AhFormalEvidenceProtocol:
    defaults = {
        "frozen_at_utc": "2026-07-20T00:00:00Z",
        "train_end_utc": "2024-12-31T23:59:59Z",
        "validation_end_utc": "2025-12-31T23:59:59Z",
        "minimum_train_samples": 0,
        "minimum_validation_samples": 0,
        "minimum_holdout_samples": 0,
    }
    defaults.update(overrides)
    return AhFormalEvidenceProtocol(**defaults)


def _evidence_row(*, kickoff: str) -> dict[str, object]:
    return {
        "canonical_cohort": True,
        "fixture_id": "f1",
        "identity_trace_id": "id1",
        "market": "ASIAN_HANDICAP",
        "settlement_outcome": "LOSS",
        "kickoff_utc": kickoff,
        "as_of_utc": "2026-01-01T00:00:00Z",
        "model_probabilities": _dist(win=0.1, half_win=0.1, push=0.1, half_loss=0.1, loss=0.6),
        "market_devig_probabilities": _dist(
            win=0.2,
            half_win=0.1,
            push=0.1,
            half_loss=0.1,
            loss=0.5,
        ),
        "selection_odds": 2.0,
        "selection": "HOME",
        "line": "-0.25",
        "entry_devig_probability": 0.3,
        "entry_captured_at": "2026-01-01T00:00:00Z",
        "closing_devig_probability": 0.34,
        "closing_quote_identity_hash": "h",
        "closing_quote_captured_at": "2026-01-01T01:00:00Z",
        "closing_selection": "HOME",
        "closing_line": "-0.25",
        "model_expected_value": -0.5,
        "model_market_probability_delta": -0.1,
        "model_version": "m1",
        "calibration_version": "c1",
        "factor_registry_sha": "f1",
        "code_sha": "code",
        "source_manifest_sha": "source",
        "f5_status": "READY",
        "f5_fact_hashes": ["fact"],
        "f8_status": "READY",
        "team_value_artifact_hashes": ["team-value"],
        "market_baseline_status": "READY",
        "market_baseline_hash": "market",
        "quote_identity_hash": "quote",
        "result_identity_hash": "result",
    }


def _quotes() -> list[dict[str, object]]:
    base = {
        "provider_fixture_id": "pf1",
        "bookmaker_id": "bm1",
        "provider": "p1",
        "captured_at": "2026-01-01T00:00:00Z",
        "source_snapshot_id": "snapshot-1",
        "source_sha256": "s" * 64,
        "live": False,
        "suspended": False,
    }
    return [
        _quote(base, "1X2", "HOME", "2.10", "1"),
        _quote(base, "1X2", "DRAW", "3.20", "2"),
        _quote(base, "1X2", "AWAY", "3.40", "3"),
        _quote(base, "ASIAN_HANDICAP", "HOME", "1.95", "4", line="-0.25"),
        _quote(base, "ASIAN_HANDICAP", "AWAY", "1.95", "5", line="0.25"),
        _quote(base, "TOTALS", "OVER", "1.90", "6", line="2.25"),
        _quote(base, "TOTALS", "UNDER", "2.00", "7", line="2.25"),
    ]


def _quote(
    base: dict[str, object],
    market: str,
    selection: str,
    odds: str,
    observation_id: str,
    line: str | None = None,
) -> dict[str, object]:
    return {
        **base,
        "market": market,
        "selection": selection,
        "decimal_odds": odds,
        "observation_id": observation_id,
        "line": line,
    }
