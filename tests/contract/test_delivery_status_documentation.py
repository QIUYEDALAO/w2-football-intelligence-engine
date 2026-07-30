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
    assert state["current_task"] == "EVAL-02A"
    assert state["current_status"] == "IN_PROGRESS"
    assert state["current_pr"] == 434
    assert state["next_task"] == "EVAL-02B"
    assert state["tasks"]["ARCH-P2-02"] == {
        "status": "DONE",
        "receipt": CHECKLIST_PATH,
    }
    assert state["tasks"]["ARCH-P2-03"]["status"] == "DONE"
    assert state["tasks"]["ARCH-P2-03"]["space_released_kib"] == 1853664
    assert state["tasks"]["ARCH-P2-04"] == {
        "status": "DONE",
        "pr": 427,
        "merge_sha": "bf21ddcc495b0c8d041c956734d278c1d611f24e",
        "main_ci": 30425831606,
    }
    assert state["tasks"]["ARCH-P2-06"] == {
        "status": "DONE",
        "pr": 428,
        "merge_sha": "1a46a9e47a478072d37e4ec4c7a44d914e1a127b",
        "main_ci": 30432075563,
    }
    assert state["tasks"]["ARCH-P2-05"] == {
        "status": "DONE",
        "pr": 429,
        "merge_sha": "86a66ff5c07438b0543d2790165d406d452daedb",
        "main_ci": 30435005222,
    }
    assert state["tasks"]["EVAL-01A"] == {
        "status": "DONE",
        "pr": 424,
        "merge_sha": "dc1a665655add801c4fe5cd7a0f39211d836e916",
        "main_ci": 30441901340,
    }
    assert state["tasks"]["EVAL-01B"] == {
        "status": "DONE",
        "pr": 430,
        "merge_sha": "5c2bd6f2e5c23196a25495335da72599e076c8ae",
        "main_ci": 30477611652,
    }
    assert state["tasks"]["EVAL-01C"] == {
        "status": "DONE",
        "pr": 432,
        "merge_sha": "10ace8f67bb3ecfa8481be4f9906c485d20b2d16",
        "main_ci": 30517146657,
    }
    assert state["tasks"]["EVAL-02A"] == {
        "status": "IN_PROGRESS",
        "pr": 434,
        "branch": "codex/eval-02a-lineup-blind-spot-defense",
    }
    assert state["tasks"]["EVAL-02B"]["status"] == "NOT_STARTED"
    assert state["architecture_convergence"]["status"] == "PASS"
    assert "[PROJECT_STATE.yaml](PROJECT_STATE.yaml)" in next_action
    assert CHECKLIST_PATH in next_action
    assert (
        "当前：B4 EVAL-02A / PR #434 IN_PROGRESS，等待实现、独立 CODE Review "
        "和 exact-head staging。"
        in next_action
    )
    assert "下一项：B5 EVAL-02B；B4 合并前不启动。" in next_action
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
    assert "Status: DONE" in b1
    assert "Merge SHA: dc1a665655add801c4fe5cd7a0f39211d836e916" in b1
    assert "Main CI: 30441901340" in b1
    assert "- [x] PR 合并。" in b1
    b2 = checklist[
        checklist.index("#### B2. EVAL-01B") : checklist.index("#### B3.")
    ]
    assert "Status: DONE" in b2
    assert "PR: #430" in b2
    assert "Source head: dbd70161823c45a1a8e38b68be7de646db2d2a33" in b2
    assert "Merge SHA: 5c2bd6f2e5c23196a25495335da72599e076c8ae" in b2
    assert "Main CI: 30477611652" in b2
    assert "Staging acceptance: PASS" in b2
    assert "- [x] PR 合并。" in b2
    b3 = checklist[
        checklist.index("#### B3. EVAL-01C") : checklist.index("#### B4.")
    ]
    assert "Status: DONE" in b3
    assert "PR: #432" in b3
    assert "Source head: f136bd9c11c67defeed9de39095130f7848aee64" in b3
    assert "Merge SHA: 10ace8f67bb3ecfa8481be4f9906c485d20b2d16" in b3
    assert "Main CI: 30517146657" in b3
    assert "Staging acceptance: PASS" in b3
    assert "- [ ]" not in b3
    assert "- [x] PR 合并。" in b3
    b4 = checklist[
        checklist.index("#### B4. EVAL-02A") : checklist.index("#### B5.")
    ]
    assert "Status: IN_PROGRESS" in b4
    assert "Branch: codex/eval-02a-lineup-blind-spot-defense" in b4
    assert "PR: #434" in b4
    assert "opening_ev = model_probability * opening_decimal_odds - 1" not in b4
    assert "current_ev = model_probability * current_decimal_odds - 1" not in b4
    assert "FROZEN_EV_DISTRIBUTION" in b4
    assert "expected_value(opening_decimal_odds, FROZEN_EV_DISTRIBUTION)" in b4
    assert "expected_value(current_decimal_odds, FROZEN_EV_DISTRIBUTION)" in b4
    assert "movement_ev_share > 0.5 = MOVEMENT_CREATED_DIVERGENCE" in b4
    assert "non-moved and divergence_age_ratio >= 0.6 = STABLE_DIVERGENCE" in b4
    assert "rotation_rate >= 4 / 11 = HIGH_ROTATION" in b4
    assert "minimum advisory canonical settled = 50" in b4
    assert "PERFORMANCE_SCHEMA_VERSION = w2.performance_projection.v3" in b4
    b5 = checklist[
        checklist.index("#### B5. EVAL-02B") : checklist.index("#### B6.")
    ]
    assert "Status: NOT_STARTED" in b5
    assert "W2_ARCHITECTURE_CONVERGENCE_COMPLETE = PASS" in checklist
    for task in FORBIDDEN_TASKS:
        assert task not in state
        assert task not in next_action
        assert task not in checklist
    assert state["staging"]["production_deployed"] is False
    assert state["staging"]["eval_01a_exact_head_acceptance"] == "PASS"
    assert state["staging"]["eval_01b_exact_head_acceptance"] == "PASS"
    assert state["staging"]["eval_01c_exact_head_acceptance"] == "PASS"


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
