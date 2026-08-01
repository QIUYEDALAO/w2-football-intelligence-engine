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
ACTIVE_NEXT_ACTION = "EXECUTE_WAVE_3_C9_THEN_GATE_A_OFFLINE"
SUPERSEDED_A148_ACTION = "INDEPENDENT_REHEARSAL_RECEIPT_REVIEW"

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


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_project_state_v5_separates_task_and_execution_authorities() -> None:
    state = yaml.safe_load(read("PROJECT_STATE.yaml"))

    assert state["schema_version"] == "w2.project_state.v3"
    assert state["active_execution_schema_version"] == "w2.active_execution.v1"
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
    assert state["current_workstream"] == "EVAL-02B-C9-AND-GATE-A"
    assert state["current_phase"] == "WAVE_3_C9_THEN_GATE_A_OFFLINE"
    assert state["current_status"] == "BLOCKED"
    assert state["current_status_detail"] == (
        "WAVE_3_C9_TRUSTED_REBUILD_AUTHORIZED"
    )
    assert state["next_task"] == "EVAL-02B"
    assert state["next_workstream"] == "EVAL-02B-C9-AND-GATE-A"
    assert state["active_next_action"] == ACTIVE_NEXT_ACTION
    assert state["tasks"]["EVAL-02B"]["next_required_action"] == ACTIVE_NEXT_ACTION
    assert "current_pr" in state
    assert state["current_pr_semantics"] == "CURRENT_BUSINESS_IMPLEMENTATION_PR_ONLY"
    assert state["active_context_pr"] == 450
    assert state["active_context_pr_semantics"] == "CURRENT_CONTEXT_AND_GUARD_PR"
    assert state["quarantined_pr"] == 453
    assert set(state["active_issues"]) == {451, 452, 455, 456, 457}

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
    assert eval_02b["contract_authority"] == "FROZEN"
    assert eval_02b["write_side_execution_tranche"] == "COMPLETED"
    for number in ("01", "02", "03", "04"):
        assert eval_02b[f"write_side_implementation_{number}"] == "DONE"
    assert eval_02b["a148_supervised_rehearsal"] == "BLOCKED_PRECONDITION"
    assert eval_02b["rehearsal_command_executed"] is False
    assert eval_02b["actual_provider_calls"] == 0

    a148 = state["historical_receipts"]["a148"]
    assert a148["previous_next_required_action"] == SUPERSEDED_A148_ACTION
    assert a148["fail_closed_barrier"] == "PASS"
    assert a148["provider_execution"] == "NOT_EXECUTED"
    assert a148["actual_provider_calls"] == 0
    assert a148["business_db_writes"] == 0
    assert a148["scheduler_started"] is False
    assert a148["celery_tasks_queued"] == 0
    assert a148["one_shot_authorization_revoked"] is True
    assert a148["end_to_end_chain"] == "NOT_VALIDATED"

    assert state["WAVE_1_FINAL"] == "PASS_WITH_BOUNDED_CARRY_FORWARD"
    assert state["FINAL_GATE_A_GROUPS"] == 28
    assert state["FINAL_EXACT_C1_C11_MAPPINGS"] == 35
    assert state["FINAL_TEST_CONTRACT_SKELETONS"] == 30
    assert state["ISSUE_457_PROJECT_GATE"] == "CLOSED_WITH_OWNER_RISK_ACCEPTANCE"
    assert state["WAVE_2"] == "CLOSED_WITH_EXISTING_C9_BLOCKER"
    assert state["SER_05_INDEPENDENT_ORACLE"] == "PASS"
    assert state["PR_461"] == "INTEGRATED_INTO_PR_460"
    assert state["WAVE_3_AUTHORIZED"] is True
    assert state["wave_1_evidence"]["role_fields_carried_to_pr450"] == 145
    assert state["wave_1_evidence"]["authority_matrix_cell_universe"] == 1305
    assert state["wave_1_evidence"]["currently_accounted_fields"] == 1160
    assert state["wave_1_evidence"]["role_field_disposition"] == (
        "CARRY_TO_PR450_DOCUMENTATION_REPAIR"
    )
    assert state["pr450_guard_closure"]["guards_repaired"] == 145
    assert state["pr450_guard_closure"]["unclassified_removed_guards"] == 0

    assert state["tasks"]["EVAL-03"]["status"] == "NOT_STARTED"
    assert state["architecture_convergence"]["status"] == "PASS"


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

    handoff_documents = (context, next_action, agents, copilot)
    for text in handoff_documents:
        assert "#454 v5" in text
        assert "R5" in text
        assert "#456" in text
        assert "ACTIVE_NEXT_ACTION = EXECUTE_WAVE_3_C9_THEN_GATE_A_OFFLINE" in text
        assert "ACTIVE_CONTEXT_PR = 450" in text
        assert "CURRENT_WORKSTREAM = EVAL-02B-C9-AND-GATE-A" in text
        assert "CURRENT_PHASE = WAVE_3_C9_THEN_GATE_A_OFFLINE" in text
        assert "WAVE_1 = CLOSED_AND_FROZEN" in text
        assert "WAVE_1_FINAL = PASS_WITH_BOUNDED_CARRY_FORWARD" in text
        assert "T00_RERUN = FORBIDDEN_UNLESS_NEW_APPROVED_EVIDENCE" in text
        assert "FINAL_GATE_A_GROUPS = 28" in text
        assert "FINAL_EXACT_C1_C11_MAPPINGS = 35" in text
        assert "FINAL_TEST_CONTRACT_SKELETONS = 30" in text
        assert "ISSUE_457_PROJECT_GATE = CLOSED_WITH_OWNER_RISK_ACCEPTANCE" in text
        assert "WAVE_2 = CLOSED_WITH_EXISTING_C9_BLOCKER" in text
        assert "SER_05_INDEPENDENT_ORACLE = PASS" in text
        assert "PR_461 = INTEGRATED_INTO_PR_460" in text
        assert "WAVE_3_AUTHORIZED = true" in text
        assert "NEXT_CODE_ACTION = C9_TRUSTED_REBUILD_THEN_GATE_A_OFFLINE" in text
        assert "PR_450 = DRAFT" in text
        assert "PR_450_FINAL_ACCEPTANCE_REVIEW = COMPLETED" in text
        assert "PREDEPLOY_C9 = EXISTING_BLOCKER" in text
        assert "PROVIDER = OFF" in text
        assert "REAL_PROVIDER = OFF" in text
        assert "REAL_CANARY = NOT_AUTHORIZED" in text
        assert "PERSISTENT_SCHEDULER = OFF" in text
        assert "CANDIDATE / FORMAL / LOCK / PRODUCTION = OFF" in text
        assert "AUTO_MERGE = FORBIDDEN" in text
        assert SUPERSEDED_A148_ACTION not in text

    assert "TOP_LEVEL_TASK = EVAL-02B" in context
    assert "PRODUCTION_SERIALIZER_IMPLEMENTER" in context
    assert "ORACLE_IMPORTS_PRODUCTION_SERIALIZER = false" in context
    assert "INDEPENDENT_PAIR_HASH_MISMATCH" in context
    assert "INDEPENDENT_BOOTSTRAP_SEED_MISMATCH" in context
    assert "ensure_ascii=True" in asset_audit
    assert "ensure_ascii=False" in asset_audit
    assert "计算权威唯一性" in registry


