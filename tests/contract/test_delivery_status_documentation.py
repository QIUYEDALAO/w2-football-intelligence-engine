from __future__ import annotations

import re
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CHECKLIST_PATH = (
    "docs/operations/architecture_convergence/"
    "W2_ARCHITECTURE_CONVERGENCE_MASTER_CHECKLIST.md"
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
    ledger = read("PROJECT_LEDGER.md")
    checklist = read(CHECKLIST_PATH)

    assert state["current_state_authority"] == "PROJECT_STATE.yaml"
    assert state["task_authority"] == CHECKLIST_PATH
    assert state["current_task"] == "ARCH-P2-04"
    assert state["current_status"] == "IN_PROGRESS"
    assert state["current_pr"] == 427
    assert state["next_task"] == "ARCH-P2-06"
    assert state["tasks"]["ARCH-P2-02"] == {
        "status": "DONE",
        "receipt": CHECKLIST_PATH,
    }
    assert state["tasks"]["ARCH-P2-03"]["status"] == "DONE"
    assert state["tasks"]["ARCH-P2-03"]["space_released_kib"] == 1853664
    assert state["tasks"]["EVAL-01A"] == {
        "status": "BLOCKED",
        "pr": 424,
        "exact_head": "1bd33939243894d37475bb6d9a7bd86f175e8900",
        "mergeable": False,
        "blockers": [
            "EXACT_HEAD_IMAGE_TRANSFER_BLOCKED",
            "BASE_DIVERGENCE_MERGE_CONFLICT",
        ],
        "next_required_action": (
            "Reconcile PR #424 onto the then-current main, resolve status-file "
            "conflicts, rerun exact-head CI and external review, then perform "
            "exact-head staging."
        ),
    }
    assert state["tasks"]["EVAL-01B"]["status"] == "NOT_STARTED"
    assert "[PROJECT_STATE.yaml](PROJECT_STATE.yaml)" in next_action
    assert CHECKLIST_PATH in next_action
    assert "sole machine-readable project-status record" in ledger
    assert not re.search(r"\b[0-9a-f]{40}\b|CI:\s*\d+", ledger)
    assert not re.search(r"\b[0-9a-f]{40}\b|CI:\s*\d+", next_action)
    assert "`PROJECT_STATE.yaml` 是 W2 **唯一当前机器可读状态快照**" in checklist
    assert "唯一任务顺序、任务规格和已合并完成回执权威" in checklist
    assert "状态只更新本文件" not in checklist
    assert "任务状态仍只由本文件" not in checklist
    redlines = checklist[checklist.index("### 永久红线") : checklist.index("### 冻结解除边界")]
    section_seven = checklist[checklist.index("## 七、") : checklist.index("## 八、")]
    machine_appendix = checklist[checklist.index("## 九、") :]
    for section in (redlines, section_seven, machine_appendix):
        assert "`PROJECT_STATE.yaml`" in section
        assert "已合并完成回执" in section
    b1 = checklist[
        checklist.index("#### B1. EVAL-01A") : checklist.index("#### B2.")
    ]
    assert "Status: BLOCKED" in b1
    assert "EXACT_HEAD_IMAGE_TRANSFER_BLOCKED" in b1
    assert "BASE_DIVERGENCE_MERGE_CONFLICT" in b1
    for task in FORBIDDEN_TASKS:
        assert task not in state
        assert task not in next_action
        assert task not in checklist
    assert state["staging"]["production_deployed"] is False


def test_historical_pr_range_is_explicitly_non_authoritative() -> None:
    policy = read("docs/operations/W2_DELIVERY_STATUS_LEVELS.md")
    recovery = read(
        "docs/archive/consolidation/W2_V3_CORRECTNESS_RECOVERY_PLAN_20260718.md"
    )

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
