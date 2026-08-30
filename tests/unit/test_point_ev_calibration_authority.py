"""POINT-EV-AUTHORITY-01 regression suite.

Fixture 1570340 (TOTALS UNDER 3.5 @ 1.92) reached
ANALYSIS_PICK_ACTIVE, EVALUATED_CANDIDATE, and a DELIVERED T-30 confirmation on a
BASELINE_PRIOR probability that had never been validated. The EV arithmetic was
right; nothing was bound to whether the probability was.

The frozen production values used below come from
docs/review_packages/POINT_EV_AUTHORITY_01/FIXTURE_1570340_EVALUATION.json, read
read-only under REPEATABLE READ. The match result is not read anywhere here.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from w2.domain import calibration_authority
from w2.markets.analysis_evidence import build_analysis_market_evidence
from w2.markets.round3_intelligence import _model_blockers
from w2.prematch.lifecycle import (
    DynamicEvaluationInput,
    DynamicEvaluationState,
    classify_evaluation,
)

NOW = datetime(2026, 8, 26, 18, 30, tzinfo=UTC)

# --- frozen from the production evaluation record -----------------------------
FIXTURE_ID = "1570340"
DECIMAL_ODDS = 1.92
EXACT_LINE = 3.5
MODEL_WIN_PROBABILITY = 0.7481305152250234
MODEL_LOSS_PROBABILITY = 0.25186948477497656
RECORDED_EV = 0.436411
RECORDED_DELTA = 0.248131
RECORDED_EV_SE = 0.436411 - 0.386085  # current_ev - current_ev_minus_se
FIVE_STATE = {
    "WIN": MODEL_WIN_PROBABILITY,
    "HALF_WIN": 0.0,
    "PUSH": 0.0,
    "HALF_LOSS": 0.0,
    "LOSS": MODEL_LOSS_PROBABILITY,
}

UNVALIDATED = ("BASELINE_PRIOR", "READY", "UNVALIDATED", "NOT_CALIBRATED", "UNKNOWN", None, "")
VALIDATED = ("PRODUCTION_VALIDATED", "APPROVED_VALIDATED")


def _evaluation(*, calibration_status: object, ev: float = 0.20, delta: float = 0.20) -> object:
    return DynamicEvaluationInput(
        fixture_id=FIXTURE_ID,
        market="TOTALS",
        selection="UNDER",
        exact_line=EXACT_LINE,
        bookmaker_id="book-1",
        capture_id="capture-1",
        quote_identity_hash="q" * 64,
        model_input_hash="m" * 64,
        evaluated_at=NOW,
        checkpoint="T-30m_VALIDATION_LOCK",
        capture_at=NOW,
        model_probability=0.50 + delta,
        market_probability=0.50,
        expected_value=ev,
        ev_se=0.05,
        decimal_odds=DECIMAL_ODDS,
        calibration_status=calibration_status,  # type: ignore[arg-type]
    )


def _simulation(calibration_status: object) -> dict[str, object]:
    simulation: dict[str, object] = {
        "status": "READY",
        "model_version": "model-v1",
        "calibration_version": "calibration-v1",
        "lambda_home": 1.4,
        "lambda_away": 0.9,
        "lambda_sigma_home": 0.08,
        "lambda_sigma_away": 0.07,
        "calibration": {
            "lambda_uncertainty_method": "deterministic_three_point",
            "params": {"dixon_coles_rho": 0.0},
        },
    }
    if calibration_status is not None:
        simulation["calibration_status"] = calibration_status
    return simulation


# --- (a) unvalidated calibration cannot form a formal recommendation ----------
@pytest.mark.parametrize("status", UNVALIDATED)
def test_a_unvalidated_calibration_cannot_reach_an_active_pick(status: object) -> None:
    """Even with EV, delta and EV-SE all comfortably clear, no candidate forms."""
    version = classify_evaluation(_evaluation(calibration_status=status))
    assert version.state is not DynamicEvaluationState.ANALYSIS_PICK_ACTIVE
    assert version.state is DynamicEvaluationState.NOT_READY_MODEL_INPUT
    assert calibration_authority.RECOMMENDATION_BLOCKER in version.blockers


@pytest.mark.parametrize("status", UNVALIDATED)
def test_a_unvalidated_calibration_blocks_the_round3_path_too(status: object) -> None:
    """The path that already checked calibration used to accept READY."""
    blockers = _model_blockers(_simulation(status))
    assert calibration_authority.RECOMMENDATION_BLOCKER in blockers


def test_a_ready_is_not_a_validation_verdict() -> None:
    """READY is the simulation pipeline's status. Conflating the two was the leak."""
    assert "READY" in calibration_authority.NON_VALIDATION_STATUSES
    assert "READY" not in calibration_authority.RECOMMENDATION_VALIDATED_STATUSES
    assert not calibration_authority.recommendation_admissible("READY")