def test_active_action_is_unique_current_and_historical_receipt_is_bounded() -> None:
    state_text = read("PROJECT_STATE.yaml")
    state = yaml.safe_load(state_text)
    next_action = read("NEXT_ACTION.md")

    assert state["active_next_action"] == ACTIVE_NEXT_ACTION
    assert state["tasks"]["EVAL-02B"]["next_required_action"] == ACTIVE_NEXT_ACTION
    assert f"ACTIVE_NEXT_ACTION = {ACTIVE_NEXT_ACTION}" in next_action
    expected_active_state = {
        "WAVE_1": "CLOSED_AND_FROZEN",
        "T00_RERUN": "FORBIDDEN_UNLESS_NEW_APPROVED_EVIDENCE",
        "NEXT_CODE_ACTION": "C9_TRUSTED_REBUILD_THEN_GATE_A_OFFLINE",
        "PR_450": "DRAFT",
        "PR_450_FINAL_ACCEPTANCE_REVIEW": "COMPLETED",
        "PREDEPLOY_C9": "EXISTING_BLOCKER",
        "PROVIDER": "OFF",
        "REAL_CANARY": "NOT_AUTHORIZED",
        "PERSISTENT_SCHEDULER": "OFF",
        "AUTO_MERGE": "FORBIDDEN",
    }
    for key, value in expected_active_state.items():
        assert state[key] == value
    assert state["WAVE_3_AUTHORIZED"] is True
    assert state["active_context_pr"] == 450

    assert state_text.count(SUPERSEDED_A148_ACTION) == 1
    assert state["historical_receipts"]["a148"][
        "previous_next_required_action"
    ] == SUPERSEDED_A148_ACTION
    assert state["active_next_action"] != SUPERSEDED_A148_ACTION
    assert state["tasks"]["EVAL-02B"]["next_required_action"] != (
        SUPERSEDED_A148_ACTION
    )
    assert SUPERSEDED_A148_ACTION not in next_action

    forbidden_current_directions = (
        "WAIT_FOR_PR450_FINAL_ACCEPTANCE",
        "POST_WAVE_1_CONTEXT_AND_GUARD_CLOSURE",
        "BLOCKED_PENDING_PHASE_MINUS_1_AND_PR450_FINAL_ACCEPTANCE",
        "先执行只读 T00-GOV/T00-SAFE",
    )
    for document in (
        state_text,
        next_action,
        read(CONTEXT_PATH),
        read("AGENTS.md"),
        read(".github/copilot-instructions.md"),
    ):
        assert all(stale not in document for stale in forbidden_current_directions)


