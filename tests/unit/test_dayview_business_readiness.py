from __future__ import annotations

from scripts.check_dayview_business_readiness import evaluate_dayview_business_readiness

from w2.models.fair_market_estimate import FairMarketEstimate, FairMarketEstimateSnapshot


def _snapshot() -> dict[str, object]:
    return FairMarketEstimateSnapshot.create(
        fixture_id="fixture",
        estimate=FairMarketEstimate(
            market="TOTALS",
            status="READY",
            model_family="R4_1_CALIBRATED",
            fair_line=2.75,
            probabilities={"OVER": 0.52, "UNDER": 0.48},
            home_mu=1.6,
            away_mu=1.1,
            feature_as_of="2026-07-12T00:00:00Z",
            train_cutoff="2026-06-30T00:00:00Z",
            artifact_hash="hash",
            artifact_version="v1",
        ),
        odds_snapshot={"line": 2.5},
        feature_snapshot={"xg": "ready"},
        created_at="2026-07-12T00:00:00Z",
    ).as_dict()


def test_business_gate_blocks_uniform_feature_chain_failure() -> None:
    report = evaluate_dayview_business_readiness(
        {"cards": [{"fixture_id": "1", "markets": [{}], "blockers": ["MISSING_XG"]}]}
    )
    assert report["status"] == "BLOCKED"
    assert "ALL_FIXTURES_BLOCKED_BY_FEATURE_CHAIN" in report["failures"]


def test_business_gate_allows_ready_fme_with_zero_recommendations() -> None:
    report = evaluate_dayview_business_readiness(
        {
            "cards": [
                {
                    "fixture_id": "fixture",
                    "markets": [{}],
                    "decision_tier": "WATCH",
                    "fair_market_estimate_snapshots": [_snapshot()],
                }
            ]
        }
    )
    assert report["status"] == "PASS"
    assert report["recommendation_count"] == 0
    assert report["fme_readiness_coverage"] == 1.0


def test_business_gate_blocks_provenance_integrity_and_missing_explanation() -> None:
    snapshot = _snapshot()
    snapshot["artifact_hash"] = "tampered"
    report = evaluate_dayview_business_readiness(
        {
            "cards": [
                {
                    "fixture_id": "fixture",
                    "markets": [{}],
                    "decision_tier": "ANALYSIS_PICK",
                    "fair_market_estimate_snapshots": [snapshot],
                    "scoreline_reference": {"direction_scorelines": []},
                }
            ]
        }
    )
    assert report["status"] == "BLOCKED"
    assert "FME_INTEGRITY_INVALID:fixture" in report["failures"]
    assert "DIRECTION_EXPLANATION_MISSING:fixture" in report["failures"]
