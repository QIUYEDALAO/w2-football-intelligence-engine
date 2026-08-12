from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from types import SimpleNamespace

from w2.api.repository import _apply_repository_v4_authority
from w2.dashboard.day_view import build_dashboard_day_view
from w2.domain.recommendation_decision_v4 import (
    RecommendationOutcomeV4,
    build_recommendation_decision_v4,
    candidate_identity_hash,
)
from w2.prematch.analysis_calculator import (
    ReadModelService,
    _build_public_recommendation_decision_v4,
    _public_formal_admission,
    _recommendation_from_v4,
)


def _candidate() -> dict[str, object]:
    return {
        "market": "ASIAN_HANDICAP",
        "selection": "AWAY",
        "line": "0.5",
        "candidate_role": "MARKET_MAINLINE",
        "market_mainline": {"line": "-0.5", "selection_policy": "CANONICAL"},
        "quote_status": "COMPLETE",
        "quote_usage": "EXECUTABLE",
        "quotes": {
            "executable": {
                "line": "0.5",
                "decimal_odds": "1.6",
                "provider": "api-football",
                "bookmaker_id": "unibet",
                "capture_id": "capture-1",
                "captured_at": "2026-08-08T15:00:00Z",
            }
        },
        "quote_identity": {
            "schema_version": "w2.quote_identity.v1",
            "identity_status": "COMPLETE",
            "freshness_status": "COMPLETE",
            "provider": "api-football",
            "bookmaker_id": "unibet",
            "capture_id": "capture-1",
            "captured_at": "2026-08-08T15:00:00Z",
            "observation_ids": {
                "home": "observation-home",
                "away": "observation-away",
            },
            "raw_payload_sha256": "a" * 64,
            "source_revision": "d" * 40,
            "quote_identity_hash": "c" * 64,
        },
        "analysis_evidence": {
            "status": "COMPLETE",
            "model_probability": {
                "status": "READY",
                "model_version": "model-v1",
                "calibration_version": "calibration-v1",
                "model_input_hash": "b" * 64,
                "effective_probability": "0.64",
                "settlement_distribution": {
                    "WIN": "0.5",
                    "HALF_WIN": "0.1",
                    "PUSH": "0.1",
                    "HALF_LOSS": "0.1",
                    "LOSS": "0.2",
                },
                "fair_decimal_odds": "1.4545",
                "expected_value": "0.08",
                "ev_se": "0.01",
            },
            "market_probability": {"devig": {"HOME": "0.48", "AWAY": "0.52"}},
            "comparison": {"probability_delta": "0.12"},
        },
    }


def _decision() -> dict[str, object]:
    decision = _build_public_recommendation_decision_v4(
        card={
            "fixture_id": "fixture-1",
            "competition_id": "allsvenskan",
            "frozen_artifact_provenance": {
                "fixture_identity": {
                    "fixture_id": "fixture-1",
                    "competition_id": "allsvenskan",
                    "kickoff_utc": "2026-08-08T15:30:00Z",
                },
                "input_manifest": {
                    "dynamic_fixture_identity": {
                        "competition_id": "allsvenskan",
                        "season": "2026",
                        "provider": "api-football",
                    }
                },
            },
        },
        row={
            "fixture_id": "fixture-1",
            "competition_id": "allsvenskan",
            "kickoff_utc": "2026-08-08T15:30:00Z",
        },
        candidate=_candidate(),
        formal_recommendation=None,
    )
    assert decision.outcome is RecommendationOutcomeV4.ANALYSIS_PICK
    return decision.as_dict()


def _contract(decision: dict[str, object]) -> dict[str, object]:
    selected = decision["selected_candidate"]
    assert isinstance(selected, dict)
    return {
        "decision_tier": "ANALYSIS_PICK",
        "data_status": "READY",
        "lifecycle_status": "DRAFT",
        "outcome_tracked": True,
        "lock_eligible": False,
        "recommendation_id": None,
        "lineup_requirement": "ADVISORY",
        "risk_reason_codes": ["LINEUP_UNOBSERVABLE"],
        "pick": {
            "market": selected["market"],
            "selection": selected["selection"],
            "line": selected["exact_line"],
            "odds": selected["decimal_odds"],
        },
        "non_pick": None,
    }


