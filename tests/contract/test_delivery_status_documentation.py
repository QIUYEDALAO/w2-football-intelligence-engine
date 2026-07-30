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
    assert state["current_task"] == "EVAL-02B"
    assert state["current_status"] == "BLOCKED"
    assert state["current_pr"] is None
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
        "status": "DONE",
        "pr": 434,
        "merge_sha": "427cb2203d943304582e5aa3f6b55e5d6b8adce0",
        "main_ci": 30556679131,
    }
    assert state["tasks"]["EVAL-02B"] == {
        "status": "BLOCKED",
        "start_authorized": False,
        "audit_as_of": "2026-07-30T16:06:59.736350Z",
        "audit_sha256": (
            "c4099f973f46514c3105911eee9bf87accd20f98b2430998868716d8ae13e70d"
        ),
        "data_blocker": {
            "dynamic_prematch_evaluations": 0,
            "lineup_confirmed_events": 0,
            "exact_pre_post_pairs": 0,
            "results_without_unique_canonical_competition_season_identity": 35,
        },
        "contract_authority": "FROZEN",
        "data_acquisition_plan": "AUTHORIZED",
        "runtime_collection_authorized": False,
        "next_required_action": "IDENTITY_REMEDIATION_DESIGN",
    }
    assert state["tasks"]["EVAL-03"]["status"] == "NOT_STARTED"
    assert state["architecture_convergence"]["status"] == "PASS"
    assert "[PROJECT_STATE.yaml](PROJECT_STATE.yaml)" in next_action
    assert CHECKLIST_PATH in next_action
    assert (
        "当前：B5 EVAL-02B 仍为 BLOCKED；合同权威已冻结、"
        "数据获取方案已授权，但运行采集未授权。" in next_action
    )
    assert (
        "下一步：B5 IDENTITY_REMEDIATION_DESIGN；"
        "EVAL_02B_START_AUTHORIZED = false，B7 EVAL-03 仍为 NOT_STARTED。"
        in next_action
    )
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
    assert "Status: DONE" in b4
    assert "Branch: codex/eval-02a-lineup-blind-spot-defense" in b4
    assert "PR: #434" in b4
    assert "Source head: 43a9e5aae1da6821edfc88d048c680b52ff870fb" in b4
    assert "Merge SHA: 427cb2203d943304582e5aa3f6b55e5d6b8adce0" in b4
    assert "Main CI: 30556679131" in b4
    assert "Staging acceptance: PASS" in b4
    assert "opening_ev = model_probability * opening_decimal_odds - 1" not in b4
    assert "current_ev = model_probability * current_decimal_odds - 1" not in b4
    assert "FROZEN_EV_DISTRIBUTION" in b4
    assert "expected_value(opening_decimal_odds, FROZEN_EV_DISTRIBUTION)" in b4
    assert "expected_value(current_decimal_odds, FROZEN_EV_DISTRIBUTION)" in b4
    assert "movement_ev_share > 0.5 = MOVEMENT_CREATED_DIVERGENCE" in b4
    assert "non-moved and divergence_age_ratio >= 0.6 = STABLE_DIVERGENCE" in b4
    assert "rotation_rate >= 4 / 11 = HIGH_ROTATION" in b4
    assert "minimum advisory canonical settled = 50" in b4
    assert (
        "ADVISORY_DELTA_SCHEMA_VERSION = w2.advisory_blind_spot_policy.v2" in b4
    )
    assert "PERFORMANCE_SCHEMA_VERSION = w2.performance_projection.v3" in b4
    assert "- [x] PR 合并。" in b4
    b5 = checklist[
        checklist.index("#### B5. EVAL-02B") : checklist.index("#### B6.")
    ]
    assert "Status: BLOCKED" in b5
    assert "EVAL_02B_START_AUTHORIZED = false" in b5
    assert "AUDIT_AS_OF = 2026-07-30T16:06:59.736350Z" in b5
    assert (
        "AUDIT_SHA256 = "
        "c4099f973f46514c3105911eee9bf87accd20f98b2430998868716d8ae13e70d"
        in b5
    )
    assert "dynamic_prematch_evaluations 0" in b5
    assert "lineup_confirmed_events 0" in b5
    assert "exact pre/post pairs 0" in b5
    assert "35 results 缺唯一 canonical competition/season identity" in b5
    for frozen_coordinate in (
        "CONTRACT_AUTHORITY = FROZEN",
        "DATA_ACQUISITION_PLAN = AUTHORIZED",
        "RUNTIME_COLLECTION_AUTHORIZED = false",
        "NEXT_REQUIRED_ACTION = IDENTITY_REMEDIATION_DESIGN",
        "PAIR_SCOPE = PER_COMPETITION_X_MARKET",
        "PAIR_GRAIN = ONE_CANONICAL_FIXTURE_PAIR",
        "MINIMUM_ELIGIBLE_TOTAL_PAIRS = 120",
        "TIME_SPLIT = STRICT_CHRONOLOGICAL_70_30",
        "MINIMUM_VALIDATION_PAIRS = 36",
        "BOOTSTRAP_ITERATIONS = 10000",
        "BOOTSTRAP_UNIT = PAIRED_VALIDATION_FIXTURE",
        "MINIMUM_COMPETITIONS = NOT_APPLICABLE",
        "paired_log_loss_improvement =",
        "baseline_log_loss - candidate_log_loss",
        "log_loss_improvement_ci_low > 0",
        "RPS_ROLE = DIAGNOSTIC_ONLY",
        "COVERAGE_ROLE = DIAGNOSTIC_ONLY",
        "REVALIDATE_AFTER_DAYS = 90",
        "REVALIDATE_AFTER_NEW_PAIRS = 60",
        "CI_CONTAINS_ZERO = FREEZE_ADJUSTMENT_TO_ZERO",
        "pre.evaluated_at < lineup_confirmed_at <= post.capture_at",
        "LEAGUE_SCOPE",
        "MARKET_SCOPE",
        "ENDPOINT_SCOPE",
        "CAPTURE_CADENCE",
        "DAILY_REQUEST_BUDGET",
        "ROLLBACK",
        "PROVIDER_CALL_LIMIT",
    ):
        assert frozen_coordinate in b5
    for identity_rule in (
        "同一 canonical fixture、competition、season、market、selection",
        "首发确认前最后一个合格持久化评估",
        "首发确认后第一个使用 fresh",
        "每场 fixture",
        "只允许一个 pair",
        "跨赛季、跨联赛、marker-only 和 superseded 数据全部排除",
        "禁止 fuzzy、名称猜测或跨 bookmaker/line 拼接",
    ):
        assert identity_rule in b5
    for acquisition_rule in (
        "35 个历史 results 只能使用已持久化的",
        "仅精确唯一",
        "多义或缺失继续保持 blocker",
        "不得调用 Provider",
        "不得用 direct SQL",
        "独立、幂等、可回滚 PR",
        "`dynamic_prematch_evaluations`、`lineup_confirmed_events` 的真实写侧",
        "不得制造历史样本或使用 synthetic 数据充数",
        "只有另行取得 activation 授权后",
        "Recommendation、Candidate、Formal、Lock、Production 全程保持关闭",
    ):
        assert acquisition_rule in b5
    assert "500 个验证样本" in b5
    assert "Bootstrap 只重采样 validation fixture pairs" in b5
    assert "排序后的 canonical pair" in b5
    assert "identity hash 派生" in b5
    assert "2.5% 与 97.5% 分位数" in b5
    assert "RPS 与 coverage 必须输出" in b5
    assert "不得作为 blocker" in b5
    b7 = checklist[
        checklist.index("#### B7. EVAL-03") : checklist.index("### 模型升级")
    ]
    assert "Status: NOT_STARTED" in b7
    assert "W2_ARCHITECTURE_CONVERGENCE_COMPLETE = PASS" in checklist
    for task in FORBIDDEN_TASKS:
        assert task not in state
        assert task not in next_action
        assert task not in checklist
    assert state["staging"]["production_deployed"] is False
    assert state["staging"]["eval_01a_exact_head_acceptance"] == "PASS"
    assert state["staging"]["eval_01b_exact_head_acceptance"] == "PASS"
    assert state["staging"]["eval_01c_exact_head_acceptance"] == "PASS"
    assert state["staging"]["eval_02a_exact_head_acceptance"] == "PASS"


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
