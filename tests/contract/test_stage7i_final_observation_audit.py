from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DECISION = ROOT / "reports/W2_STAGE7I_FINAL_OBSERVATION_DECISION.json"
HANDOFF = ROOT / "reports/W2_CURRENT_HANDOFF.md"
R1B2 = ROOT / "reports/W2_STAGE7I_R1B2_RESULT.md"


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def test_stage7i_final_decision_uses_allowed_status() -> None:
    decision = json.loads(DECISION.read_text(encoding="utf-8"))

    assert decision["status"] in {
        "SUCCESSOR_OBSERVATION_COMPLETED",
        "BLOCKED_NON_QUALIFYING_LIFECYCLE_GAP",
        "OBSERVER_OVERRUN_AFTER_EXPECTED_END",
        "OBSERVER_TERMINATED_WITHOUT_FINAL_SUMMARY",
        "FINAL_EVIDENCE_BLOCKED",
    }
    assert decision["classification"] == decision["status"]


def test_lifecycle_gap_does_not_claim_completion_or_gate5_eligibility() -> None:
    decision = json.loads(DECISION.read_text(encoding="utf-8"))

    assert decision["status"] == "BLOCKED_NON_QUALIFYING_LIFECYCLE_GAP"
    assert decision["lifecycle"]["gap"] is True
    assert decision["final_evidence_builder"]["status"] != "COMPLETED"
    assert decision["gate5"]["status"] == "OPEN"
    assert decision["gate5"]["eligible"] is False


def test_actual_kickoff_and_closing_boundaries_are_not_fabricated() -> None:
    decision = json.loads(DECISION.read_text(encoding="utf-8"))

    assert decision["actual_kickoff"]["utc"] is None
    assert decision["actual_kickoff"]["status"] == "ACTUAL_KICKOFF_SOURCE_UNAVAILABLE"
    assert decision["closing_observation"]["captured_at_utc"] is None
    assert decision["closing_observation"]["status"] == "PENDING_ACTUAL_KICKOFF"

    actual = decision["actual_kickoff"]["utc"]
    closing = decision["closing_observation"]["captured_at_utc"]
    if actual and closing:
        assert _parse_utc(closing) < _parse_utc(actual)


def test_final_checker_failure_blocks_gate5() -> None:
    decision = json.loads(DECISION.read_text(encoding="utf-8"))

    assert decision["final_checker"]["result"] == "FAIL"
    assert decision["gate5"]["eligible"] is False


def test_handoff_records_v33_and_no_recommendation_flags() -> None:
    handoff = HANDOFF.read_text(encoding="utf-8")

    assert "handoff_version: 36" in handoff
    assert "stage7i_status: BLOCKED_NON_QUALIFYING_LIFECYCLE_GAP" in handoff
    assert "gate5: OPEN" in handoff
    assert "candidate: false" in handoff
    assert "formal_recommendation: false" in handoff


def test_handoff_and_r1b2_do_not_restore_stale_active_observer_claims() -> None:
    handoff = HANDOFF.read_text(encoding="utf-8")
    r1b2 = R1B2.read_text(encoding="utf-8")

    stale_handoff_phrases = {
        "successor_run_status=IN_PROGRESS",
        "Stage7I successor 24h observation 尚未完成",
        "当前 successor `1489404` 仍需完成完整 24h",
    }
    stale_r1b2_phrases = {
        "Stage7I successor 24-hour observation is still in progress.",
        "While the successor observer continues",
        "The active observer is the intended R1B2 successor process.",
    }

    assert not stale_handoff_phrases.intersection(handoff.splitlines())
    for phrase in stale_handoff_phrases:
        assert phrase not in handoff
    for phrase in stale_r1b2_phrases:
        assert phrase not in r1b2

    assert (
        "stage7i_successor_run_status: "
        "BLOCKED_NON_QUALIFYING_LIFECYCLE_GAP"
    ) in handoff
    assert "Process after audit buffer: not alive" in r1b2
