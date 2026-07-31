from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CHECKLIST_PATH = (
    "docs/operations/architecture_convergence/"
    "W2_ARCHITECTURE_CONVERGENCE_MASTER_CHECKLIST.md"
)
AUDIT_PATH = "docs/operations/W2_INDEPENDENT_FINAL_AUDIT_20260731.md"
ASSET_AUDIT_PATH = "docs/operations/W2_ASSET_UNIQUENESS_AUDIT_20260731.md"
REGISTRY_PATH = "docs/operations/W2_AUDIT_PERSPECTIVE_REGISTRY.md"
CONTEXT_PATH = "AI_PROJECT_CONTEXT.md"
EXECUTION_AUTHORITY = (
    "https://github.com/QIUYEDALAO/w2-football-intelligence-engine/issues/454"
)

CRITICAL_BLOCKERS = (
    "C1_PROVIDER_DEFAULT_FAIL_OPEN",
    "C2_RUNTIME_AUTHORIZATION_BYPASS",
    "C3_CLI_SEASON_POLICY_MISMATCH",
    "C4_EXECUTE_DEFAULT_DB_PERSISTENCE",
    "C5_DB_RUN_LOCK_OPTIONAL",
    "C6_PROVIDER_LEDGER_NOT_ATOMIC",
    "C7_UNCERTAIN_TIMEOUT_RETRY",
    "C8_SCHEMA_OR_EMPTY_DATA_SILENT_SUCCESS",
    "C9_LINEUP_MATERIALIZATION_FAILURE_SWALLOWED",
    "C10_SCHEDULER_RESTART_POLICY_MISMATCH",
    "C11_LEDGER_INTEGRITY_AND_QUOTA_EVIDENCE_SILENT_FAILURE",
    "R5_CANONICAL_SERIALIZATION_AUTHORITY_SPLIT",
)
REQUIRED_CANARY_DELTAS = (
    "actual_provider_calls_delta",
    "provider_request_ledger_delta",
    "raw_payload_delta",
    "endpoint_capture_delta",
    "lineup_event_delta",
    "dynamic_evaluation_v2_delta",
    "five_state_snapshot_delta",
    "exact_pair_delta",
)
RISK_FAMILIES = (
    "R1_DEFAULT_ALLOW_OR_MISSING_AUTHORITY",
    "R2_SILENT_FAILURE_OR_FAILURE_DOWNGRADE",
    "R3_EXTERNAL_SIDE_EFFECT_LOCAL_STATE_NON_ATOMICITY",
    "R4_AUTHORITY_SPLIT_CONCURRENCY_IDENTITY_DRIFT",
    "R5_COMPUTATION_AUTHORITY_SPLIT",
)


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_project_state_v5_separates_task_and_execution_authorities() -> None:
    state = yaml.safe_load(read("PROJECT_STATE.yaml"))

    assert state["schema_version"] == "w2.project_state.v5"
    assert state["current_state_authority"] == "PROJECT_STATE.yaml"
    assert state["task_authority"] == CHECKLIST_PATH
    assert state["active_execution_authority"] == EXECUTION_AUTHORITY
    assert state["master_task_and_receipt_authority"] == CHECKLIST_PATH
    assert state["handoff_authority"] == CONTEXT_PATH
    assert state["independent_audit_authority"] == AUDIT_PATH
    assert state["asset_uniqueness_audit_authority"] == ASSET_AUDIT_PATH
    assert state["audit_perspective_registry_authority"] == REGISTRY_PATH
    assert state["workflow_governance_issue"] == 455
    assert state["computation_authority_issue"] == 456

    assert state["current_task"] == "EVAL-02B"
    assert state["current_workstream"] == "EVAL-02B-T00"
    assert state["current_phase"] == "PHASE_00_LOCAL_SYNC_AND_T00_GOV"
    assert state["current_status"] == "BLOCKED"
    assert state["current_status_detail"] == (
        "BLOCKED_GOVERNANCE_RUNTIME_AND_COMPUTATION_AUTHORITY_REMEDIATION"
    )
    assert state["next_task"] == "EVAL-02B"
    assert state["next_workstream"] == "T00-GOV"
    assert state["quarantined_pr"] == 453
    assert set(state["active_issues"]) == {451, 452, 455, 456, 457}

    assert tuple(state["risk_families"]) == RISK_FAMILIES
    assert all(
        state["risk_families"][family] == "OPEN_SCAN_REQUIRED"
        for family in RISK_FAMILIES
    )

    for task in (
        "ARCH-P2-02",
        "ARCH-P2-03",
        "ARCH-P2-04",
        "ARCH-P2-05",
        "ARCH-P2-06",
        "EVAL-01A",
        "EVAL-01B",
        "EVAL-01C",
        "EVAL-02A",
    ):
        assert state["tasks"][task]["status"] == "DONE"

    eval_02b = state["tasks"]["EVAL-02B"]
    assert eval_02b["status"] == "BLOCKED"
    assert eval_02b["contract_authority"] == (
        "FROZEN_BUT_PAIR_SERIALIZATION_INCOMPLETE"
    )
    assert eval_02b["write_side_execution_tranche"] == "COMPLETED"
    for number in ("01", "02", "03", "04"):
        assert eval_02b[f"write_side_implementation_{number}"] == "DONE"
    assert eval_02b["end_to_end_status"] == "NOT_VALIDATED"
    assert eval_02b["a148_supervised_rehearsal"] == "SAFE_FAIL_CLOSED_ONLY"
    assert eval_02b["rehearsal_command_executed"] is False
    assert eval_02b["actual_provider_calls"] == 0
    assert tuple(eval_02b["critical_blockers"]) == CRITICAL_BLOCKERS
    assert eval_02b["c9_contaminated_pr"] == 453
    assert eval_02b["c9_clean_rebuild_required"] is True

    execution_order = state["execution_order"]
    assert execution_order.index("T00_SAFE_R1_R2_R3_R4_R5_AND_ASSET_INVENTORY") < (
        execution_order.index(
            "R5_CANONICAL_SERIALIZATION_AUTHORITY_AND_VERSIONED_MIGRATION"
        )
    )
    assert execution_order.index(
        "R5_CANONICAL_SERIALIZATION_AUTHORITY_AND_VERSIONED_MIGRATION"
    ) < execution_order.index("TRUSTED_MAIN_C9_REBUILD_NEW_DRAFT_PR")

    assert state["tasks"]["EVAL-03"]["status"] == "NOT_STARTED"
    assert state["architecture_convergence"]["status"] == "PASS"
    assert state["architecture_convergence"]["scope_remains_valid"] is True


