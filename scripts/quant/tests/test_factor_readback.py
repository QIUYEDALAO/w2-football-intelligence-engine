"""The factor verdict must survive a real repository round-trip, and only it
may change an identity.

Two separate obligations. First, a duplicate append returns the stored row
rebuilt from its payload; if the rebuild drops the verdict, a caller reading
that return cannot tell a refused pick from one nothing ever judged. Second,
the verdict must not re-key anything that never had one: every TOTALS attempt
and every row written before the verdict existed keeps the attempt identity it
already has, which append-only requires.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine

from w2.infrastructure.database import Base
from w2.prematch.lifecycle import (
    ATTEMPT_IDENTITY_FACTOR_VERSION,
    ATTEMPT_IDENTITY_VERSION,
    CHECKPOINT_OPPORTUNITY_SCOPE,
    FACTOR_VERDICT_SCHEMA,
    HISTORICAL_NO_FACTOR_VERDICT,
    DynamicEvaluationInput,
    DynamicEvaluationState,
    EvaluationOpportunityContext,
    bind_evaluation_opportunity,
    classify_evaluation,
    factor_blocker,
)
from w2.prematch.repository import DynamicPrematchRepository, _version_from_payload

NOW = datetime(2026, 8, 20, 8, 0, tzinfo=UTC)
IDENTITY = "f" * 64
FACTOR_FIELDS = (
    "factor_verdict_schema",
    "factor_decision_status",
    "factor_direction",
    "ev_direction",
    "factor_veto_code",
    "factor_input_identity_hash",
    "factor_evidence_digest",
)
VERDICT = {
    "factor_decision_status": "VETOED",
    "factor_direction": "AWAY",
    "ev_direction": "HOME",
    "factor_veto_code": "FACTOR_EV_DIRECTION_CONFLICT",
    "factor_input_identity": IDENTITY,
    "factor_input_identity_hash": IDENTITY,
    "factor_evidence_digest": {"participant_ids": ["F3", "F6", "F9"], "weight_sum_used": 0.25},
}


def _engine():  # type: ignore[no-untyped-def]
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _input(**overrides) -> DynamicEvaluationInput:
    base = dict(
        fixture_id="1490401",
        market="ASIAN_HANDICAP",
        selection="HOME",
        exact_line=-0.25,
        bookmaker_id="book-1",
        capture_id="capture-a",
        quote_identity_hash="a" * 64,
        model_input_hash="2" * 64,
        evaluated_at=NOW,
        checkpoint="T15_ODDS",
        capture_at=NOW,
        model_probability=0.60,
        market_probability=0.50,
        expected_value=0.06,
        ev_se=0.01,
        cashflow_price_edge=0.10,
        decimal_odds=1.91,
        bookmaker_count=7,
        mainline_parsed=True,
        calibration_status="PRODUCTION_VALIDATED",
        denominator_scope=CHECKPOINT_OPPORTUNITY_SCOPE,
    )
    base.update(overrides)
    return DynamicEvaluationInput(**base)  # type: ignore[arg-type]


def _context(suffix: str = "golden") -> EvaluationOpportunityContext:
    return EvaluationOpportunityContext(
        model_forecast_capture_identity_hash="1" * 64,
        model_input_hash="2" * 64,
        evaluation_policy_version="candidate-eval.v1",
        evaluation_slot_id="T15_ODDS",
        scheduled_checkpoint_at=NOW,
        checkpoint_plan_identity=f"plan-{suffix}",
        source_event_identity=f"event-{suffix}",
    )


# --- 1-3: a real repository round-trip through the existing-row readback -----
def test_second_append_of_the_same_identity_returns_the_verdict_field_for_field() -> None:
    repository = DynamicPrematchRepository(_engine())
    original = bind_evaluation_opportunity(classify_evaluation(_input(**VERDICT)), _context())

    first, created_first = repository.append_evaluation(original)
    second, created_second = repository.append_evaluation(original)

    assert (created_first, created_second) == (True, False)
    # the second return came off the stored payload, not the object we passed in
    assert second is not original
    for field in FACTOR_FIELDS:
        assert getattr(second, field) == getattr(original, field), field
    assert second.factor_verdict_schema == FACTOR_VERDICT_SCHEMA
    assert second.factor_veto_code == "FACTOR_EV_DIRECTION_CONFLICT"
    assert second.factor_evidence_digest == VERDICT["factor_evidence_digest"]
    assert second.state is DynamicEvaluationState.BLOCKED_BY_FACTOR
    assert first.identity_hash == second.identity_hash


def test_readback_of_an_admitted_verdict_keeps_it_admitted() -> None:
    repository = DynamicPrematchRepository(_engine())
    admitted = bind_evaluation_opportunity(
        classify_evaluation(
            _input(
                factor_decision_status="ADMITTED",
                factor_direction="HOME",
                factor_input_identity=IDENTITY,
                factor_input_identity_hash=IDENTITY,
            )
        ),
        _context(),
    )
    repository.append_evaluation(admitted)

    rebuilt, created = repository.append_evaluation(admitted)

    assert created is False
    assert rebuilt.factor_decision_status == "ADMITTED"
    assert rebuilt.factor_direction == "HOME"
    assert rebuilt.factor_veto_code is None
    assert rebuilt.state is DynamicEvaluationState.ANALYSIS_PICK_ACTIVE


# --- 4: an old AH payload reads back as the explicit marker, never a pass ----
def test_old_ah_payload_without_the_verdict_reads_back_as_the_historical_marker() -> None:
    payload = classify_evaluation(_input()).as_dict()
    for field in FACTOR_FIELDS:
        payload.pop(field, None)

    rebuilt = _version_from_payload(payload)

    assert rebuilt.factor_decision_status == HISTORICAL_NO_FACTOR_VERDICT
    assert rebuilt.factor_verdict_schema is None
    assert rebuilt.factor_input_identity_hash is None
    # and the marker is not a pass: re-gating the rebuilt verdict blocks
    assert factor_blocker(_input(factor_decision_status=rebuilt.factor_decision_status)) == (
        "FACTOR_SCORE_UNAVAILABLE"
    )


# --- 5: an old TOTALS payload keeps working and needs no verdict ------------
def test_old_totals_payload_needs_no_verdict() -> None:
    totals = _input(market="TOTALS", selection="OVER", exact_line=2.25)
    payload = classify_evaluation(totals).as_dict()
    for field in FACTOR_FIELDS:
        payload.pop(field, None)

    rebuilt = _version_from_payload(payload)

    assert rebuilt.factor_decision_status is None
    assert rebuilt.state is DynamicEvaluationState.ANALYSIS_PICK_ACTIVE
    assert factor_blocker(totals) is None


# --- attempt identity: v2 for verdict-less, v3 only for factor-bearing ------
# Derived by running this exact fixture against the unmodified production
# baseline 3ac86c14 -- the commit this branch forked from -- and confirming the
# same value here. If the verdict ever re-keys a verdict-less attempt, this is
# the assertion that fails.
GOLDEN_VERDICTLESS_TOTALS_ATTEMPT = (
    "72110414f0a80392e5b140daec873fe8a3466f332679d6ea3a7bb23c5bc1c9aa"
)


def _verdictless_totals_attempt():  # type: ignore[no-untyped-def]
    value = _input(
        market="TOTALS",
        selection="OVER",
        exact_line=2.25,
        capture_id="capture-golden",
        calibration_status="PRODUCTION_VALIDATED",
    )
    return bind_evaluation_opportunity(classify_evaluation(value), _context())


def test_verdictless_totals_attempt_keeps_its_pre_factor_identity() -> None:
    bound = _verdictless_totals_attempt()

    assert bound.attempt_identity_hash == GOLDEN_VERDICTLESS_TOTALS_ATTEMPT
    assert bound.identity_hash == GOLDEN_VERDICTLESS_TOTALS_ATTEMPT


def test_a_verdict_bearing_attempt_uses_the_v3_preimage_and_a_different_identity() -> None:
    verdictless = _verdictless_totals_attempt()
    bearing = bind_evaluation_opportunity(
        classify_evaluation(_input(**VERDICT)), _context()
    )

    assert ATTEMPT_IDENTITY_VERSION.endswith(".v2")
    assert ATTEMPT_IDENTITY_FACTOR_VERSION.endswith(".v3")
    assert bearing.attempt_identity_hash != verdictless.attempt_identity_hash


@pytest.mark.parametrize(
    ("field", "mutation"),
    [
        ("factor_decision_status", "NOT_ADMITTED"),
        ("factor_direction", "HOME"),
        ("ev_direction", "AWAY"),
        ("factor_veto_code", "FACTOR_ADMISSION_FAILED"),
        ("factor_input_identity_hash", "b" * 64),
    ],
)
def test_any_of_the_five_verdict_fields_re_keys_the_v3_identities(field, mutation) -> None:
    context = _context()
    baseline_version = classify_evaluation(_input(**VERDICT))
    baseline_attempt = bind_evaluation_opportunity(baseline_version, context)
    mutated_version = classify_evaluation(_input(**{**VERDICT, field: mutation}))
    mutated_attempt = bind_evaluation_opportunity(mutated_version, context)

    assert mutated_version.identity_hash != baseline_version.identity_hash, field
    assert mutated_attempt.attempt_identity_hash != baseline_attempt.attempt_identity_hash, field
