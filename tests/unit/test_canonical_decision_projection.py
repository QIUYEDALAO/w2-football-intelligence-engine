from __future__ import annotations

from w2.domain.canonical_decision_projection import project_canonical_decision


def test_non_pick_v3_is_fail_closed_in_compatibility_projection() -> None:
    projected = project_canonical_decision(
        {
            "outcome": "NOT_READY",
            "reason": {"code": "DATA_NOT_READY"},
            "selected_candidate": {"market": "TOTALS"},
        }
    )
    assert projected["pick"] is None
    assert projected["outcome_tracked"] is False
    assert projected["lock_eligible"] is False


def test_analysis_pick_keeps_candidate_but_is_never_lock_eligible() -> None:
    projected = project_canonical_decision(
        {
            "outcome": "ANALYSIS_PICK",
            "selected_candidate": {"market": "TOTALS", "line": "2.5"},
            "decision_hash": "h",
        }
    )
    assert projected["pick"] == {"market": "TOTALS", "line": "2.5"}
    assert projected["lock_eligible"] is False


def test_formal_recommend_projection_does_not_recompute_lock() -> None:
    projected = project_canonical_decision(
        {
            "outcome": "FORMAL_RECOMMEND",
            "selected_candidate": {"market": "ASIAN_HANDICAP", "line": "-0.25"},
            "decision_hash": "h",
        }
    )

    assert projected["decision_tier"] == "RECOMMEND"
    assert projected["lock_eligible"] is False
