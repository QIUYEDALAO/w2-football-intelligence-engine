from __future__ import annotations

from copy import deepcopy
from decimal import Decimal

import pytest

from w2.domain.canonical_serialization import CURRENT_SERIALIZER_VERSION
from w2.domain.recommendation_decision_v4 import (
    IDENTITY_REQUIRED_FIELDS,
    RECOMMENDATION_SCHEMA_VERSION,
    RecommendationOutcomeV4,
    build_recommendation_decision_v4,
    candidate_identity_hash,
    validate_decision_v4_identity,
)


def _authoritative_input() -> dict[str, object]:
    payload: dict[str, object] = {
        "fixture_id": "fixture-1",
        "competition_id": "allsvenskan",
        "season": "2026",
        "kickoff_utc": "2026-08-08T15:30:00Z",
        "kickoff_revision_or_fixture_identity_hash": "d" * 64,
        "provider": "api-football",
        "bookmaker_id": "unibet",
        "market": "ASIAN_HANDICAP",
        "selection": "AWAY",
        "exact_line": "0.5",
        "capture_id": "capture-1",
        "captured_at": "2026-08-08T15:00:00Z",
        "decision_evaluated_at": "2026-08-08T15:10:00Z",
        "quote_observation_ids": {"home": "observation-home", "away": "observation-away"},
        "raw_payload_sha256": "a" * 64,
        "source_revision": "e" * 40,
        "model_version": "model-v1",
        "calibration_version": "calibration-v1",
        "serializer_version": CURRENT_SERIALIZER_VERSION.value,
        "recommendation_schema_version": RECOMMENDATION_SCHEMA_VERSION,
        "quote_schema_version": "w2.quote_identity.v1",
        "model_input_manifest_hash": "b" * 64,
        "decimal_odds": "1.6",
        "canonical_mainline_identity": {
            "market": "ASIAN_HANDICAP",
            "line": "-0.5",
            "selected_side_line": "0.5",
            "candidate_role": "MARKET_MAINLINE",
            "quote_identity_hash": "c" * 64,
        },
        "settlement_distribution": {
            "WIN": "0.5",
            "HALF_WIN": "0.1",
            "PUSH": "0.1",
            "HALF_LOSS": "0.1",
            "LOSS": "0.2",
        },
        "fair_odds": "1.4545",
        "expected_value": "0.08",
        "uncertainty": "0.01",
        "readiness": {
            "status": "READY",
            "quote_identity_status": "COMPLETE",
            "quote_freshness_status": "COMPLETE",
            "quote_freshness_policy_version": "w2.quote_freshness.v1",
            "quote_age_seconds": 600,
            "quote_max_age_seconds": 1800,
            "model_status": "READY",
        },
        "capability_status": "FORMAL_ENABLED",
        "formal_admission": {
            "status": "PASSED",
            "readiness_hash": "f" * 64,
            "approval_hash": "1" * 64,
            "candidate_identity_hash": None,
        },
        "model_probability": "0.625",
        "market_probability": "0.52",
        "probability_delta_diagnostic": "0.105",
    }
    formal = payload["formal_admission"]
    assert isinstance(formal, dict)
    formal["candidate_identity_hash"] = candidate_identity_hash(payload)
    return payload


_IDENTITY_MUTATIONS: dict[str, object] = {
    "fixture_id": "fixture-2",
    "competition_id": "eliteserien",
    "season": "2027",
    "kickoff_utc": "2026-08-08T16:30:00Z",
    "kickoff_revision_or_fixture_identity_hash": "2" * 64,
    "provider": "provider-2",
    "bookmaker_id": "bookmaker-2",
    "market": "TOTALS",
    "selection": "HOME",
    "exact_line": "0.75",
    "capture_id": "capture-2",
    "captured_at": "2026-08-08T15:01:00Z",
    "decision_evaluated_at": "2026-08-08T15:11:00Z",
    "quote_observation_ids": {"home": "observation-home-2", "away": "observation-away"},
    "raw_payload_sha256": "c" * 64,
    "source_revision": "3" * 40,
    "model_version": "model-v2",
    "calibration_version": "calibration-v2",
    "serializer_version": "w2.canonical-json.future",
    "recommendation_schema_version": "w2.recommendation_decision.future",
    "quote_schema_version": "w2.quote_identity.v2",
    "model_input_manifest_hash": "d" * 64,
}