def test_public_v4_input_reuses_exact_candidate_identity_and_manifest_gate() -> None:
    decision = _decision()
    authoritative = decision["authoritative_input"]
    assert isinstance(authoritative, dict)

    assert authoritative["readiness"] == {
        "status": "READY",
        "quote_identity_status": "COMPLETE",
        "quote_freshness_status": "COMPLETE",
        "model_status": "READY",
    }
    assert authoritative["canonical_mainline_identity"] == {
        "market": "ASIAN_HANDICAP",
        "line": "-0.5",
        "selection_policy": "CANONICAL",
        "selected_side_line": "0.5",
        "candidate_role": "MARKET_MAINLINE",
        "quote_identity_hash": "c" * 64,
    }
    assert authoritative["capability_status"] == "FORMAL_DISABLED"
    assert authoritative["formal_admission"]["status"] == "DISABLED"


def test_formal_recommendation_carries_exact_v4_quote_identity() -> None:
    materialized = _decision()
    authoritative = deepcopy(materialized["authoritative_input"])
    authoritative["capability_status"] = "FORMAL_ENABLED"
    authoritative["formal_admission"] = {
        "status": "PASSED",
        "readiness_hash": "e" * 64,
        "approval_hash": "f" * 64,
        "candidate_identity_hash": candidate_identity_hash(authoritative),
    }
    decision = build_recommendation_decision_v4(authoritative)

    recommendation = _recommendation_from_v4(
        decision,
        formal_recommendation=_formal_payload(authoritative),
    )

    assert decision.outcome is RecommendationOutcomeV4.FORMAL_RECOMMEND
    assert recommendation is not None
    assert recommendation["quote_identity"] == {
        "provider": "api-football",
        "bookmaker_id": "unibet",
        "capture_id": "capture-1",
        "captured_at": "2026-08-08T15:00:00.000000Z",
        "observation_ids": {
            "home": "observation-home",
            "away": "observation-away",
        },
        "raw_payload_sha256": "a" * 64,
        "source_revision": "d" * 40,
        "quote_identity_hash": "c" * 64,
    }


def _formal_readiness(*, approved: bool = True) -> dict[str, object]:
    body: dict[str, object] = {
        "schema_version": "w2.formal_ah_readiness.v1",
        "actual_hashes": {"evidence": "a" * 64},
        "approved_hashes": {"evidence": "a" * 64} if approved else {},
        "approval_status": {"passed": approved},
        "approval_hash": "b" * 64 if approved else None,
        "formal_eligible": approved,
    }
    body["readiness_hash"] = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return body


def _formal_payload(authoritative: dict[str, object]) -> dict[str, object]:
    mainline = authoritative["canonical_mainline_identity"]
    assert isinstance(mainline, dict)
    return {
        "decision_tier": "RECOMMEND",
        "market": "ASIAN_HANDICAP",
        "selection": "AWAY_AH",
        "line": authoritative["exact_line"],
        "odds": authoritative["decimal_odds"],
        "quote_identity": {
            "provider": authoritative["provider"],
            "bookmaker_id": authoritative["bookmaker_id"],
            "capture_id": authoritative["capture_id"],
            "captured_at": authoritative["captured_at"],
            "observation_ids": authoritative["quote_observation_ids"],
            "raw_payload_sha256": authoritative["raw_payload_sha256"],
            "source_revision": authoritative["source_revision"],
            "quote_identity_hash": mainline["quote_identity_hash"],
        },
    }


