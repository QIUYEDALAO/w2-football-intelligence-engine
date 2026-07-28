from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
TASK_ORDER = (
    "ARCH-GOVERNANCE-01",
    "ARCH-P1-04C",
    "ARCH-P1-03",
    "ARCH-P1-05",
    "ARCH-P1-06",
    "ARCH-P1-07",
    "ARCH-P1-08",
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

    assert state["current_task"] == "ARCH-P1-05"
    assert state["current_status"] == "IN_PROGRESS"
    assert state["current_pr"] == 420
    assert state["next_task"] == "ARCH-P1-06"
    assert tuple(state["task_queue"]) == TASK_ORDER
    assert "当前：完成 A4 ARCH-P1-05 的 Draft Implementation PR。" in next_action
    assert "下一项：A5 ARCH-P1-06。" in next_action
    positions = [
        checklist.index(f"#### A{index}. {task}")
        for index, task in enumerate(TASK_ORDER, 1)
    ]
    assert positions == sorted(positions)
    for task in FORBIDDEN_TASKS:
        assert task not in state
        assert task not in next_action
        assert task not in checklist
    assert state["staging"]["production_deployed"] is False


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
