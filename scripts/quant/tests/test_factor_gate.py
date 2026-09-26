"""Task B minimum test matrix: the AH factor verdict must gate candidacy."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from w2.prematch.lifecycle import (
    DynamicEvaluationInput,
    DynamicEvaluationState,
    OpportunityState,
    classify_evaluation,
    factor_blocker,
)

NOW = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)


# A well-formed factor identity: 64 lowercase hex, and the same value in both
# fields, which is what read_model_projection._factor_verdict produces.
_GOOD_IDENTITY = "f" * 64


def _input(**overrides) -> DynamicEvaluationInput:
    base = dict(
        fixture_id="1", market="ASIAN_HANDICAP", selection="HOME", exact_line=0.25,
        bookmaker_id="bm", capture_id="cap", quote_identity_hash="qh",
        model_input_hash="mh", evaluated_at=NOW, checkpoint="T-30m",
        calibration_status="APPROVED_VALIDATED",
        model_probability=0.6, market_probability=0.5,
        expected_value=0.3, ev_se=0.1, cashflow_price_edge=0.3,
        decimal_odds=1.95, mainline_parsed=True, bookmaker_count=3,
        denominator_scope="CHECKPOINT_OPPORTUNITY",
        # A factor verdict that permits the pick.
        factor_decision_status="ADMITTED", factor_direction="HOME",
        ev_direction="HOME", factor_veto_code=None,
        factor_input_identity=_GOOD_IDENTITY, factor_input_identity_hash=_GOOD_IDENTITY,
    )
    base.update(overrides)
    return DynamicEvaluationInput(**base)


def _state(**overrides) -> DynamicEvaluationState:
    return classify_evaluation(_input(**overrides)).state


# 1-3: each blocking code must stop candidacy even when economics pass.
@pytest.mark.parametrize("code", [
    "FACTOR_SCORE_UNAVAILABLE", "FACTOR_ADMISSION_FAILED", "FACTOR_EV_DIRECTION_CONFLICT",
])
def test_blocking_codes_block_despite_positive_economics(code):
    version = classify_evaluation(_input(factor_veto_code=code))
    assert version.state is DynamicEvaluationState.BLOCKED_BY_FACTOR
    assert code in version.blockers


def test_absent_factor_verdict_fails_closed():
    assert _state(factor_decision_status=None, factor_input_identity=None) is \
        DynamicEvaluationState.BLOCKED_BY_FACTOR


def test_direction_conflict_detected_without_an_explicit_code():
    assert _state(factor_direction="AWAY", ev_direction="HOME") is \
        DynamicEvaluationState.BLOCKED_BY_FACTOR


# 4: consistent factor + passing economics still becomes a candidate.
def test_consistent_factor_still_produces_candidate():
    assert _state() is DynamicEvaluationState.ANALYSIS_PICK_ACTIVE


# 5: TOTALS behaviour is untouched.
def test_totals_is_not_gated_by_the_factor():
    assert factor_blocker(_input(market="TOTALS", factor_decision_status=None,
                                 factor_input_identity=None,
                                 factor_input_identity_hash=None)) is None
    assert _state(market="TOTALS", selection="OVER", factor_decision_status=None,
                  factor_direction=None, ev_direction=None,
                  factor_input_identity=None,
                  factor_input_identity_hash=None) is (
        DynamicEvaluationState.NO_EDGE_CURRENT)


# 9: a blocked AH stays in the official funnel denominator as BLOCKED_BY_GATE.
def test_blocked_ah_stays_in_denominator_but_is_not_a_candidate():
    """The factor gate must not touch official_funnel_eligible.

    classify_evaluation leaves the field unset; the opportunity binding step
    sets it True for every state, so a blocked AH still counts in the funnel
    denominator. The gate only has to avoid a candidate state.
    """
    blocked = classify_evaluation(_input(factor_veto_code="FACTOR_EV_DIRECTION_CONFLICT"))
    allowed = classify_evaluation(_input())
    assert blocked.official_funnel_eligible == allowed.official_funnel_eligible
    assert blocked.state is DynamicEvaluationState.BLOCKED_BY_FACTOR
    assert blocked.state is not DynamicEvaluationState.ANALYSIS_PICK_ACTIVE
    assert blocked.state is not DynamicEvaluationState.NO_EDGE_CURRENT


# 10: historical payloads remain readable and are never treated as passing.
def test_historical_payload_without_factor_identity_is_not_a_pass():
    assert _state(factor_decision_status="HISTORICAL_NO_FACTOR_VERDICT_IDENTITY") is \
        DynamicEvaluationState.BLOCKED_BY_FACTOR


def test_blocked_state_is_not_one_of_the_two_candidate_states():
    """BLOCKED_BY_FACTOR must fall through to BLOCKED_BY_GATE downstream."""
    assert DynamicEvaluationState.BLOCKED_BY_FACTOR not in {
        DynamicEvaluationState.ANALYSIS_PICK_ACTIVE,
        DynamicEvaluationState.NO_EDGE_CURRENT,
    }
    assert OpportunityState.BLOCKED_BY_GATE.value == "BLOCKED_BY_GATE"


# --- R1/R2/R3: persistence, identity binding, real opportunity binding -------

from datetime import timedelta  # noqa: E402

from w2.prematch.lifecycle import (  # noqa: E402
    FACTOR_VERDICT_SCHEMA,
    EvaluationOpportunityContext,
    bind_evaluation_opportunity,
)

PROTECTED = ("factor_decision_status", "factor_direction", "ev_direction",
             "factor_veto_code", "factor_input_identity_hash")


def _with_verdict(**overrides):
    base = dict(factor_input_identity="a" * 64, factor_input_identity_hash="a" * 64,
                factor_evidence_digest={"participant_ids": ["F3", "F6", "F9"]})
    base.update(overrides)
    return _input(**base)


def test_factor_verdict_is_persisted_in_the_version_and_payload():
    version = classify_evaluation(_with_verdict())
    assert version.factor_verdict_schema == FACTOR_VERDICT_SCHEMA
    assert version.factor_decision_status == "ADMITTED"
    assert version.factor_input_identity_hash == "a" * 64
    payload = version.as_dict()
    for field in (*PROTECTED, "factor_verdict_schema", "factor_evidence_digest"):
        assert field in payload, f"{field} missing from the persisted payload"
    assert payload["factor_evidence_digest"]["participant_ids"] == ["F3", "F6", "F9"]


@pytest.mark.parametrize("field", PROTECTED)
def test_changing_any_protected_factor_field_changes_the_evaluation_identity(field):
    baseline = classify_evaluation(_with_verdict()).identity_hash
    mutated = {"factor_decision_status": "NOT_ADMITTED", "factor_direction": "AWAY",
               "ev_direction": "AWAY", "factor_veto_code": "FACTOR_ADMISSION_FAILED",
               "factor_input_identity_hash": "b" * 64}[field]
    assert classify_evaluation(_with_verdict(**{field: mutated})).identity_hash != baseline


def _context() -> EvaluationOpportunityContext:
    return EvaluationOpportunityContext(
        model_forecast_capture_identity_hash="c" * 64,
        model_input_hash="mh",
        evaluation_policy_version="candidate-eval.v2",
        evaluation_slot_id="T-30m_VALIDATION_LOCK",
        scheduled_checkpoint_at=NOW - timedelta(minutes=30),
        checkpoint_plan_identity="plan-1",
        source_event_identity="evt-1",
    )


@pytest.mark.parametrize("field", PROTECTED)
def test_changing_any_protected_factor_field_changes_the_attempt_identity(field):
    context = _context()
    baseline = bind_evaluation_opportunity(
        classify_evaluation(_with_verdict()), context).attempt_identity_hash
    mutated = {"factor_decision_status": "NOT_ADMITTED", "factor_direction": "AWAY",
               "ev_direction": "AWAY", "factor_veto_code": "FACTOR_ADMISSION_FAILED",
               "factor_input_identity_hash": "b" * 64}[field]
    other = bind_evaluation_opportunity(
        classify_evaluation(_with_verdict(**{field: mutated})), context)
    assert other.attempt_identity_hash != baseline


def test_verdictless_evaluation_keeps_its_historical_identity():
    """Absent verdict must not rewrite append-only history."""
    without = classify_evaluation(_input(
        market="TOTALS", selection="OVER", factor_decision_status=None,
        factor_direction=None, ev_direction=None, factor_veto_code=None,
        factor_input_identity=None, factor_input_identity_hash=None))
    assert without.factor_verdict_schema is None
    assert without.identity_hash


# 9 (rewritten as a real binding test, not an empty assertion)
def test_blocked_ah_binds_to_blocked_by_gate_and_stays_in_the_denominator():
    bound = bind_evaluation_opportunity(
        classify_evaluation(_with_verdict(factor_veto_code="FACTOR_EV_DIRECTION_CONFLICT")),
        _context())
    assert bound.official_funnel_eligible is True
    assert bound.opportunity_state is OpportunityState.BLOCKED_BY_GATE
    assert bound.opportunity_state is not OpportunityState.EVALUATED_CANDIDATE
    assert bound.state is DynamicEvaluationState.BLOCKED_BY_FACTOR


def test_consistent_factor_binds_to_evaluated_candidate():
    bound = bind_evaluation_opportunity(classify_evaluation(_with_verdict()), _context())
    assert bound.opportunity_state is OpportunityState.EVALUATED_CANDIDATE
    assert bound.official_funnel_eligible is True


# --- strict fail-closed: every way a verdict can fail to permit an AH pick ----
from w2.prematch.lifecycle import (  # noqa: E402
    FACTOR_ADMISSION_FAILED,
    FACTOR_EV_DIRECTION_CONFLICT,
    FACTOR_SCORE_UNAVAILABLE,
    FACTOR_VERDICT_MALFORMED,
    HISTORICAL_NO_FACTOR_VERDICT,
)

GOOD_IDENTITY = "f" * 64
ADMITTED_VERDICT = {
    "factor_decision_status": "ADMITTED",
    "factor_direction": "HOME",
    "factor_input_identity": GOOD_IDENTITY,
    "factor_input_identity_hash": GOOD_IDENTITY,
}


@pytest.mark.parametrize(
    ("label", "verdict", "expected"),
    [
        # no verdict at all, and the marker a pre-verdict payload reads back as
        (
            "absent",
            {"factor_decision_status": None, "factor_direction": None,
             "ev_direction": None, "factor_veto_code": None,
             "factor_input_identity": None, "factor_input_identity_hash": None},
            FACTOR_SCORE_UNAVAILABLE,
        ),
        (
            "historical",
            {**ADMITTED_VERDICT, "factor_decision_status": HISTORICAL_NO_FACTOR_VERDICT},
            FACTOR_SCORE_UNAVAILABLE,
        ),
        # deliberate refusals by the factor layer
        (
            "not_admitted",
            {**ADMITTED_VERDICT, "factor_decision_status": "NOT_ADMITTED"},
            FACTOR_ADMISSION_FAILED,
        ),
        (
            "vetoed_status_only",
            {**ADMITTED_VERDICT, "factor_decision_status": "VETOED"},
            FACTOR_ADMISSION_FAILED,
        ),
        # a recognised veto code survives verbatim
        (
            "vetoed_with_code",
            {**ADMITTED_VERDICT, "factor_decision_status": "VETOED",
             "factor_veto_code": FACTOR_EV_DIRECTION_CONFLICT},
            FACTOR_EV_DIRECTION_CONFLICT,
        ),
        # unusable verdicts
        (
            "garbage_status",
            {**ADMITTED_VERDICT, "factor_decision_status": "PROBABLY_FINE"},
            FACTOR_VERDICT_MALFORMED,
        ),
        (
            "garbage_veto_code",
            {**ADMITTED_VERDICT, "factor_veto_code": "LOOKS_OK_TO_ME"},
            FACTOR_VERDICT_MALFORMED,
        ),
        (
            "empty_direction",
            {**ADMITTED_VERDICT, "factor_direction": ""},
            FACTOR_VERDICT_MALFORMED,
        ),
        (
            "garbage_direction",
            {**ADMITTED_VERDICT, "factor_direction": "SIDEWAYS"},
            FACTOR_VERDICT_MALFORMED,
        ),
        (
            "identity_missing",
            {**ADMITTED_VERDICT, "factor_input_identity": None},
            FACTOR_VERDICT_MALFORMED,
        ),
        (
            "identity_hash_missing",
            {**ADMITTED_VERDICT, "factor_input_identity_hash": None},
            FACTOR_VERDICT_MALFORMED,
        ),
        (
            "identity_disagrees_with_hash",
            {**ADMITTED_VERDICT, "factor_input_identity_hash": "e" * 64},
            FACTOR_VERDICT_MALFORMED,
        ),
        (
            "identity_not_hex64",
            {**ADMITTED_VERDICT, "factor_input_identity": "not-a-hash",
             "factor_input_identity_hash": "not-a-hash"},
            FACTOR_VERDICT_MALFORMED,
        ),
        (
            "identity_uppercase_hex",
            {**ADMITTED_VERDICT, "factor_input_identity": "F" * 64,
             "factor_input_identity_hash": "F" * 64},
            FACTOR_VERDICT_MALFORMED,
        ),
        # a usable verdict pointing the other way
        (
            "direction_conflict",
            {**ADMITTED_VERDICT, "factor_direction": "AWAY"},
            FACTOR_EV_DIRECTION_CONFLICT,
        ),
    ],
)
def test_strict_fail_closed_blocks_every_non_admitted_verdict(label, verdict, expected) -> None:
    value = _input(selection="HOME", **verdict)

    assert factor_blocker(value) == expected, label
    assert classify_evaluation(value).state is DynamicEvaluationState.BLOCKED_BY_FACTOR


def test_only_a_complete_admitted_consistent_verdict_passes() -> None:
    value = _input(selection="HOME", **ADMITTED_VERDICT)

    assert factor_blocker(value) is None
    assert classify_evaluation(value).state is DynamicEvaluationState.ANALYSIS_PICK_ACTIVE


@pytest.mark.parametrize("selection", ["HOME", "HOME_AH", "home", "home_ah"])
def test_the_market_candidate_spelling_of_a_side_still_resolves(selection: str) -> None:
    """HOME_AH is the same side as HOME; recommendation_decision_v4 strips it too."""
    value = _input(selection=selection, **ADMITTED_VERDICT)

    assert factor_blocker(value) is None


def test_ev_direction_overrides_selection_when_both_are_present() -> None:
    """ev_direction is the side the EV actually chose; it wins over selection."""
    conflicting = _input(selection="HOME", ev_direction="AWAY", **ADMITTED_VERDICT)

    assert factor_blocker(conflicting) == FACTOR_EV_DIRECTION_CONFLICT


def test_totals_never_needs_a_verdict_under_the_strict_gate() -> None:
    empty = {"factor_decision_status": None, "factor_direction": None,
             "ev_direction": None, "factor_veto_code": None,
             "factor_input_identity": None, "factor_input_identity_hash": None}
    for verdict in (empty, {**empty, "factor_decision_status": "VETOED",
                            "factor_veto_code": FACTOR_EV_DIRECTION_CONFLICT}):
        value = _input(market="TOTALS", selection="OVER", **verdict)
        assert factor_blocker(value) is None