def test_manifest_enabled_but_environment_disabled_cannot_admit_formal() -> None:
    authoritative = deepcopy(_decision()["authoritative_input"])
    assert isinstance(authoritative, dict)
    admission = _public_formal_admission(
        authoritative_input=authoritative,
        formal_recommendation=_formal_payload(authoritative),
        formal_result=SimpleNamespace(formal_eligible=True),
        analysis_readiness={"formal_ah_readiness": _formal_readiness()},
        formal_capability_enabled=False,
    )

    assert admission["status"] == "DISABLED"


def test_enabled_gates_without_human_approval_cannot_admit_formal() -> None:
    authoritative = deepcopy(_decision()["authoritative_input"])
    assert isinstance(authoritative, dict)
    admission = _public_formal_admission(
        authoritative_input=authoritative,
        formal_recommendation=_formal_payload(authoritative),
        formal_result=SimpleNamespace(formal_eligible=True),
        analysis_readiness={"formal_ah_readiness": _formal_readiness(approved=False)},
        formal_capability_enabled=True,
    )

    assert admission["status"] == "NOT_READY"


def test_empty_formal_result_cannot_admit_formal() -> None:
    authoritative = deepcopy(_decision()["authoritative_input"])
    assert isinstance(authoritative, dict)
    admission = _public_formal_admission(
        authoritative_input=authoritative,
        formal_recommendation=None,
        formal_result=SimpleNamespace(formal_eligible=False),
        analysis_readiness={"formal_ah_readiness": _formal_readiness()},
        formal_capability_enabled=True,
    )

    assert admission["status"] == "NOT_READY"


def test_formal_payload_candidate_identity_mismatch_cannot_admit_formal() -> None:
    authoritative = deepcopy(_decision()["authoritative_input"])
    assert isinstance(authoritative, dict)
    formal = _formal_payload(authoritative)
    formal["line"] = "0.75"
    admission = _public_formal_admission(
        authoritative_input=authoritative,
        formal_recommendation=formal,
        formal_result=SimpleNamespace(formal_eligible=True),
        analysis_readiness={"formal_ah_readiness": _formal_readiness()},
        formal_capability_enabled=True,
    )

    assert admission["status"] == "NOT_READY"


def test_only_complete_same_candidate_formal_evidence_is_admitted() -> None:
    authoritative = deepcopy(_decision()["authoritative_input"])
    assert isinstance(authoritative, dict)
    authoritative["capability_status"] = "FORMAL_ENABLED"
    admission = _public_formal_admission(
        authoritative_input=authoritative,
        formal_recommendation=_formal_payload(authoritative),
        formal_result=SimpleNamespace(formal_eligible=True),
        analysis_readiness={"formal_ah_readiness": _formal_readiness()},
        formal_capability_enabled=True,
    )
    authoritative["formal_admission"] = admission

    decision = build_recommendation_decision_v4(authoritative)

    assert admission["status"] == "PASSED"
    assert decision.outcome is RecommendationOutcomeV4.FORMAL_RECOMMEND


def test_all_ineligible_candidates_emit_no_public_pick() -> None:
    authoritative = deepcopy(_decision()["authoritative_input"])
    assert isinstance(authoritative, dict)
    authoritative["decimal_odds"] = "1.5"
    authoritative["expected_value"] = "0.025"
    authoritative["formal_admission"] = {
        "status": "NOT_READY",
        "readiness_hash": None,
        "approval_hash": None,
        "candidate_identity_hash": None,
    }

    decision = build_recommendation_decision_v4(authoritative)

    assert decision.outcome is RecommendationOutcomeV4.NO_EDGE
    assert decision.selected_candidate is None
    assert _recommendation_from_v4(decision, formal_recommendation=None) is None


def test_repository_current_projection_uses_v4_not_historical_v3_direction() -> None:
    decision = _decision()
    contract = _contract(decision)
    card = {
        "fixture_id": "fixture-1",
        **deepcopy(contract),
        "decision_contract": deepcopy(contract),
        "recommendation_decision_v4": decision,
        "recommendation_decision_v3": {
            "outcome": "ANALYSIS_PICK",
            "selected_candidate": {"selection": "HOME", "exact_line": "-0.5"},
        },
    }

    projected = _apply_repository_v4_authority(card)

    assert projected["pick"]["selection"] == "AWAY"
    assert projected["recommendation_decision_v3_role"] == "HISTORY_ONLY"
    assert projected["decision_contract"]["recommendation_authority"] == (
        "RECOMMENDATION_DECISION_V4"
    )


