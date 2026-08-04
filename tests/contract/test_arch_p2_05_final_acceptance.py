from __future__ import annotations

import re
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CHECKLIST = (
    ROOT
    / "docs/operations/architecture_convergence/"
    "W2_ARCHITECTURE_CONVERGENCE_MASTER_CHECKLIST.md"
)
HISTORICAL_RECEIPTS = {
    "ARCH-00 总清单建立": (371, "09ca14a969b835314c93c122b80c3cfa1bbf9c6c"),
    "ARCH-01 PR#370 收口": (374, "160a67505e2ba725b70250635ee71ce99e11b812"),
    "ARCH-P0-01 报表读取删除": (375, "1e9e811dc5393eb6b270bbe0bfa1fb8579142b4a"),
    "ARCH-P0-02 赔率读取收敛": (376, "dae21e59f949be4ac70b75bbcf0f96d1d03f8266"),
    "ARCH-P0-03 联赛白名单入库": (377, "7bd5088b034a36ec12a23a6aa647a53524ecdce8"),
    "ARCH-P0-04 P0 总验收": (378, "d62e335100ebd41856a5b7822938424a511a5fb0"),
    "ARCH-P1-01 僵尸表删除": (379, "76201af8aad43976ffbcd7d2f72726bac4bc8106"),
    "P1-01 收口 + 清单修订": (380, "8af05ddbacf32370303fb0e57e5097d6634c278e"),
    "ARCH-P1-02 赔率表收敛": (381, "f53b073f5f53e078d75831ad4f2c0c648f32db88"),
    "HYGIENE 清单顺序修正": (382, "db3fd12fedb76e9a9cb074f7a3dcc3294042c2fc"),
    "ARCH-HYGIENE-01": (383, "748b50e5c990c6138193810ec319e0e413a7ab25"),
    "ARCH-HYGIENE-02": (384, "1e252d73d8c9658e6ba60093ed8006dde656db10"),
    "ARCH-P1-04A 评估持久化": (385, "aa59b61d7d60dfda8fb43d293514fcda6beb7664"),
    "ARCH-P1-04B Dashboard 读切换": (
        387,
        "7ffdc0fed42538243be9e6700b8093bb56372920",
    ),
}
TASK_RECEIPTS = {
    "ARCH-GOVERNANCE-01": (393, "35fcac0d99573556c5e9f7a41822e153783efa73"),
    "ARCH-P1-04C": (395, "6eeb411747a1cef624ff4780dbad87d4cec4b26d"),
    "ARCH-P1-03": (419, "5026919fe1b1bbe2d5c6dfd67a2f70b6b0f59768"),
    "ARCH-P1-05": (420, "ba8f10e1809c491a112c13eec28303ceb67d7f74"),
    "ARCH-P1-06": (421, "5fb6ea5172f92633c609dd9c5cc1287b9a231e70"),
    "ARCH-P1-07": (422, "e2f0d5ca895f08e1d4e9ef20ccc8db89a8045e64"),
    "ARCH-P1-08": (423, "a607d65b0b71afbc0caa50c44a6e162cf397e4e4"),
    "ARCH-P2-02": (426, "49c75521325af46551699b27241c0ef4c6bbb7a0"),
    "ARCH-P2-04": (427, "bf21ddcc495b0c8d041c956734d278c1d611f24e"),
    "ARCH-P2-06": (428, "1a46a9e47a478072d37e4ec4c7a44d914e1a127b"),
    "ARCH-P2-05": (429, "86a66ff5c07438b0543d2790165d406d452daedb"),
}


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _is_ancestor(commit: str) -> bool:
    return (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", commit, "HEAD"],
            cwd=ROOT,
            check=False,
        ).returncode
        == 0
    )


def test_p0_p1_p2_receipts_are_real_ancestors() -> None:
    checklist = _text(CHECKLIST)
    for task, (pr, commit) in HISTORICAL_RECEIPTS.items():
        assert f"| {task} | #{pr} | `{commit[:8]}` |" in checklist
        assert _is_ancestor(commit)
    for task, (pr, commit) in TASK_RECEIPTS.items():
        heading = re.search(
            rf"^(?:#### [^\n]*{re.escape(task)}[^\n]*|\*\*{re.escape(task)}[^\n]*)$",
            checklist,
            re.MULTILINE,
        )
        assert heading
        start = heading.start()
        receipt = checklist[start : start + 1_200]
        assert f"PR: #{pr}" in receipt
        assert f"Merge SHA: {commit}" in receipt
        assert _is_ancestor(commit)

    assert "收口 #386 `46aa8d36`" in checklist
    assert "收口 #388 `75e49932`" in checklist
    assert _is_ancestor("46aa8d36d652d31831e7f99543ce16e575b7154d")
    assert _is_ancestor("75e499325875c8a11bf6581422555cf425fac5b2")


def test_done_a1_a7_sections_have_no_unchecked_tasks() -> None:
    checklist = _text(CHECKLIST)
    sections = re.findall(
        r"^#### A[1-7]\..*?(?=^---$|^##### A7 Database authority matrix)",
        checklist,
        re.MULTILINE | re.DOTALL,
    )

    assert len(sections) == 7
    for section in sections:
        if "Status: DONE" in section:
            assert "- [ ]" not in section


