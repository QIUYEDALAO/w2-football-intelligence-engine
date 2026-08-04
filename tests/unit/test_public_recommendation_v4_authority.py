from __future__ import annotations

from copy import deepcopy

from w2.api.repository import _apply_repository_v4_authority
from w2.dashboard.day_view import build_dashboard_day_view
from w2.domain.recommendation_decision_v4 import (
    RecommendationOutcomeV4,
    build_recommendation_decision_v4,
)
from w2.prematch.analysis_calculator import (
    ReadModelService,
    _build_public_recommendation_decision_v4,
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
            "source_revision": "source-revision-1",
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


def test_formal_recommendation_carries_exact_v4_quote_identity() -> None:
    materialized = _decision()
    authoritative = deepcopy(materialized["authoritative_input"])
    authoritative["capability_status"] = "FORMAL_ENABLED"
    decision = build_recommendation_decision_v4(authoritative)

    recommendation = _recommendation_from_v4(
        decision,
        formal_recommendation={
            "tier": "FORMAL",
            "market": "ASIAN_HANDICAP",
            "selection": "AWAY_AH",
            "line": "0.5",
            "odds": "1.6",
        },
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
        "source_revision": "source-revision-1",
        "quote_identity_hash": "c" * 64,
    }


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
