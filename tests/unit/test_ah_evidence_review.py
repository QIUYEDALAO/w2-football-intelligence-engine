from __future__ import annotations

from w2.tracking.ah_evidence_review import build_ah_evidence_review


def _outcome(index: int, *, strategy: str = "W2_AH_STRICT_SHADOW_V1") -> dict[str, object]:
    selection = "HOME_AH" if index % 2 == 0 else "AWAY_AH"
    outcome = "WIN" if index % 3 else "LOSS"
    return {
        "record_type": "outcome",
        "fixture_id": f"fixture-{index}",
        "market": "ASIAN_HANDICAP",
        "selection": selection,
        "entry_line": -0.75 if selection == "HOME_AH" else 0.75,
        "entry_price": 1.92,
        "settled_side": "shadow_pick",
        "settlement_outcome": outcome,
        "strategy_version": strategy,
        "estimate_id": f"fme-{index}",
        "quote_id": f"mq-{index}",
        "source_capture_hash": f"capture-{index}",
        "source_captured_at": f"2026-08-{index % 28 + 1:02d}T10:00:00Z",
        "canonical_performance_key": [
            f"fixture-{index}",
            "ASIAN_HANDICAP",
            "SHADOW",
            strategy,
        ],
        "competition_name": "Example League",
        "analysis_gate_v2_shadow": {
            "evidence_eligible": True,
            "semantic_status": "VERIFIED",
            "confirmation_required": strategy.startswith("W2_AH_STRICT"),
            "confirmation_status": "CONFIRMED",
            "artifact_hash": "artifact-1",
            "settlement_probabilities": {
                "WIN": 0.45,
                "HALF_WIN": 0.1,
                "PUSH": 0.1,
                "HALF_LOSS": 0.1,
                "LOSS": 0.25,
            },
        },
    }


def test_ah_evidence_review_reports_accumulating_and_remaining_counts() -> None:
    report = build_ah_evidence_review([_outcome(index) for index in range(12)])

    assert report["status"] == "ACCUMULATING"
    assert report["corrected_settled_count"] == 12
    assert report["home_ah_count"] == 6
    assert report["away_ah_count"] == 6
    assert report["review_35"]["remaining"] == 23
    assert report["maturity_100"]["remaining"] == 88
    assert report["conclusion"] == "ACCUMULATING"


def test_ah_evidence_review_compares_wide_and_strict_with_metrics() -> None:
    records = [
        *[_outcome(index) for index in range(6)],
        *[_outcome(index + 20, strategy="WIDE_SHADOW_V1") for index in range(4)],
    ]
    clv = [
        {"fixture_id": row["fixture_id"], "clv_decimal": 0.03, "line_clv": 0.25} for row in records
    ]

    report = build_ah_evidence_review(records, clv_rows=clv)

    by_strategy = {row["key"]: row for row in report["wide_vs_strict"]}
    assert by_strategy["W2_AH_STRICT_SHADOW_V1"]["settled_count"] == 6
    assert by_strategy["WIDE_SHADOW_V1"]["settled_count"] == 4
    assert by_strategy["W2_AH_STRICT_SHADOW_V1"]["median_clv_decimal"] == 0.03
    assert by_strategy["W2_AH_STRICT_SHADOW_V1"]["five_state_brier"] is not None
    assert by_strategy["W2_AH_STRICT_SHADOW_V1"]["max_drawdown_units"] is not None


def test_ah_evidence_review_marks_35_and_100_maturity_without_opening_direction() -> None:
    review = build_ah_evidence_review([_outcome(index) for index in range(35)])
    mature = build_ah_evidence_review([_outcome(index) for index in range(100)])

    assert review["review_35"]["status"] == "REVIEW_ELIGIBLE"
    assert review["conclusion"] == "KEEP_SHADOW_ONLY"
    assert mature["maturity_100"]["status"] == "MATURE"
    assert mature["conclusion"] == "KEEP_SHADOW_ONLY"
    assert mature["automatic_direction_enable"] is False
