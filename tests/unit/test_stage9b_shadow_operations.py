from __future__ import annotations

import json
from pathlib import Path

from scripts.run_stage9a_shadow_replay import demo_inputs

from w2.strategy.operations import gate5_preflight, run_shadow_replay

ROOT = Path(__file__).resolve().parents[2]


def test_stage9b_separates_forward_and_retrospective() -> None:
    replay = run_shadow_replay(inputs=demo_inputs(), root=ROOT, mode="LOCAL_DRY_RUN")
    assert replay["forward"]["lock_count"] == 0
    assert replay["retrospective"]["status"] == "RETROSPECTIVE_REPLAY"
    assert all(decision["phase"] == "RETROSPECTIVE_REPLAY" for decision in replay["decisions"])
    assert replay["formal_recommendation"] is False
    assert replay["candidate"] is False


def test_stage9b_replay_is_deterministic() -> None:
    first = run_shadow_replay(inputs=demo_inputs(), root=ROOT, mode="LOCAL_DRY_RUN")
    second = run_shadow_replay(inputs=demo_inputs(), root=ROOT, mode="LOCAL_DRY_RUN")
    first_hashes = [variant["decision_hash"] for variant in first["retrospective"]["variants"]]
    second_hashes = [variant["decision_hash"] for variant in second["retrospective"]["variants"]]
    assert first_hashes == second_hashes


def test_gate5_preflight_cannot_close_when_gate4_pending() -> None:
    replay = {
        "forward": {"lock_count": 0},
        "coverage": {"hard_gate_reasons": {}},
        "locks": [],
    }
    comparison = {"status": "COMPLETED_WITH_NOT_AVAILABLE_FIELDS"}
    policy = {
        "gate4_prerequisite": "GATE_4_NATIONAL_1X2_CLOSED_REQUIRED",
        "target_forward_sample_count": 60,
    }
    result = gate5_preflight(replay=replay, comparison=comparison, acceptance_policy=policy)
    assert result["closed"] is False
    assert result["gate5_result"] == "PROVISIONAL_BLOCKED_GATE4"


def test_stage9b_report_has_no_forbidden_public_states() -> None:
    replay = run_shadow_replay(inputs=demo_inputs(), root=ROOT, mode="LOCAL_DRY_RUN")
    encoded = json.dumps(replay)
    assert '"public_decision": "CANDIDATE"' not in encoded
    assert '"public_decision": "RECOMMEND"' not in encoded