def test_v4_is_complete_recomputable_and_uses_five_state_cashflow_edge() -> None:
    decision = build_recommendation_decision_v4(_authoritative_input())

    assert decision.outcome is RecommendationOutcomeV4.FORMAL_RECOMMEND
    assert Decimal(decision.authoritative_input.payload["cashflow_price_edge"]) == (
        Decimal("1.6") / Decimal("1.4545") - 1
    )
    assert decision.selected_candidate is not None
    assert decision.selected_candidate["selection"] == "AWAY"
    assert decision.selected_candidate["model_probability"] == "0.625"
    assert decision.selected_candidate["market_probability"] == "0.52"
    assert validate_decision_v4_identity(decision) == decision.decision_hash


@pytest.mark.parametrize("field", IDENTITY_REQUIRED_FIELDS)
def test_each_required_identity_field_changes_decision_hash(field: str) -> None:
    original = _authoritative_input()
    mutated = deepcopy(original)
    mutated[field] = _IDENTITY_MUTATIONS[field]

    assert (
        build_recommendation_decision_v4(mutated).decision_hash
        != build_recommendation_decision_v4(original).decision_hash
    )


@pytest.mark.parametrize("field", IDENTITY_REQUIRED_FIELDS)
def test_missing_required_identity_field_is_not_ready(field: str) -> None:
    payload = _authoritative_input()
    payload.pop(field)

    decision = build_recommendation_decision_v4(payload)

    assert decision.outcome is RecommendationOutcomeV4.NOT_READY
    assert f"MISSING_{field.upper()}" in decision.blockers


def test_not_ready_reason_distinguishes_fixture_model_and_quote_truth() -> None:
    fixture_missing = _authoritative_input()
    fixture_missing["season"] = None
    assert build_recommendation_decision_v4(fixture_missing).reason_code == "IDENTITY_NOT_READY"

    model_missing = _authoritative_input()
    readiness = model_missing["readiness"]
    assert isinstance(readiness, dict)
    readiness["model_status"] = "NOT_READY"
    readiness["status"] = "NOT_READY"
    assert build_recommendation_decision_v4(model_missing).reason_code == "EVIDENCE_NOT_READY"

    quote_missing = _authoritative_input()
    quote_readiness = quote_missing["readiness"]
    assert isinstance(quote_readiness, dict)
    quote_readiness["quote_identity_status"] = "INCOMPLETE"
    quote_readiness["status"] = "NOT_READY"
    assert (
        build_recommendation_decision_v4(quote_missing).reason_code
        == "QUOTE_IDENTITY_NOT_READY"
    )


def test_new_decision_must_be_formed_before_kickoff() -> None:
    payload = _authoritative_input()
    payload["decision_evaluated_at"] = payload["kickoff_utc"]

    decision = build_recommendation_decision_v4(payload)

    assert decision.outcome is RecommendationOutcomeV4.NOT_READY
    assert decision.reason_code == "FIXTURE_NOT_PREMATCH"
    assert "DECISION_NOT_BEFORE_KICKOFF" in decision.blockers


def test_candidate_quote_age_boundary_is_independent_and_hashed() -> None:
    accepted = _authoritative_input()
    accepted_readiness = accepted["readiness"]
    assert isinstance(accepted_readiness, dict)
    accepted_readiness["quote_age_seconds"] = 1800
    accepted_decision = build_recommendation_decision_v4(accepted)

    rejected = _authoritative_input()
    rejected_readiness = rejected["readiness"]
    assert isinstance(rejected_readiness, dict)
    rejected_readiness["quote_age_seconds"] = 1801
    rejected_decision = build_recommendation_decision_v4(rejected)

    assert accepted_decision.outcome is RecommendationOutcomeV4.FORMAL_RECOMMEND
    assert rejected_decision.outcome is RecommendationOutcomeV4.NOT_READY
    assert "QUOTE_FRESHNESS_BOUNDARY_INVALID" in rejected_decision.blockers
    assert accepted_decision.decision_hash != rejected_decision.decision_hash


def test_decision_evaluation_time_is_part_of_v4_identity() -> None:
    original = _authoritative_input()
    changed = deepcopy(original)
    changed["decision_evaluated_at"] = "2026-08-08T15:11:00Z"

    assert (
        build_recommendation_decision_v4(changed).decision_hash
        != build_recommendation_decision_v4(original).decision_hash
    )


