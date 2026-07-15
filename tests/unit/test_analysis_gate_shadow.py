from __future__ import annotations

from copy import deepcopy

from w2.models.fair_market_estimate import FairMarketEstimate, FairMarketEstimateSnapshot
from w2.strategy.analysis_gate_shadow import (
    STRICT_GATE_HASH,
    STRICT_POLICY,
    build_analysis_gate_v2_shadow,
)


def _snapshot() -> dict[str, object]:
    return FairMarketEstimateSnapshot.create(
        fixture_id="fixture-1",
        estimate=FairMarketEstimate(
            market="TOTALS",
            status="READY",
            model_family="R4_1_CALIBRATED",
            fair_line=3.0,
            probabilities={"OVER": 0.55, "UNDER": 0.45},
            home_mu=1.8,
            away_mu=1.2,
            feature_as_of="2026-07-12T00:00:00Z",
            train_cutoff="2026-06-01T00:00:00Z",
            artifact_hash="artifact",
            artifact_version="v1",
        ),
        odds_snapshot={"ou": {"line": 2.5, "over_price": 1.95}},
        feature_snapshot={"home_xg": 1.8, "away_xg": 1.2},
        created_at="2026-07-12T00:00:00Z",
    ).as_dict()


def test_ev_challenger_uses_frozen_settlement_distribution_and_never_affects_decision() -> None:
    snapshot = _snapshot()
    result = build_analysis_gate_v2_shadow(
        estimate=snapshot,
        gate={
            "market": "TOTALS",
            "selection": "OVER",
            "market_line": 2.5,
            "status": "ELIGIBLE",
        },
        odds=1.95,
    )

    probabilities = result["settlement_probabilities"]
    expected = (
        probabilities["WIN"] * 0.95
        + probabilities["HALF_WIN"] * 0.475
        - probabilities["HALF_LOSS"] * 0.5
        - probabilities["LOSS"]
    )
    assert result["net_ev"] == round(expected, 8)
    assert result["estimate_id"] == snapshot["estimate_id"]
    assert result["affects_decision"] is False
    assert result["affects_pick"] is False
    assert result["affects_tier"] is False
    assert result["shadow_only"] is True
    assert result["confirmation_required"] is False
    assert result["confirmation_status"] == "NOT_REQUIRED"


def test_ah_strict_policy_is_versioned_hashed_and_never_visible() -> None:
    snapshot = FairMarketEstimateSnapshot.create(
        fixture_id="fixture-ah",
        estimate=FairMarketEstimate(
            market="ASIAN_HANDICAP",
            status="READY",
            model_family="R4_1_CALIBRATED",
            fair_line=-1.0,
            probabilities={},
            home_mu=1.9,
            away_mu=0.9,
            feature_as_of="2026-07-12T00:00:00Z",
            train_cutoff="2026-06-01T00:00:00Z",
            artifact_hash="artifact",
            artifact_version="v1",
        ),
        odds_snapshot={"ah": {"line": -0.75, "home_price": 1.92}},
        feature_snapshot={"home_xg": 1.9, "away_xg": 0.9},
        created_at="2026-07-12T00:00:00Z",
    ).as_dict()

    result = build_analysis_gate_v2_shadow(
        estimate=snapshot,
        gate={
            "market": "ASIAN_HANDICAP",
            "selection": "HOME_AH",
            "market_line": -0.75,
            "status": "ELIGIBLE",
        },
        odds=1.92,
    )

    assert STRICT_POLICY["strategy_version"] == "W2_AH_STRICT_SHADOW_V1"
    assert len(STRICT_GATE_HASH) == 64
    assert result["strict_gate_hash"] == STRICT_GATE_HASH
    assert result["confirmation_required"] is True
    assert result["visible_eligible"] is False
    assert result["affects_decision"] is False


def test_ev_challenger_is_insufficient_without_odds_and_does_not_change_current_gate() -> None:
    result = build_analysis_gate_v2_shadow(
        estimate=_snapshot(),
        gate={
            "market": "TOTALS",
            "selection": "OVER",
            "market_line": 2.5,
            "status": "ELIGIBLE",
        },
        odds=None,
    )

    assert result["status"] == "INSUFFICIENT"
    assert result["current_gate_status"] == "ELIGIBLE"
    assert result["current_gate_pass"] is True
    assert result["affects_decision"] is False


