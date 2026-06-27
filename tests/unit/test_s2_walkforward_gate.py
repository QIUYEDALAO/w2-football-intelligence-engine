from __future__ import annotations

from w2.backtest.s2_gate import (
    S2_MIN_COVERED_SETTLED_SAMPLE,
    S2GateEvidence,
    s2_walkforward_shadow_status,
)


def test_s2_gate_freezes_portfolio_threshold_and_blocks_missing_evidence() -> None:
    status = s2_walkforward_shadow_status(
        S2GateEvidence(
            covered_settled_sample=199,
            noise_separated_advantage=False,
            time_split_passed=False,
            holdout_replicated=False,
            forward_shadow_passed=False,
        )
    )

    assert status["minimum_covered_settled_sample"] == 200
    assert S2_MIN_COVERED_SETTLED_SAMPLE == 200
    assert status["status"] == "ANALYSIS_ONLY"
    assert status["beats_market"] is False
    assert status["blockers"] == [
        "covered_settled_sample",
        "noise_separated_advantage",
        "time_split_passed",
        "holdout_replicated",
        "forward_shadow_passed",
    ]
    assert status["reason"] == "INSUFFICIENT_VALIDATED_SAMPLES"


def test_s2_gate_skeleton_never_enables_beats_market_in_wave1() -> None:
    status = s2_walkforward_shadow_status(
        S2GateEvidence(
            covered_settled_sample=200,
            noise_separated_advantage=True,
            time_split_passed=True,
            holdout_replicated=True,
            forward_shadow_passed=True,
        )
    )

    assert status["checks"] == {
        "covered_settled_sample": True,
        "noise_separated_advantage": True,
        "time_split_passed": True,
        "holdout_replicated": True,
        "forward_shadow_passed": True,
    }
    assert status["blockers"] == ["FORMAL_GATE_DISABLED_IN_WAVE1"]
    assert status["reason"] == "WAVE1_FORMAL_GATE_DISABLED"
    assert status["status"] == "ANALYSIS_ONLY"
    assert status["beats_market"] is False