def test_single_authorities_and_production_fallback_guards_remain_active() -> None:
    checklist = _text(CHECKLIST)
    state = yaml.safe_load(_text(ROOT / "PROJECT_STATE.yaml"))
    required_metrics = (
        "CURRENT_ODDS_PROJECTION_AUTHORITY_COUNT = 1",
        "CANONICAL_PLAYER_IDENTITY_AUTHORITY_COUNT = 1",
        "CANONICAL_TEAM_IDENTITY_AUTHORITY_COUNT = 1",
        "DASHBOARD_READ_AUTHORITY_COUNT = 1",
        "API_COMPUTE_IMPORT_COUNT = 0",
        "IMPLICIT_EMPTY_DATA_FALLBACK_COUNT = 0",
        "LEGACY_DECISION_RUNTIME_REFERENCE_COUNT = 0",
        "CURRENT_AUTHORITY_CONFLICT_COUNT = 0",
        "PRODUCTION_FALLBACK_REFERENCE_COUNT = 0",
    )
    for metric in required_metrics:
        assert metric in checklist
    assert state["current_state_authority"] == "PROJECT_STATE.yaml"
    assert state["task_authority"].endswith(
        "W2_ARCHITECTURE_CONVERGENCE_MASTER_CHECKLIST.md"
    )

    guard = _text(ROOT / "tests/contract/test_api_projection_read_authority.py")
    assert "test_api_transitive_import_graph_has_no_read_time_computation_packages" in guard
    assert "test_full_execution_surface_has_no_removed_production_fallback_identity" in guard
    assert "test_retired_shadow_strategy_has_no_production_reference" in guard


def test_deployment_is_pull_only_and_has_no_server_build_path() -> None:
    deploy = _text(ROOT / "scripts/deploy_stage7h_staging.sh")
    compose = yaml.safe_load(_text(ROOT / "infra/compose/compose.staging.yml"))
    workflow = _text(ROOT / ".github/workflows/release-candidate.yml")
    for forbidden in (
        "docker build",
        "compose build",
        "git archive",
        "tar -x",
        "uv sync",
        "pip install",
        "/opt/w2/releases/${REVISION}/src",
    ):
        assert forbidden not in deploy
    assert all("build" not in service for service in compose["services"].values())
    for service in ("migration", "api", "worker", "scheduler", "web"):
        assert "immutable" in compose["services"][service]["image"]
    assert "docker/build-push-action@v6" in workflow
    assert "push: true" in workflow


def test_deletions_keep_direct_evidence_and_known_retained_items() -> None:
    checklist = _text(CHECKLIST)
    matrix = checklist.split("<!-- SCRIPT_AUTHORITY_MATRIX_START -->", 1)[1].split(
        "<!-- SCRIPT_AUTHORITY_MATRIX_END -->", 1
    )[0]
    deleted = []
    for line in matrix.splitlines():
        if "| `DELETE` |" not in line:
            continue
        cells = [cell.strip().strip("`") for cell in line.strip("|").split("|")]
        deleted.append(cells[0])
        assert cells[-1] == "D1/D2"
        assert not (ROOT / cells[0]).exists()
    assert len(deleted) == 8

    migration = _text(ROOT / "migrations/versions/0044_drop_retired_shadow_strategy.py")
    assert migration.index("SHADOW_STRATEGY_DROP_REQUIRED_TABLES_MISSING") < migration.index(
        "op.drop_table"
    )
    assert migration.index("SHADOW_STRATEGY_DROP_NONEMPTY") < migration.index("op.drop_table")
    assert migration.index("SHADOW_STRATEGY_DROP_DEPENDENCIES") < migration.index(
        "op.drop_table"
    )
    assert "ARCH-P1-01 僵尸表删除" in checklist and "144→66 表" in checklist
    assert "ARCH-P1-02 赔率表收敛" in checklist and "断言式 drop" in checklist

    cycle = re.search(r"^CYCLE_1_MEMBERS = (.+)$", checklist, re.MULTILINE)
    assert cycle
    assert len(cycle.group(1).split(",")) == 24
    schemas = next(
        line for line in checklist.splitlines() if line.startswith("| `schemas` |")
    )
    assert "KEEP_OFFLINE" in schemas
    assert "INVESTIGATION_REQUIRED" in schemas
    assert "PACKAGE_CYCLE_COUNT = 1" in checklist
    assert "CYCLIC_PACKAGE_COUNT = 24" in checklist


def test_p2_05_is_done_and_eval_02b_is_current() -> None:
    checklist = _text(CHECKLIST)
    state = yaml.safe_load(_text(ROOT / "PROJECT_STATE.yaml"))
    section = checklist[checklist.index("**ARCH-P2-05") : checklist.index("### 阶段 B")]

    assert "Status: DONE" in section
    assert "P2_ARCHITECTURE_FINAL_ACCEPTANCE = PASS" in section
    assert "- [x] exact-head FULL CI、外部验收与 PR 合并" in section
    assert "- [ ]" not in section
    assert "W2_ARCHITECTURE_CONVERGENCE_COMPLETE = PASS" in section
    assert state["current_task"] == "EVAL-02B"
    assert state["current_status"] == "PASS"
    assert state["current_pr"] is None
    assert state["tasks"]["ARCH-P2-05"]["status"] == "DONE"
    assert state["tasks"]["EVAL-01A"]["status"] == "DONE"
    assert state["tasks"]["EVAL-01B"]["status"] == "DONE"
    assert state["tasks"]["EVAL-01C"]["status"] == "DONE"
    assert state["tasks"]["EVAL-02A"]["status"] == "DONE"
    assert state["tasks"]["EVAL-02B"]["status"] == "PASS"