# --- (b) an approved validated calibration still admits -----------------------
@pytest.mark.parametrize("status", VALIDATED)
def test_b_validated_calibration_still_admits(status: str) -> None:
    """The fix must be an authority, not a blanket denial."""
    version = classify_evaluation(_evaluation(calibration_status=status))
    assert version.state is DynamicEvaluationState.ANALYSIS_PICK_ACTIVE
    assert calibration_authority.RECOMMENDATION_BLOCKER not in version.blockers


@pytest.mark.parametrize("status", VALIDATED)
def test_b_validated_calibration_clears_the_round3_path(status: str) -> None:
    assert calibration_authority.RECOMMENDATION_BLOCKER not in _model_blockers(
        _simulation(status)
    )


def test_b_validated_calibration_still_answers_to_the_ev_gates() -> None:
    """Authority is a precondition, not a bypass: a validated model with no edge
    still gets NO_EDGE_CURRENT rather than a free pass."""
    version = classify_evaluation(
        _evaluation(calibration_status="PRODUCTION_VALIDATED", ev=-0.01, delta=0.20)
    )
    assert version.state is DynamicEvaluationState.NO_EDGE_CURRENT
    assert "EV_NOT_POSITIVE" in version.blockers


# --- (c) EV formula, direction, odds format and five-state binding intact -----
def test_c_five_state_ev_formula_is_unchanged() -> None:
    """The reported +43.6411% is arithmetically right and stays right."""
    ev = MODEL_WIN_PROBABILITY * (DECIMAL_ODDS - 1) - MODEL_LOSS_PROBABILITY
    assert ev == pytest.approx(RECORDED_EV, abs=1e-6)


def test_c_five_state_distribution_binding_is_unchanged() -> None:
    """A .5 line admits no push or half settlement, and the states still sum to 1."""
    assert FIVE_STATE["PUSH"] == 0.0
    assert FIVE_STATE["HALF_WIN"] == 0.0
    assert FIVE_STATE["HALF_LOSS"] == 0.0
    assert sum(FIVE_STATE.values()) == pytest.approx(1.0, abs=1e-12)


def test_c_line_direction_and_odds_format_survive_the_block() -> None:
    """Blocking the recommendation must not rewrite the quote it was about."""
    version = classify_evaluation(_evaluation(calibration_status="BASELINE_PRIOR"))
    assert version.market == "TOTALS"
    assert version.selection == "UNDER"
    assert version.exact_line == EXACT_LINE
    assert version.decimal_odds == DECIMAL_ODDS
    assert version.current_ev == pytest.approx(0.20)


def test_c_market_implied_probability_still_reads_as_decimal_odds() -> None:
    assert 1 / DECIMAL_ODDS == pytest.approx(0.520833, abs=1e-6)