def test_canary_contract_requires_independent_hard_failures() -> None:
    state = yaml.safe_load(read("PROJECT_STATE.yaml"))
    canary = state["canary_acceptance"]

    assert canary["status"] == "NOT_AUTHORIZED"
    assert tuple(canary["required_deltas"]) == REQUIRED_CANARY_DELTAS
    assert all(canary["required_deltas"][key] == ">0" for key in REQUIRED_CANARY_DELTAS)
    assert canary["zero_required_delta_result"] == "FAILED"
    assert canary["lineage_mismatch_result"] == "FAILED"
    assert canary["serializer_version_missing_result"] == "FAILED"
    assert canary["independent_pair_hash_mismatch_result"] == "FAILED"
    assert canary["independent_bootstrap_seed_mismatch_result"] == "FAILED"
    assert canary["nan_or_infinity_result"] == "FAILED"
    assert canary["auto_retry"] is False

    required_lineage = set(canary["required_lineage_fields"])
    assert {
        "run_id",
        "authorization_id",
        "competition_id",
        "season",
        "fixture_id",
        "provider",
        "bookmaker",
        "market",
        "selection",
        "exact_line",
        "capture_at",
        "raw_payload_sha256",
        "endpoint_capture_id",
        "lineup_input_hash",
        "evaluation_id",
        "pair_hash",
        "exact_git_sha",
        "serializer_version",
    } <= required_lineage

    oracle = state["oracle_independence"]
    assert oracle["production_serializer_implementer_must_differ_from_oracle_author"]
    assert oracle["oracle_imports_production_serializer"] is False
    assert oracle["independent_reviewer_recorded_required"] is True

    stop = state["codex_stop_line"]
    assert stop["real_provider_call_executed"] is False
    assert stop["real_canary_authorization_created"] is False
    assert stop["auto_merge_executed"] is False
    assert stop["stop_after_offline_evidence_package"] is True


def test_handoff_documents_are_synchronized_to_v5() -> None:
    context = read(CONTEXT_PATH)
    next_action = read("NEXT_ACTION.md")
    agents = read("AGENTS.md")
    copilot = read(".github/copilot-instructions.md")
    registry = read(REGISTRY_PATH)
    asset_audit = read(ASSET_AUDIT_PATH)

    for text in (context, next_action, agents, copilot):
        assert "#454 v5" in text
        assert "EVAL-02B-T00" in text
        assert "R5" in text
        assert "#456" in text

    assert "TOP_LEVEL_TASK = EVAL-02B" in context
    assert "CURRENT_WORKSTREAM = EVAL-02B-T00" in context
    assert "PRODUCTION_SERIALIZER_IMPLEMENTER" in context
    assert "ORACLE_IMPORTS_PRODUCTION_SERIALIZER = false" in context
    assert "INDEPENDENT_PAIR_HASH_MISMATCH" in context
    assert "INDEPENDENT_BOOTSTRAP_SEED_MISMATCH" in context
    assert "ensure_ascii=True" in asset_audit
    assert "ensure_ascii=False" in asset_audit
    assert "计算权威唯一性" in registry


def test_master_checklist_remains_historical_task_authority() -> None:
    checklist = read(CHECKLIST_PATH)
    state = yaml.safe_load(read("PROJECT_STATE.yaml"))

    assert "`PROJECT_STATE.yaml` 是 W2 **唯一当前机器可读状态快照**" in checklist
    assert "唯一任务顺序、任务规格和已合并完成回执权威" in checklist
    assert state["task_authority"] == CHECKLIST_PATH
    assert state["active_execution_authority"] == EXECUTION_AUTHORITY
    assert state["current_task"] == "EVAL-02B"
    assert state["current_workstream"] == "EVAL-02B-T00"

    assert "PAIR_IDENTITY_SERIALIZATION" in checklist
    assert "UTF8_CANONICAL_JSON_SORTED_KEYS_COMPACT" in checklist
    assert "Canonical JSON 禁止 NaN/Infinity" in checklist
    assert "ensure_ascii" not in checklist
    assert state["tasks"]["EVAL-02B"]["contract_authority"] == (
        "FROZEN_BUT_PAIR_SERIALIZATION_INCOMPLETE"
    )


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
