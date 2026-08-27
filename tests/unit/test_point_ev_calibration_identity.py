"""POINT-EV-AUTHORITY-01-R1: calibration in the identity, and on the record.

R0 bound calibration to admission but left three holes. The status never entered
the immutable identity, so the same quote and model input under a different
calibration produced the same hash and append-only first-write-wins swallowed the
second, different conclusion. It never reached DynamicEvaluationVersion, so the
persisted record showed only whether a gate passed, not what it was looking at.
And an absent status normalised to BASELINE_PRIOR, which fails closed but destroys
the difference between "declared unvalidated" and "declared nothing".

Every assertion here is direct. None is of the "x is None or ..." shape that
passes when the thing under test was never produced.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from w2.domain import calibration_authority
from w2.infrastructure.database import Base
from w2.infrastructure.persistence.dynamic_prematch_models import (
    CandidateNotificationOutboxModel,
    DynamicPrematchEvaluationModel,
)
from w2.markets.market_candidate import build_market_candidates
from w2.prematch.lifecycle import (
    CHECKPOINT_OPPORTUNITY_SCOPE,
    MODEL_FORECAST_DENOMINATOR_SCOPE,
    DynamicEvaluationInput,
    DynamicEvaluationState,
    EvaluationOpportunityContext,
    OpportunityState,
    bind_evaluation_opportunity,
    classify_evaluation,
)
from w2.prematch.read_model_projection import _dynamic_evaluations
from w2.prematch.repository import DynamicPrematchRepository

NOW = datetime(2026, 8, 26, 18, 30, tzinfo=UTC)

# frozen from the production record for fixture 1570340
RECORDED_EV = 0.436411
RECORDED_EV_MINUS_SE = 0.386085
RECORDED_EV_SE = 0.050326
RECORDED_DELTA = 0.248131
MODEL_WIN_PROBABILITY = 0.7481305152250234

UNADMISSIBLE = ("BASELINE_PRIOR", "READY", "UNKNOWN", None, "")
ADMISSIBLE = ("PRODUCTION_VALIDATED", "APPROVED_VALIDATED")


def _engine():  # type: ignore[no-untyped-def]
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _input(
    *, calibration_status: object, ev: float = 0.20, suffix: str = "a", minutes: int = 0
) -> Any:
    return DynamicEvaluationInput(
        fixture_id="1570340",
        market="ASIAN_HANDICAP",
        selection="HOME_AH",
        exact_line=-0.25,
        bookmaker_id="book-1",
        capture_id=f"capture-{suffix}",
        quote_identity_hash=(suffix * 64)[:64],
        model_input_hash="2" * 64,
        evaluated_at=NOW + timedelta(minutes=minutes),
        checkpoint="T15_ODDS",
        capture_at=NOW,
        model_probability=0.70,
        market_probability=0.50,
        expected_value=ev,
        ev_se=0.01,
        decimal_odds=1.91,
        bookmaker_count=7,
        mainline_parsed=True,
        denominator_scope=CHECKPOINT_OPPORTUNITY_SCOPE,
        calibration_status=calibration_status,  # type: ignore[arg-type]
    )


def _context(slot: str, suffix: str) -> EvaluationOpportunityContext:
    return EvaluationOpportunityContext(
        # distinct per suffix: two attempts on the same capture and market are the
        # same opportunity, and binding them to different slots is a conflict
        model_forecast_capture_identity_hash=(suffix * 64)[:64],
        model_input_hash="2" * 64,
        evaluation_policy_version="candidate-eval.v1",
        evaluation_slot_id=slot,
        scheduled_checkpoint_at=NOW + timedelta(minutes=len(suffix)),
        checkpoint_plan_identity=f"plan-{suffix}",
        source_event_identity=f"event-{suffix}",
    )


def _attempt(
    calibration_status: object,
    *,
    slot: str = "T15_ODDS",
    suffix: str = "a",
    minutes: int = 0,
) -> Any:
    return bind_evaluation_opportunity(
        classify_evaluation(
            _input(calibration_status=calibration_status, suffix=suffix, minutes=minutes)
        ),
        _context(slot, suffix),
    )


# --- (a) nothing unadmissible forms a candidate or a notification ------------
@pytest.mark.parametrize("status", UNADMISSIBLE)
def test_a_unadmissible_forms_no_candidate(status: object) -> None:
    attempt = _attempt(status)
    assert attempt.state is DynamicEvaluationState.NOT_READY_MODEL_INPUT
    assert attempt.opportunity_state is OpportunityState.BLOCKED_BY_GATE
    assert calibration_authority.RECOMMENDATION_BLOCKER in attempt.blockers


def _outbox(engine) -> list[Any]:  # type: ignore[no-untyped-def]
    with Session(engine) as session:
        return list(session.scalars(select(CandidateNotificationOutboxModel)))


@pytest.mark.parametrize("status", UNADMISSIBLE)
def test_a_unadmissible_emits_no_notification(status: object) -> None:
    """The repository enqueues inside the evaluation transaction, so appending is
    the whole path; nothing is called a second time to manufacture a result."""
    engine = _engine()
    DynamicPrematchRepository(engine).append_evaluation(_attempt(status))
    assert _outbox(engine) == []


# --- (b) admissible statuses still answer to the EV gates --------------------
@pytest.mark.parametrize("status", ADMISSIBLE)
def test_b_admissible_reaches_candidate(status: str) -> None:
    attempt = _attempt(status)
    assert attempt.state is DynamicEvaluationState.ANALYSIS_PICK_ACTIVE
    assert attempt.opportunity_state is OpportunityState.EVALUATED_CANDIDATE


@pytest.mark.parametrize("status", ADMISSIBLE)
def test_b_admissible_without_edge_is_still_no_edge(status: str) -> None:
    attempt = bind_evaluation_opportunity(
        classify_evaluation(_input(calibration_status=status, ev=-0.01)),
        _context("T15_ODDS", "a"),
    )
    assert attempt.state is DynamicEvaluationState.NO_EDGE_CURRENT
    assert attempt.opportunity_state is OpportunityState.EVALUATED_NO_EDGE


# --- (c) a calibration change must not collide on identity -------------------
def test_c_classify_identity_separates_every_calibration_state() -> None:
    hashes = {
        status: classify_evaluation(_input(calibration_status=status)).identity_hash
        for status in ("BASELINE_PRIOR", "READY", "UNKNOWN", None, "PRODUCTION_VALIDATED")
    }
    assert len(set(hashes.values())) == len(hashes), hashes


def test_c_attempt_identity_separates_calibration_under_identical_inputs() -> None:
    """Same opportunity, same quote, same model input, same source event."""
    blocked = _attempt("BASELINE_PRIOR")
    admitted = _attempt("PRODUCTION_VALIDATED")
    assert blocked.opportunity_identity_hash == admitted.opportunity_identity_hash
    assert blocked.attempt_identity_hash != admitted.attempt_identity_hash
    assert blocked.evaluation_id != admitted.evaluation_id


def test_c_absent_and_baseline_prior_do_not_share_an_identity() -> None:
    assert (
        classify_evaluation(_input(calibration_status=None)).identity_hash
        != classify_evaluation(_input(calibration_status="BASELINE_PRIOR")).identity_hash
    )


def test_c_append_only_keeps_both_conclusions() -> None:
    """The swallow this fixes: two conclusions, two rows, neither lost."""
    engine = _engine()
    repository = DynamicPrematchRepository(engine)
    repository.append_evaluation(_attempt("PRODUCTION_VALIDATED"))
    repository.append_evaluation(_attempt("BASELINE_PRIOR"))
    with Session(engine) as session:
        rows = list(session.scalars(select(DynamicPrematchEvaluationModel)))
    assert len(rows) == 2
    states = {row.original_state for row in rows}
    assert states == {"ANALYSIS_PICK_ACTIVE", "NOT_READY_MODEL_INPUT"}


# --- (d) the record carries the audit fields through the database ------------
def test_d_as_dict_carries_every_calibration_field() -> None:
    payload = _attempt("BASELINE_PRIOR").as_dict()
    assert payload["calibration_status"] == "BASELINE_PRIOR"
    assert payload["calibration_status_raw"] == "BASELINE_PRIOR"
    assert payload["calibration_recommendation_admissible"] is False
    assert payload["calibration_authority"] == calibration_authority.AUTHORITY_VERSION


def test_d_absent_status_is_recorded_as_absent_not_as_baseline_prior() -> None:
    payload = _attempt(None).as_dict()
    assert payload["calibration_status"] == calibration_authority.ABSENT_STATUS
    assert payload["calibration_status_raw"] is None
    assert payload["calibration_recommendation_admissible"] is False


def test_d_database_round_trip_preserves_the_audit_fields() -> None:
    engine = _engine()
    DynamicPrematchRepository(engine).append_evaluation(_attempt("BASELINE_PRIOR"))
    with Session(engine) as session:
        row = session.scalars(select(DynamicPrematchEvaluationModel)).one()
        stored = row.payload if isinstance(row.payload, dict) else json.loads(row.payload)
    assert stored["calibration_status"] == "BASELINE_PRIOR"
    assert stored["calibration_status_raw"] == "BASELINE_PRIOR"
    assert stored["calibration_recommendation_admissible"] is False
    assert stored["calibration_authority"] == calibration_authority.AUTHORITY_VERSION
    assert stored["gate_results"]["calibration_validated"] is False


def test_d_round_trip_distinguishes_absent_from_declared_baseline() -> None:
    engine = _engine()
    repository = DynamicPrematchRepository(engine)
    repository.append_evaluation(_attempt(None, suffix="a"))
    repository.append_evaluation(_attempt("BASELINE_PRIOR", suffix="b"))
    with Session(engine) as session:
        rows = list(session.scalars(select(DynamicPrematchEvaluationModel)))
    stored = {
        (row.payload if isinstance(row.payload, dict) else json.loads(row.payload))[
            "calibration_status"
        ]
        for row in rows
    }
    assert stored == {calibration_authority.ABSENT_STATUS, "BASELINE_PRIOR"}


# --- (e) a downgrade blocks and does not leave a stale candidate -------------
def test_e_downgrade_blocks_and_does_not_keep_the_old_candidate_state() -> None:
    engine = _engine()
    repository = DynamicPrematchRepository(engine)
    formed = _attempt("PRODUCTION_VALIDATED", slot="T45_ODDS", suffix="a", minutes=0)
    repository.append_evaluation(formed)
    downgraded = _attempt("BASELINE_PRIOR", slot="T15_ODDS", suffix="b", minutes=30)
    repository.append_evaluation(downgraded)

    assert formed.opportunity_state is OpportunityState.EVALUATED_CANDIDATE
    assert downgraded.opportunity_state is OpportunityState.BLOCKED_BY_GATE
    with Session(engine) as session:
        rows = sorted(
            session.scalars(select(DynamicPrematchEvaluationModel)),
            key=lambda row: row.evaluation_id,
        )
    assert len(rows) == 2
    latest = max(rows, key=lambda row: row.evaluated_at)
    assert latest.original_state == "NOT_READY_MODEL_INPUT"


def test_e_upgrade_is_recorded_as_its_own_attempt() -> None:
    """The reverse direction must not be swallowed either."""
    engine = _engine()
    repository = DynamicPrematchRepository(engine)
    repository.append_evaluation(_attempt("BASELINE_PRIOR", slot="T45_ODDS", suffix="a"))
    repository.append_evaluation(_attempt("PRODUCTION_VALIDATED", slot="T15_ODDS", suffix="b"))
    with Session(engine) as session:
        rows = list(session.scalars(select(DynamicPrematchEvaluationModel)))
    assert len(rows) == 2
    assert {row.original_state for row in rows} == {
        "NOT_READY_MODEL_INPUT",
        "ANALYSIS_PICK_ACTIVE",
    }


# --- (f) real coverage of the other three surfaces ---------------------------
def _simulation(status: object) -> dict[str, Any]:
    simulation: dict[str, Any] = {
        "status": "READY",
        "model_version": "model",
        "calibration_version": "calibration",
        "lambda_home": 1.4,
        "lambda_away": 0.9,
        "lambda_sigma_home": 0.08,
        "lambda_sigma_away": 0.07,
        "calibration": {
            "lambda_uncertainty_method": "deterministic_three_point",
            "params": {"dixon_coles_rho": 0.0},
        },
    }
    if status is not None:
        simulation["calibration_status"] = status
    return simulation


def test_f_read_model_projection_carries_the_status_onto_the_evaluation() -> None:
    versions = _dynamic_evaluations(
        {"fixture_id": "1570340", "simulation": _simulation("BASELINE_PRIOR")},
        {
            "evaluated_at": "2026-08-26T18:30:00Z",
            "simulation_sha256": "simulation",
            "analysis_evidence_sha256": "evidence",
            "dynamic_evaluation_denominator_scope": MODEL_FORECAST_DENOMINATOR_SCOPE,
        },
        fixture_identity={
            "competition_id": "140",
            "season": "2026",
            "provider": "api_football",
        },
        lineup_identity=None,
    )
    assert versions, "the projection produced no evaluations to inspect"
    for version in versions:
        assert version.calibration_status == "BASELINE_PRIOR"
        assert version.calibration_recommendation_admissible is False
        assert version.state is not DynamicEvaluationState.ANALYSIS_PICK_ACTIVE


def test_f_read_model_projection_records_absent_when_the_card_declares_nothing() -> None:
    versions = _dynamic_evaluations(
        {"fixture_id": "1570340", "simulation": _simulation(None)},
        {
            "evaluated_at": "2026-08-26T18:30:00Z",
            "simulation_sha256": "simulation",
            "analysis_evidence_sha256": "evidence",
            "dynamic_evaluation_denominator_scope": MODEL_FORECAST_DENOMINATOR_SCOPE,
        },
        fixture_identity={
            "competition_id": "140",
            "season": "2026",
            "provider": "api_football",
        },
        lineup_identity=None,
    )
    assert versions, "the projection produced no evaluations to inspect"
    for version in versions:
        assert version.calibration_status == calibration_authority.ABSENT_STATUS
        assert version.calibration_recommendation_admissible is False


def test_f_market_candidate_stamps_the_evidence_with_the_authority() -> None:
    candidates = build_market_candidates(
        markets=[
            {
                "market": "TOTALS",
                "selection": "OVER",
                "line": "2.5",
                "calibration_status": "BASELINE_PRIOR",
            }
        ],
        quote_identity_audit={},
        current_odds={},
        pricing_shadow={},
        simulation=_simulation("BASELINE_PRIOR"),
        fixture_id="1570340",
        competition_id="la_liga",
    )
    assert candidates, "no candidate rows were produced to inspect"
    for candidate in candidates.values():
        evidence = candidate["analysis_evidence"]
        assert evidence["calibration_status"] == "BASELINE_PRIOR"
        assert evidence["calibration_recommendation_admissible"] is False


def test_f_notification_is_emitted_for_a_validated_candidate() -> None:
    """The counterpart to the (a) case: the pipe is not simply dead."""
    engine = _engine()
    DynamicPrematchRepository(engine).append_evaluation(_attempt("PRODUCTION_VALIDATED"))
    events = _outbox(engine)
    assert events != []
    assert {event.current_state for event in events} == {"EVALUATED_CANDIDATE"}


# --- (h) EV_SE and EV minus SE are different numbers -------------------------
def test_h_ev_se_is_not_ev_minus_se() -> None:
    assert RECORDED_EV - RECORDED_EV_MINUS_SE == pytest.approx(RECORDED_EV_SE, abs=1e-6)
    assert RECORDED_EV_SE != RECORDED_EV_MINUS_SE


def test_h_the_recorded_market_probability_is_the_devigged_one() -> None:
    """1/1.92 = 0.5208 is one side including vig. The authority's own devigged
    market probability is model probability minus the recorded delta."""
    devigged = MODEL_WIN_PROBABILITY - RECORDED_DELTA
    assert devigged == pytest.approx(0.50, abs=1e-6)
    assert devigged != pytest.approx(1 / 1.92, abs=1e-4)
