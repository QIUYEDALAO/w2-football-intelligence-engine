from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
TASK_ORDER = (
    "EVAL-01A",
    "EVAL-01B",
    "EVAL-01C",
    "EVAL-02A",
    "EVAL-02B",
    "OPS-01",
    "EVAL-03",
)
FORBIDDEN_TASKS = (
    "ARCH-OBS-01",
    "ARCH-EVIDENCE-01",
    "ARCH-DONE-REAUDIT",
    "ARCH-P1-03B-R1_VERIFICATION",
    "PREFLIGHT",
    "CLOSURE",
)


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_v3_task_authority_and_next_action_are_consistent() -> None:
    state = yaml.safe_load(read("PROJECT_STATE.yaml"))
    next_action = read("NEXT_ACTION.md")
    checklist = read(
        "docs/operations/architecture_convergence/"
        "W2_ARCHITECTURE_CONVERGENCE_MASTER_CHECKLIST.md"
    )

    assert state["current_task"] == "EVAL-01A"
    assert state["current_status"] == "IMPLEMENTED_PENDING_ACCEPTANCE"
    assert state["current_pr"] == 424
    assert state["next_task"] == "EVAL-01B"
    assert tuple(state["task_queue"]) == TASK_ORDER
    assert "当前：完成 B1 EVAL-01A 的 Draft Implementation PR。" in next_action
    assert "下一项：B2 EVAL-01B；B1 合并前不启动。" in next_action
    assert "#### B1. EVAL-01A" in checklist
    assert "Status: IMPLEMENTED_PENDING_ACCEPTANCE" in checklist
    assert "P1_ARCHITECTURE_CONVERGENCE_PASS = PASS" in checklist
    for task in FORBIDDEN_TASKS:
        assert task not in state
        assert task not in next_action
        assert task not in checklist
    assert state["staging"]["production_deployed"] is False
    assert "ARCH-P1-08" not in state["task_queue"]


def test_historical_pr_range_is_explicitly_non_authoritative() -> None:
    policy = read("docs/operations/W2_DELIVERY_STATUS_LEVELS.md")
    recovery = read("docs/consolidation/W2_V3_CORRECTNESS_RECOVERY_PLAN_20260718.md")

    assert "PRs #333–#347" in policy
    assert "PRs #333–#347" in recovery
    assert "specification and failure-case inputs only" in recovery


def test_obsolete_staging_ip_is_absent_from_tracked_authority() -> None:
    obsolete_ip = "43.155" + ".208.138"
    result = subprocess.run(
        ["git", "grep", "-n", obsolete_ip],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1, result.stdout