def test_declared_fair_odds_and_ev_must_reconcile_with_five_state_distribution() -> None:
    payload = _authoritative_input()
    payload["fair_odds"] = "1.50"
    payload["expected_value"] = "0.09"

    decision = build_recommendation_decision_v4(payload)

    assert decision.outcome is RecommendationOutcomeV4.NOT_READY
    assert {"FAIR_ODDS_CONFLICT", "EXPECTED_VALUE_CONFLICT"} <= set(decision.blockers)


def test_tampered_v4_payload_cannot_validate_against_original_identity() -> None:
    payload = build_recommendation_decision_v4(_authoritative_input()).as_dict()
    authoritative = payload["authoritative_input"]
    assert isinstance(authoritative, dict)
    authoritative["capture_id"] = "capture-tampered"

    with pytest.raises(ValueError, match="DECISION_V4_IDENTITY_CONFLICT"):
        validate_decision_v4_identity(payload)


@pytest.mark.parametrize(
    ("field", "value", "blocker"),
    [
        ("source_revision", "a" * 39, "INVALID_SOURCE_REVISION"),
        ("source_revision", "A" * 40, "INVALID_SOURCE_REVISION"),
        ("source_revision", "g" * 40, "INVALID_SOURCE_REVISION"),
        ("source_revision", f"{'a' * 40} ", "INVALID_SOURCE_REVISION"),
        (
            "kickoff_revision_or_fixture_identity_hash",
            "a" * 63,
            "INVALID_KICKOFF_REVISION_OR_FIXTURE_IDENTITY_HASH",
        ),
        (
            "kickoff_revision_or_fixture_identity_hash",
            "A" * 64,
            "INVALID_KICKOFF_REVISION_OR_FIXTURE_IDENTITY_HASH",
        ),
        (
            "kickoff_revision_or_fixture_identity_hash",
            "g" * 64,
            "INVALID_KICKOFF_REVISION_OR_FIXTURE_IDENTITY_HASH",
        ),
        (
            "kickoff_revision_or_fixture_identity_hash",
            f"{'a' * 64} ",
            "INVALID_KICKOFF_REVISION_OR_FIXTURE_IDENTITY_HASH",
        ),
    ],
)
def test_revision_identity_formats_fail_closed(field: str, value: str, blocker: str) -> None:
    payload = _authoritative_input()
    payload[field] = value

    decision = build_recommendation_decision_v4(payload)

    assert decision.outcome is RecommendationOutcomeV4.NOT_READY
    assert blocker in decision.blockers


@pytest.mark.parametrize("value", ["c" * 63, "C" * 64, "g" * 64, f"{'c' * 64} "])
def test_quote_identity_hash_format_fails_closed(value: str) -> None:
    payload = _authoritative_input()
    mainline = payload["canonical_mainline_identity"]
    assert isinstance(mainline, dict)
    mainline["quote_identity_hash"] = value

    decision = build_recommendation_decision_v4(payload)

    assert decision.outcome is RecommendationOutcomeV4.NOT_READY
    assert "INVALID_QUOTE_IDENTITY_HASH" in decision.blockers


def test_capability_without_passed_formal_admission_remains_analysis_only() -> None:
    payload = _authoritative_input()
    payload["formal_admission"] = {
        "status": "NOT_READY",
        "readiness_hash": None,
        "approval_hash": None,
        "candidate_identity_hash": None,
    }

    decision = build_recommendation_decision_v4(payload)

    assert decision.outcome is RecommendationOutcomeV4.ANALYSIS_PICK


def test_formal_candidate_identity_mismatch_fails_closed() -> None:
    payload = _authoritative_input()
    admission = payload["formal_admission"]
    assert isinstance(admission, dict)
    admission["candidate_identity_hash"] = "9" * 64

    decision = build_recommendation_decision_v4(payload)

    assert decision.outcome is RecommendationOutcomeV4.NOT_READY
    assert "FORMAL_CANDIDATE_IDENTITY_MISMATCH" in decision.blockers


def test_all_admission_gates_insufficient_is_no_edge_without_selected_candidate() -> None:
    payload = _authoritative_input()
    payload["decimal_odds"] = "1.5"
    payload["expected_value"] = "0.025"
    payload["formal_admission"] = {
        "status": "NOT_READY",
        "readiness_hash": None,
        "approval_hash": None,
        "candidate_identity_hash": None,
    }

    decision = build_recommendation_decision_v4(payload)

    assert decision.outcome is RecommendationOutcomeV4.NO_EDGE
    assert decision.selected_candidate is None