def test_ev_challenger_supports_quarter_asian_handicap_without_crossing_markets() -> None:
    snapshot = FairMarketEstimateSnapshot.create(
        fixture_id="fixture-ah",
        estimate=FairMarketEstimate(
            market="ASIAN_HANDICAP",
            status="READY",
            model_family="R4_1_CALIBRATED",
            fair_line=-1.0,
            probabilities={"HOME_AH": 0.56, "AWAY_AH": 0.44},
            home_mu=1.9,
            away_mu=0.9,
            feature_as_of="2026-07-12T00:00:00Z",
            train_cutoff="2026-06-01T00:00:00Z",
            artifact_hash="artifact",
            artifact_version="v1",
        ),
        odds_snapshot={"ah": {"line": -0.75, "home_price": 1.92}},
        feature_snapshot={"home_xg": 1.9, "away_xg": 0.9},
        created_at="2026-07-12T00:00:00Z",
    ).as_dict()

    result = build_analysis_gate_v2_shadow(
        estimate=snapshot,
        gate={
            "market": "ASIAN_HANDICAP",
            "selection": "HOME_AH",
            "market_line": -0.75,
            "status": "ELIGIBLE",
        },
        odds=1.92,
    )

    probabilities = result["settlement_probabilities"]
    assert result["market"] == "ASIAN_HANDICAP"
    assert result["home_centric_market_line"] == -0.75
    assert result["selection_line"] == -0.75
    assert result["line"] == -0.75
    assert probabilities["HALF_WIN"] > 0
    assert probabilities["PUSH"] == 0
    assert round(sum(probabilities.values()), 8) == 1.0


def test_away_ah_shadow_ev_uses_positive_selection_line() -> None:
    snapshot = FairMarketEstimateSnapshot.create(
        fixture_id="fixture-ah-away",
        estimate=FairMarketEstimate(
            market="ASIAN_HANDICAP",
            status="READY",
            model_family="R4_1_CALIBRATED",
            fair_line=-0.5,
            probabilities={},
            home_mu=1.4,
            away_mu=1.1,
            feature_as_of="2026-07-12T00:00:00Z",
            train_cutoff="2026-06-01T00:00:00Z",
            artifact_hash="artifact",
            artifact_version="v1",
        ),
        odds_snapshot={"ah": {"line": -0.75, "away_price": 1.92}},
        feature_snapshot={"home_xg": 1.4, "away_xg": 1.1},
        created_at="2026-07-12T00:00:00Z",
    ).as_dict()

    result = build_analysis_gate_v2_shadow(
        estimate=snapshot,
        gate={
            "market": "ASIAN_HANDICAP",
            "selection": "AWAY_AH",
            "market_line": -0.75,
            "status": "ELIGIBLE",
        },
        odds=1.92,
    )

    assert result["home_centric_market_line"] == -0.75
    assert result["selection_line"] == 0.75
    assert result["line"] == 0.75
    assert round(sum(result["settlement_probabilities"].values()), 8) == 1.0


def test_ev_challenger_rejects_tampered_estimate_snapshot() -> None:
    snapshot = deepcopy(_snapshot())
    snapshot["score_matrix"]["0-0"] = 0.5  # type: ignore[index]

    result = build_analysis_gate_v2_shadow(
        estimate=snapshot,
        gate={
            "market": "TOTALS",
            "selection": "OVER",
            "market_line": 2.5,
            "status": "ELIGIBLE",
        },
        odds=1.95,
    )

    assert result["status"] == "INSUFFICIENT"
    assert result["reason"] == "INVALID_ESTIMATE_INTEGRITY"
    assert result["affects_decision"] is False


def test_v1_snapshot_is_not_evidence_eligible() -> None:
    snapshot = _snapshot()
    legacy = {
        "market": snapshot["market"],
        "score_matrix": snapshot["score_matrix"],
    }
    result = build_analysis_gate_v2_shadow(
        estimate=legacy,
        gate={
            "market": "TOTALS",
            "selection": "OVER",
            "market_line": 2.5,
            "status": "ELIGIBLE",
        },
        odds=1.95,
    )

    assert result["raw_shadow_capture"] is True
    assert result["diagnostic_only"] is True
    assert result["evidence_eligible"] is False
    assert result["not_a_recommendation"] is True
    assert result["semantic_status"] == "LEGACY_DISTRIBUTION_CONTEXT_UNVERIFIED"
