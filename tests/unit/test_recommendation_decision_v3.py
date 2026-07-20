from __future__ import annotations

from w2.domain.recommendation_capabilities import load_recommendation_capability_manifest
from w2.domain.recommendation_decision_v3 import RecommendationOutcomeV3, project_decision_v3


def _contract(**overrides: object) -> dict[str, object]:
    contract: dict[str, object] = {
        "fixture_id": "f-1",
        "competition_id": "c-1",
        "as_of": "2026-07-19T00:00:00Z",
        "decision_tier": "ANALYSIS_PICK",
        "data_status": "READY",
        "quote_provenance_status": "COMPLETE",
        "integrity_status": "PASS",
        "model_version": "model-v1",
        "card_hash": "v2-card",
        "pick": {"market": "ASIAN_HANDICAP", "selection": "HOME", "line": "-0.25", "odds": "1.95"},
    }
    contract.update(overrides)
    return contract


def test_v3_shadow_is_deterministic_and_analysis_only_when_formal_capability_closed() -> None:
    manifest = load_recommendation_capability_manifest()
    left = project_decision_v3(_contract(), manifest=manifest)
    right = project_decision_v3(_contract(), manifest=manifest)

    assert left.outcome is RecommendationOutcomeV3.ANALYSIS_PICK
    assert left.decision_hash == right.decision_hash
    assert left.as_dict()["selected_candidate"] is not None


def test_v3_fails_closed_for_non_ready_and_integrity_conflict() -> None:
    manifest = load_recommendation_capability_manifest()

    not_ready = project_decision_v3(_contract(data_status="STALE"), manifest=manifest)
    degraded = project_decision_v3(
        _contract(quote_provenance_status="CONFLICT"), manifest=manifest
    )

    assert not_ready.outcome is RecommendationOutcomeV3.NOT_READY
    assert not_ready.selected_candidate is None
    assert degraded.outcome is RecommendationOutcomeV3.SYSTEM_DEGRADED
    assert degraded.selected_candidate is None


def test_v3_never_promotes_ou_to_formal() -> None:
    manifest = load_recommendation_capability_manifest()
    decision = project_decision_v3(
        _contract(
            decision_tier="RECOMMEND",
            pick={"market": "TOTALS", "selection": "OVER", "line": "2.5", "odds": "1.95"},
        ),
        manifest=manifest,
    )

    assert decision.outcome is RecommendationOutcomeV3.ANALYSIS_PICK


def test_v3_no_edge_keeps_evaluated_candidate_and_ready_model_status() -> None:
    manifest = load_recommendation_capability_manifest()
    evaluated = {
        "market": "ASIAN_HANDICAP",
        "selection": "HOME",
        "line": "-0.25",
        "model_status": "READY",
        "analysis_evidence": {
            "status": "COMPLETE",
            "model_probability": {"status": "READY"},
            "comparison": {"analysis_direction_allowed": False},
        },
    }

    decision = project_decision_v3(
        _contract(
            decision_tier="SKIP",
            pick=None,
            selected_market_candidate=evaluated,
        ),
        manifest=manifest,
    )

    assert decision.outcome is RecommendationOutcomeV3.NO_EDGE
    assert decision.selected_candidate is None
    assert decision.evaluated_candidate == evaluated
    assert decision.statuses["model"] == "READY"
