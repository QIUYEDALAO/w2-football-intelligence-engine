from __future__ import annotations

from dataclasses import dataclass
from typing import Any

S2_MIN_COVERED_SETTLED_SAMPLE = 200
S2_GATE_VERSION = "w2.s2.walkforward_gate.v1"
WAVE1_FORMAL_GATE_DISABLED_REASON = "WAVE1_FORMAL_GATE_DISABLED"
WAVE1_FORMAL_GATE_DISABLED_BLOCKER = "FORMAL_GATE_DISABLED_IN_WAVE1"


@dataclass(frozen=True, kw_only=True)
class S2GateEvidence:
    covered_settled_sample: int
    noise_separated_advantage: bool = False
    time_split_passed: bool = False
    holdout_replicated: bool = False
    forward_shadow_passed: bool = False


def s2_walkforward_shadow_status(evidence: S2GateEvidence) -> dict[str, Any]:
    checks = {
        "covered_settled_sample": evidence.covered_settled_sample
        >= S2_MIN_COVERED_SETTLED_SAMPLE,
        "noise_separated_advantage": evidence.noise_separated_advantage,
        "time_split_passed": evidence.time_split_passed,
        "holdout_replicated": evidence.holdout_replicated,
        "forward_shadow_passed": evidence.forward_shadow_passed,
    }
    blockers = [
        key
        for key, passed in checks.items()
        if not passed
    ]
    reason = (
        WAVE1_FORMAL_GATE_DISABLED_REASON
        if not blockers
        else "INSUFFICIENT_VALIDATED_SAMPLES"
    )
    if not blockers:
        blockers = [WAVE1_FORMAL_GATE_DISABLED_BLOCKER]
    return {
        "gate_version": S2_GATE_VERSION,
        "status": "ANALYSIS_ONLY",
        "portfolio_level": True,
        "minimum_covered_settled_sample": S2_MIN_COVERED_SETTLED_SAMPLE,
        "covered_settled_sample": evidence.covered_settled_sample,
        "checks": checks,
        "blockers": blockers,
        "reason": reason,
        "beats_market": False,
    }
