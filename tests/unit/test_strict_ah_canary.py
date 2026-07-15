from __future__ import annotations

from copy import deepcopy

from w2.models.fair_market_estimate import FairMarketEstimate, FairMarketEstimateSnapshot
from w2.models.market_quote import MarketQuote
from w2.strategy.analysis_gate_shadow import STRICT_GATE_HASH, STRICT_STRATEGY_VERSION
from w2.tracking.strict_ah_canary import check_strict_ah_canary


def test_no_candidate_is_successful_accumulating_state() -> None:
    result = check_strict_ah_canary([])

    assert result["status"] == "NO_CORRECTED_STRICT_CANDIDATE_YET"
    assert result["exit_code"] == 0


def test_unbound_strict_gate_is_not_a_corrected_candidate() -> None:
    capture = _capture("2026-07-16T10:00:00Z", "capture-1", home_mu=1.8)
    capture["analysis_gate_v2_shadows"][0]["quote_id"] = "unbound-quote"

    result = check_strict_ah_canary([capture])

    assert result["status"] == "NO_CORRECTED_STRICT_CANDIDATE_YET"
    assert result["candidate_count"] == 0


def test_valid_dual_confirmation_canary_passes() -> None:
    first, second = _dual_captures()

    result = check_strict_ah_canary([first, second])

    assert result["status"] == "PREMATCH_CANARY_PASS"
    assert result["exit_code"] == 0
    assert result["confirmation"]["status"] == "PASS"


def test_model_basis_change_resets_confirmation() -> None:
    first, second = _dual_captures(second_home_mu=1.9)

    result = check_strict_ah_canary([first, second])

    assert result["status"] == "NO_CORRECTED_STRICT_CANDIDATE_YET"
    assert result["confirmation"]["confirmation_status"] == "RESET"
    assert result["exit_code"] == 0


def test_duplicate_quote_id_fails() -> None:
    first, second = _dual_captures()
    first_identity = first["audit_capture_identities"][0]
    second_identity = second["audit_capture_identities"][0]
    second_identity["quote_id"] = first_identity["quote_id"]
    second_identity["market_quote"] = deepcopy(first_identity["market_quote"])
    second["analysis_gate_v2_shadows"][0]["quote_id"] = first_identity["quote_id"]

    result = check_strict_ah_canary([first, second])

    assert result["status"] == "NO_CORRECTED_STRICT_CANDIDATE_YET"
    assert result["checks"]["distinct_quote_ids"] == "FAIL"


def test_interval_below_fifteen_minutes_fails() -> None:
    first, second = _dual_captures(second_captured_at="2026-07-16T10:10:00Z")

    result = check_strict_ah_canary([first, second])

    assert result["status"] == "NO_CORRECTED_STRICT_CANDIDATE_YET"
    assert result["checks"]["minimum_interval"] == "FAIL"


def test_wrong_selection_line_fails() -> None:
    first, second = _dual_captures()
    second["analysis_gate_v2_shadows"][0]["selection_line"] = 0.75

    result = check_strict_ah_canary([first, second])

    assert result["status"] == "CANARY_BLOCKED"
    assert result["checks"]["selection_side_line"] == "FAIL"
    assert result["exit_code"] == 1


def test_duplicate_settlement_fails() -> None:
    first, second = _dual_captures()
    outcome = _outcome(second)

    result = check_strict_ah_canary([first, second, outcome, deepcopy(outcome)])

    assert result["status"] == "CANARY_BLOCKED"
    assert result["checks"]["single_settlement"] == "FAIL"


def test_validation_contamination_fails() -> None:
    first, second = _dual_captures()
    contamination = _outcome(second)
    contamination["recommendation_scope"] = "VALIDATION"
    contamination["settled_side"] = "pick"

    result = check_strict_ah_canary([first, second, contamination])

    assert result["status"] == "CANARY_BLOCKED"
    assert result["checks"]["validation_contamination"] == "FAIL"


def test_official_contamination_fails() -> None:
    first, second = _dual_captures()
    contamination = _outcome(second)
    contamination["recommendation_scope"] = "OFFICIAL"
    contamination["settled_side"] = "pick"

    result = check_strict_ah_canary([first, second, contamination])

    assert result["status"] == "CANARY_BLOCKED"
    assert result["checks"]["official_contamination"] == "FAIL"