def test_repository_legacy_direction_cannot_create_current_pick_without_v4() -> None:
    contract = _contract(_decision())
    card = {
        "fixture_id": "fixture-1",
        **deepcopy(contract),
        "decision_contract": deepcopy(contract),
        "recommendation_decision_v3": {
            "outcome": "ANALYSIS_PICK",
            "selected_candidate": {"selection": "HOME", "exact_line": "-0.5"},
        },
    }

    projected = _apply_repository_v4_authority(card)

    assert projected["decision_tier"] == "NOT_READY"
    assert projected["pick"] is None
    assert projected["reason_code"] == "CURRENT_V4_AUTHORITY_MISSING"
    assert projected["recommendation_decision_v3_role"] == "HISTORY_ONLY"


def test_invalid_history_v3_cannot_block_or_mutate_current_v4() -> None:
    decision_v4 = _decision()
    card = {
        "card_hash": "current-v4-card",
        "decision_contract": {"card_hash": "current-v4-card"},
        "recommendation_decision_v4": deepcopy(decision_v4),
        "recommendation_decision_v3": {
            "schema_version": "w2.recommendation_decision.v3",
            "outcome": "ANALYSIS_PICK",
            "decision_hash": "tampered-history",
        },
    }

    service = object.__new__(ReadModelService)
    service._retain_valid_history_v3(card)

    assert card["recommendation_decision_v4"] == decision_v4
    assert "recommendation_decision_v3" not in card
    assert card["recommendation_decision_v3_role"] == "HISTORY_ONLY"


def test_day_view_passes_valid_v4_current_pick_without_rebuilding_it() -> None:
    decision = _decision()
    contract = _contract(decision)
    view = build_dashboard_day_view(
        {
            "generated_at": "2026-08-08T10:00:00Z",
            "date": "2026-08-08",
            "selected_football_day": "2026-08-08",
            "all": [
                {
                    "fixture_id": "fixture-1",
                    "kickoff_utc": "2026-08-08T15:30:00Z",
                    **deepcopy(contract),
                    "decision_contract": deepcopy(contract),
                    "recommendation_decision_v4": decision,
                    "recommendation_decision_v3": {"outcome": "NOT_READY"},
                }
            ],
        },
        environment="staging",
    )

    card = view["cards"][0]
    assert card["decision_tier"] == "ANALYSIS_PICK"
    assert card["pick"]["selection"] == "AWAY"
    assert card["recommendation_decision_v4"] == decision
    assert card["recommendation_decision_v3_role"] == "HISTORY_ONLY"


def test_public_v4_does_not_invent_identity_failure_when_model_is_unready() -> None:
    decision = _build_public_recommendation_decision_v4(
        card={
            "fixture_id": "fixture-1",
            "competition_id": "allsvenskan",
            "season": "2026",
            "kickoff_utc": "2026-08-08T15:30:00Z",
            "simulation": {"status": "INSUFFICIENT_INPUTS"},
            "quote_identity_audit": {
                "ah": {
                    "identity_status": "COMPLETE",
                    "freshness_status": "COMPLETE",
                }
            },
        },
        row={
            "fixture_id": "fixture-1",
            "competition_id": "allsvenskan",
            "kickoff_utc": "2026-08-08T15:30:00Z",
        },
        candidate=None,
        formal_recommendation=None,
    )

    assert decision.outcome is RecommendationOutcomeV4.NOT_READY
    assert decision.reason_code == "EVIDENCE_NOT_READY"
    assert "MODEL_EVIDENCE_NOT_READY" in decision.blockers
