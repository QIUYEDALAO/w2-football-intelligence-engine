from __future__ import annotations

from w2.dashboard.recommendations import (
    RecommendationTier,
    build_recommendation,
    derive_recommendation_tier,
)


def test_dashboard_reads_decision_tier_before_legacy_fields() -> None:
    card = {
        "decision_tier": "WATCH",
        "formal_recommendation": True,
        "recommendation_id": "legacy-rec",
    }
    market = {"decision": "PICK", "analysis_decision": "ANALYSIS_PICK"}

    assert derive_recommendation_tier(card, market) is RecommendationTier.WATCH
    assert build_recommendation(card, market) is None


def test_dashboard_maps_recommend_decision_tier_to_legacy_formal_view() -> None:
    card = {
        "decision_tier": "RECOMMEND",
        "generated_at": "2026-07-05T00:00:00Z",
        "outcome_tracked": True,
        "lock_eligible": True,
    }
    market = {
        "market": "ASIAN_HANDICAP",
        "tendency": "HOME",
        "line": "-0.25",
        "odds": "1.95",
        "reasons": ["forward +EV evidence"],
    }

    recommendation = build_recommendation(card, market)

    assert recommendation is not None
    assert recommendation["tier"] == "FORMAL"
    assert recommendation["decision_tier"] == "RECOMMEND"
    assert recommendation["outcome_tracked"] is True
    assert recommendation["lock_eligible"] is True
    assert recommendation["selection"] == "HOME"
    assert "candidate" not in recommendation
    assert "formal_recommendation" not in recommendation


def test_dashboard_uses_legacy_shim_only_when_decision_tier_is_missing() -> None:
    legacy_formal = {"formal_recommendation": True, "recommendation_id": "rec-1"}
    before = dict(legacy_formal)

    assert derive_recommendation_tier(legacy_formal, None) is RecommendationTier.FORMAL
    assert legacy_formal == before
    assert (
        derive_recommendation_tier(
            {"decision_tier": "RECOMMEND", "recommendation_id": "rec-new"},
            {"market": "ASIAN_HANDICAP"},
        )
        is RecommendationTier.FORMAL
    )
    assert (
        derive_recommendation_tier(
            {},
            {"analysis_decision": "ANALYSIS_PICK", "formal_recommendation": False},
        )
        is RecommendationTier.ANALYSIS_PICK
    )
    assert derive_recommendation_tier({"decision": "NO_RECOMMENDATION"}, None) is (
        RecommendationTier.NO_RECOMMENDATION
    )


def test_new_card_does_not_infer_from_formal_candidate_or_analysis_decision() -> None:
    card = {
        "decision_tier": "SKIP",
        "formal_recommendation": True,
        "candidate": True,
        "decision": "PICK",
    }
    market = {
        "candidate": True,
        "decision": "PICK",
        "analysis_decision": "ANALYSIS_PICK",
    }

    assert derive_recommendation_tier(card, market) is RecommendationTier.NO_RECOMMENDATION
    assert build_recommendation(card, market) is None


def test_analysis_pick_recommendation_shell_is_not_production_actionable() -> None:
    recommendation = build_recommendation(
        {"decision_tier": "ANALYSIS_PICK"},
        {
            "market": "ASIAN_HANDICAP",
            "decision": "PICK",
            "tendency": "HOME",
            "line": "-0.25",
            "odds": "1.95",
            "reasons": ["analysis only"],
        },
    )

    assert recommendation is not None
    assert recommendation["tier"] == "ANALYSIS_PICK"
    assert recommendation["decision_tier"] == "ANALYSIS_PICK"
    assert recommendation["outcome_tracked"] is True
    assert "selection" not in recommendation
    assert "line" not in recommendation
    assert "odds" not in recommendation
    assert "candidate" not in recommendation
    assert "formal_recommendation" not in recommendation