def _dual_captures(
    *,
    second_captured_at: str = "2026-07-16T10:15:00Z",
    second_home_mu: float = 1.8,
) -> tuple[dict[str, object], dict[str, object]]:
    return (
        _capture("2026-07-16T10:00:00Z", "capture-1", home_mu=1.8),
        _capture(second_captured_at, "capture-2", home_mu=second_home_mu),
    )


def _capture(captured_at: str, capture_hash: str, *, home_mu: float) -> dict[str, object]:
    estimate = FairMarketEstimate(
        market="ASIAN_HANDICAP",
        status="READY",
        model_family="R4_1_CALIBRATED",
        fair_line=-1.0,
        probabilities={"HOME": 0.55, "DRAW": 0.24, "AWAY": 0.21},
        home_mu=home_mu,
        away_mu=0.8,
        feature_as_of="2026-07-16T09:00:00Z",
        train_cutoff="2026-06-30T00:00:00Z",
        artifact_hash="artifact",
        artifact_version="r4.1",
    )
    odds = {
        "home_line": -0.75,
        "away_line": 0.75,
        "home_price": 1.92,
        "away_price": 1.92,
        "captured_at": captured_at,
    }
    snapshot = FairMarketEstimateSnapshot.create(
        fixture_id="strict-fixture",
        estimate=estimate,
        odds_snapshot={"ah": odds},
        feature_snapshot={"home_xg": home_mu, "away_xg": 0.8},
        created_at=captured_at,
    ).as_dict()
    quote = MarketQuote.create(
        fixture_id="strict-fixture",
        market="ASIAN_HANDICAP",
        selection="HOME_AH",
        odds=odds,
        captured_at=captured_at,
    ).as_dict()
    gate = {
        "fixture_id": "strict-fixture",
        "kickoff_utc": "2026-07-16T12:00:00Z",
        "market": "ASIAN_HANDICAP",
        "selection": "HOME_AH",
        "model_basis_id": snapshot["model_basis_id"],
        "estimate_id": snapshot["estimate_id"],
        "quote_id": quote["quote_id"],
        "quote_captured_at": captured_at,
        "candidate_pass": True,
        "confirmation_required": True,
        "strategy_version": STRICT_STRATEGY_VERSION,
        "strict_gate_hash": STRICT_GATE_HASH,
        "evidence_eligible": True,
        "semantic_status": "VERIFIED",
        "selection_line": -0.75,
        "odds": 1.92,
        "shadow_only": True,
        "affects_decision": False,
        "affects_tier": False,
    }
    identity = {
        "market": "ASIAN_HANDICAP",
        "selection": "HOME_AH",
        "recommendation_scope": "SHADOW",
        "strategy_version": STRICT_STRATEGY_VERSION,
        "estimate_id": snapshot["estimate_id"],
        "quote_id": quote["quote_id"],
        "market_quote": quote,
        "evidence_eligible": True,
    }
    return {
        "record_type": "capture",
        "fixture_id": "strict-fixture",
        "kickoff_utc": "2026-07-16T12:00:00Z",
        "captured_at": captured_at,
        "capture_hash": capture_hash,
        "decision_tier": "WATCH",
        "fair_market_estimate_snapshots": [snapshot],
        "analysis_gate_v2_shadows": [gate],
        "audit_capture_identities": [identity],
    }


def _outcome(capture: dict[str, object]) -> dict[str, object]:
    identity = capture["audit_capture_identities"][0]
    return {
        "record_type": "outcome",
        "fixture_id": "strict-fixture",
        "market": "ASIAN_HANDICAP",
        "selection": "HOME_AH",
        "recommendation_scope": "SHADOW",
        "strategy_version": STRICT_STRATEGY_VERSION,
        "estimate_id": identity["estimate_id"],
        "quote_id": identity["quote_id"],
        "source_capture_hash": capture["capture_hash"],
        "settled_side": "shadow_pick",
        "entry_line": -0.75,
        "entry_price": 1.92,
        "final_score": {"home": 2, "away": 0, "status": "FT"},
        "settlement_outcome": "WIN",
        "settled_at": "2026-07-16T14:00:00Z",
    }