def test_master_checklist_remains_historical_task_authority() -> None:
    checklist = read(CHECKLIST_PATH)
    state = yaml.safe_load(read("PROJECT_STATE.yaml"))

    assert "`PROJECT_STATE.yaml` 是 W2 **唯一当前机器可读状态快照**" in checklist
    assert "唯一任务顺序、任务规格和已合并完成回执权威" in checklist
    assert state["task_authority"] == CHECKLIST_PATH
    assert state["active_execution_authority"] == EXECUTION_AUTHORITY
    assert state["current_task"] == "EVAL-02B"
    assert state["current_workstream"] == "EVAL-02B-C9-AND-GATE-A"

    assert "PAIR_IDENTITY_SERIALIZATION" in checklist
    assert "UTF8_CANONICAL_JSON_SORTED_KEYS_COMPACT" in checklist
    assert "Canonical JSON 禁止 NaN/Infinity" in checklist
    assert "ensure_ascii" not in checklist
    assert state["tasks"]["EVAL-02B"]["contract_authority"] == "FROZEN"


def test_script_authority_matrix_schema_and_role_accounting_are_exact() -> None:
    checklist = read(CHECKLIST_PATH)
    state = yaml.safe_load(read("PROJECT_STATE.yaml"))
    matrix = checklist.split("<!-- SCRIPT_AUTHORITY_MATRIX_START -->", 1)[1].split(
        "<!-- SCRIPT_AUTHORITY_MATRIX_END -->", 1
    )[0]
    table_lines = [line for line in matrix.splitlines() if line.startswith("|")]
    expected_header = [
        "path",
        "唯一分类",
        "直接调用方",
        "传递调用链",
        "运行环境",
        "部署引用",
        "运维文档",
        "决定",
        "证据",
    ]

    header = [cell.strip() for cell in table_lines[0].strip("|").split("|")]
    rows = [line for line in table_lines[2:] if line.startswith("| `")]
    parsed_rows = [
        [cell.strip().strip("`") for cell in line.strip("|").split("|")]
        for line in rows
    ]

    assert header == expected_header
    assert len(header) == 9
    assert len(parsed_rows) == 145
    assert all(len(row) == len(expected_header) for row in parsed_rows)
    assert len({row[0] for row in parsed_rows}) == 145
    assert all(row[1] for row in parsed_rows)
    assert state["wave_1_evidence"]["role_fields_carried_to_pr450"] == len(
        parsed_rows
    )
    assert state["wave_1_evidence"]["role_field_disposition"] == (
        "CARRY_TO_PR450_DOCUMENTATION_REPAIR"
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