# --- (d) fixture 1570340 under the current unvalidated model -> no candidate --
def test_d_fixture_1570340_yields_no_candidate_under_the_shipped_calibration() -> None:
    """The reported case, with its own recorded numbers, now holds instead of firing.

    The repository ledger has no grant for the shipped parameters, so the strategy
    declares BASELINE_PRIOR today.
    """
    from w2.prematch import analysis_calculator
    from w2.strategy.simulate import SimulationInputs

    simulation = analysis_calculator.run_simulation(
        SimulationInputs(
            fixture_id=FIXTURE_ID,
            home_team_id="home",
            away_team_id="away",
            home_xg_for=1.0,
            home_xg_against=1.0,
            away_xg_for=1.0,
            away_xg_against=1.0,
        )
    )
    calibration_status = simulation.calibration_status
    assert calibration_status == "BASELINE_PRIOR"
    version = classify_evaluation(
        _evaluation(
            calibration_status=calibration_status,
            ev=RECORDED_EV,
            delta=RECORDED_DELTA,
        )
    )
    assert version.state is not DynamicEvaluationState.ANALYSIS_PICK_ACTIVE
    assert calibration_authority.RECOMMENDATION_BLOCKER in version.blockers
    # the EV that was reported is still recorded, unmodified and uncapped
    assert version.current_ev == pytest.approx(RECORDED_EV)


def test_d_the_same_fixture_would_admit_once_the_model_is_validated() -> None:
    """The block is about provenance, not about this fixture's numbers."""
    version = classify_evaluation(
        _evaluation(
            calibration_status="PRODUCTION_VALIDATED",
            ev=RECORDED_EV,
            delta=RECORDED_DELTA,
        )
    )
    assert version.state is DynamicEvaluationState.ANALYSIS_PICK_ACTIVE


# --- (e) analysis evidence survives intact -----------------------------------
def test_e_analysis_evidence_is_still_produced_when_unvalidated() -> None:
    """Suppressing the evidence would be a different bug. EV and the distribution
    stay computed and readable; only the authority to recommend is withheld."""
    evidence = build_analysis_market_evidence(
        fixture_id=FIXTURE_ID,
        competition_id="la_liga",
        market="TOTALS",
        selection="UNDER",
        line="3.5",
        quote_identity_audit={},
        simulation=_simulation("BASELINE_PRIOR"),
    )
    assert evidence["calibration_status"] == "BASELINE_PRIOR"
    assert evidence["calibration_recommendation_admissible"] is False
    assert evidence["model_probability"] is not None
    assert evidence["fixture_id"] == FIXTURE_ID


def test_e_the_decision_record_now_declares_its_calibration() -> None:
    """The production record for 1570340 carried no calibration field at all, so a
    reviewer could not tell what the delivered recommendation rested on.

    This asserts on a denominator-scoped evaluation so `gate_results` is actually
    populated. The earlier form of this test read
    `gate_results is None or "calibration_validated" in gate_results`, which passed
    without checking anything whenever the gate map was absent.
    """
    version = classify_evaluation(
        DynamicEvaluationInput(
            fixture_id=FIXTURE_ID,
            market="TOTALS",
            selection="UNDER",
            exact_line=EXACT_LINE,
            bookmaker_id="book-1",
            capture_id="capture-1",
            quote_identity_hash="q" * 64,
            model_input_hash="m" * 64,
            evaluated_at=NOW,
            checkpoint="T-30m_VALIDATION_LOCK",
            capture_at=NOW,
            model_probability=0.70,
            market_probability=0.50,
            expected_value=0.20,
            ev_se=0.05,
            decimal_odds=DECIMAL_ODDS,
            bookmaker_count=7,
            mainline_parsed=True,
            denominator_scope="CHECKPOINT_EVALUATION_OPPORTUNITY_V2",
            calibration_status="BASELINE_PRIOR",
        )
    )
    assert version.gate_results is not None
    assert version.gate_results["calibration_validated"] is False
    assert version.calibration_status == "BASELINE_PRIOR"
    assert version.calibration_recommendation_admissible is False
    assert version.calibration_authority == calibration_authority.AUTHORITY_VERSION


def test_e_no_ev_cap_was_introduced() -> None:
    """A cap would hide an uncalibrated probability behind a threshold fitted to
    this fixture. The EV passes through untouched at any magnitude."""
    version = classify_evaluation(
        _evaluation(calibration_status="PRODUCTION_VALIDATED", ev=9.99, delta=0.9)
    )
    assert version.current_ev == pytest.approx(9.99)
    assert version.state is DynamicEvaluationState.ANALYSIS_PICK_ACTIVE
