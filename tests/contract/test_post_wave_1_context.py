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
CANARY_RECEIPT_PATH = "docs/operations/W2_WAVE4_REAL_CANARY_RECEIPT_20260802.md"
POSTDEPLOY_RECEIPT_PATH = "docs/operations/W2_VPS_POSTDEPLOY_RECEIPT_20260802.md"
RECOVERY_RECEIPT_PATH = "docs/operations/W2_PRODUCTION_RECOVERY_RECEIPT_20260803.md"
EXECUTION_AUTHORITY = (
    "https://github.com/QIUYEDALAO/w2-football-intelligence-engine/issues/454"
)
ACTIVE_NEXT_ACTION = "POST_RECOVERY_OBSERVATION_AND_DYNAMIC_EVALUATION_READINESS"
CURRENT_SHA = "3b38e283959394459671e441132c1e1cb9d1f019"
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
    assert state["current_workstream"] == ACTIVE_NEXT_ACTION
    assert state["current_phase"] == "PRODUCTION_RECOVERY_CONTEXT_CLOSURE_COMPLETE"
    assert state["current_status"] == "PASS"
    assert (
        state["current_status_detail"]
        == "DASHBOARD_REAL_DATA_RECOVERY_PASS_CONTROLLED_COLLECTION_ON"
    )
    assert state["next_task"] == "EVAL-02B"
    assert state["next_workstream"] == ACTIVE_NEXT_ACTION
    assert state["active_next_action"] == ACTIVE_NEXT_ACTION
    assert state["tasks"]["EVAL-02B"]["next_required_action"] == ACTIVE_NEXT_ACTION
    assert "current_pr" in state
    assert state["current_pr_semantics"] == "CURRENT_BUSINESS_IMPLEMENTATION_PR_ONLY"
    assert state["active_context_pr"] is None
    assert state["active_context_pr_semantics"] == "NO_ACTIVE_CONTEXT_PR_AFTER_CLOSURE"
    assert state["audit_baseline_sha"] == "dbc8e1e8aa74a7613fd7121bf6026890c3ee06c6"
    assert state["current_main_sha"] == CURRENT_SHA
    assert state["deployed_sha"] == state["current_main_sha"]
    assert state["main_post_merge_ci"] == 30761641987
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
    assert eval_02b["status"] == "PASS"
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
    assert state["TOP_LEVEL_TASK"] == "EVAL-02B"
    assert state["WAVE_1"] == "PASS_AND_FROZEN"
    assert state["WAVE_2"] == "PASS"
    assert state["WAVE_3"] == "PASS"
    assert state["WAVE_4_REAL_CANARY"] == "PASS"
    assert state["EVAL_02B_REAL_CHAIN"] == "PROVEN"
    assert state["REAL_CANARY_PROVIDER_CALLS"] == 5
    assert state["REAL_CANARY_EVIDENCE_SHA256"] == (
        "30e961cbedee33b5ec74bf3eabbd80a202ced3b9b21483160896812442ddd1f4"
    )
    assert state["SER_05_INDEPENDENT_ORACLE"] == "PASS"
    assert state["PR_461"] == "INTEGRATED_INTO_PR_460"
    assert eval_02b["real_chain"] == "PROVEN"
    assert eval_02b["real_canary_provider_calls"] == 5
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

    assert canary["status"] == "PASS"
    assert tuple(canary["required_deltas"]) == REQUIRED_CANARY_DELTAS
    assert all(canary["required_deltas"][key] == ">0" for key in REQUIRED_CANARY_DELTAS)
    assert canary["zero_required_delta_result"] == "FAILED"
    assert canary["lineage_mismatch_result"] == "FAILED"
    assert canary["serializer_version_missing_result"] == "FAILED"
    assert canary["independent_pair_hash_mismatch_result"] == "FAILED"
    assert canary["independent_bootstrap_seed_mismatch_result"] == "FAILED"
    assert canary["nan_or_infinity_result"] == "FAILED"
    assert canary["auto_retry"] is False
    assert canary["actual_provider_calls"] == 5
    assert canary["provider_request_ledger_delta"] == 5
    assert canary["raw_payload_delta"] == 4
    assert canary["endpoint_capture_delta"] == 5
    assert canary["lineup_event_delta"] == 1
    assert canary["dynamic_evaluation_v2_delta"] == 2
    assert canary["five_state_snapshot_delta"] == 2
    assert canary["exact_pair_delta"] == 1
    assert canary["bootstrap_seed_evidence_delta"] == 1
    assert canary["independent_oracle"] == "PASS"
    assert canary["db_admission_validator"] == "PASS"

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
    assert stop["context_closure_provider_call_delta"] == 0
    assert stop["real_canary_authorization_created"] is False
    assert stop["scheduler_restarted_in_context_closure"] is False
    assert stop["deployment_executed_in_context_closure"] is False
    assert stop["auto_merge_executed"] is False
    assert stop["stop_after_offline_evidence_package"] is False


def test_wave4_receipt_is_complete_and_sanitized() -> None:
    state = yaml.safe_load(read("PROJECT_STATE.yaml"))
    receipt = read(CANARY_RECEIPT_PATH)

    assert state["REAL_CANARY_RECEIPT"] == CANARY_RECEIPT_PATH
    for evidence in (
        "EXACT_HEAD = b74659e5afdc9047d1e84759df11c7f58f929c86",
        "AUTHORIZATION_SHA256 = "
        "51339d452bcbf590c8a9710b67e6df665a3d85f83140d1ae7663573146afdd79",
        "EVIDENCE_SHA256 = "
        "30e961cbedee33b5ec74bf3eabbd80a202ced3b9b21483160896812442ddd1f4",
        "ACTUAL_PROVIDER_CALLS = 5",
        "PROVIDER_REQUEST_LOG_DELTA = 5",
        "RAW_PAYLOAD_DELTA = 4",
        "ENDPOINT_CAPTURE_DELTA = 5",
        "LINEUP_EVENT_DELTA = 1",
        "DYNAMIC_EVALUATION_V2_DELTA = 2",
        "FIVE_STATE_SNAPSHOT_DELTA = 2",
        "EXACT_PAIR_DELTA = 1",
        "BOOTSTRAP_SEED_EVIDENCE_DELTA = 1",
        "INDEPENDENT_ORACLE = PASS",
        "DB_ADMISSION_VALIDATOR = PASS",
        "PRODUCT_DATABASE_WRITTEN = false",
    ):
        assert evidence in receipt

    for redacted_field in (
        "FIXTURE_ID =",
        "API" + "_KEY =",
        "DATABASE_URL =",
        "VPS_ADDRESS =",
        "PASS" + "WORD =",
    ):
        assert redacted_field not in receipt.upper()


def test_postdeploy_receipt_and_state_are_complete_and_sanitized() -> None:
    state = yaml.safe_load(read("PROJECT_STATE.yaml"))
    receipt = read(POSTDEPLOY_RECEIPT_PATH)

    assert state["historical_postdeploy_receipt"] == POSTDEPLOY_RECEIPT_PATH
    staging = state["staging"]
    assert staging["production_deployed"] is False
    assert staging["vps_deployed"] is True
    assert staging["deployed_sha"] == "fe03a8267d7086c87557c267afb12d32433bd2cf"
    assert staging["main_post_merge_ci"] == 30746096431
    assert staging["migration_head"] == "0050_gate_a_runtime_selection"
    assert staging["release_sync"] == "PASS"
    assert staging["scheduler_running_count"] == 0
    assert staging["real_provider_call_delta"] == 0
    assert staging["canary_database_deleted"] is True
    for evidence in (
        "MAIN_POST_MERGE_CI_RUN = 30746096431",
        "DEPLOYED_SHA = fe03a8267d7086c87557c267afb12d32433bd2cf",
        "MIGRATION_HEAD = 0050_gate_a_runtime_selection",
        "HEALTH = PASS",
        "READY = PASS",
        "RELEASE_SYNC = PASS",
        "SCHEDULER_RUNNING_COUNT = 0",
        "REAL_PROVIDER_CALL_DELTA = 0",
        "CANARY_DATABASE_DELETED = true",
        "AUTO_MERGE_EXECUTED = false",
    ):
        assert evidence in receipt
    for redacted_field in (
        "VPS_ADDRESS =",
        "PUBLIC_URL =",
        "DATABASE_NAME =",
        "DATABASE_URL =",
        "API" + "_KEY =",
        "PASS" + "WORD =",
    ):
        assert redacted_field not in receipt.upper()


def test_production_recovery_receipt_and_state_are_complete_and_sanitized() -> None:
    state = yaml.safe_load(read("PROJECT_STATE.yaml"))
    receipt = read(RECOVERY_RECEIPT_PATH)
    recovery = state["production_recovery"]

    assert state["deployment_receipt"] == RECOVERY_RECEIPT_PATH
    assert recovery["receipt"] == RECOVERY_RECEIPT_PATH
    assert recovery["status"] == "PASS"
    assert recovery["dashboard_real_data_recovery"] == "PASS"
    assert recovery["public_dashboard_cards"] == 51
    assert recovery["production_future_fixtures"] == 51
    assert recovery["provider_request_delta"] == 58
    assert recovery["endpoint_capture_delta"] == 58
    assert recovery["provider_errors"] == 0
    assert recovery["provider_ledger_reconciled"] is True
    assert recovery["staging_seed_used"] is False
    assert recovery["collection_ready_competitions"] == [
        "brasileirao_serie_a",
        "chinese_super_league",
        "allsvenskan",
        "eliteserien",
    ]
    assert recovery["registered_competitions_missing_future_refresh_and_matchday_policy"] == [
        "argentina_primera",
        "bundesliga",
        "eredivisie",
        "la_liga",
        "ligue_1",
        "mls",
        "premier_league",
        "primeira_liga",
        "serie_a",
    ]
    assert recovery["persistent_scheduler"] == "ON_CONTROLLED"
    assert recovery["scheduler_concurrency"] == 1
    assert recovery["provider_attempts"] == 1
    assert recovery["daily_hard_cap"] == 120
    assert recovery["tick_hard_cap"] == 30
    assert recovery["dynamic_evaluation_v2"] == 0
    assert recovery["explicit_not_ready_cards"] == 51
    assert recovery["dynamic_evaluation_production_recovery"] == "PENDING"
    assert recovery["eval_03"] == "NOT_STARTED"
    assert recovery["cold_pull_slo"] == "NOT_PROVEN"
    assert {recovery[key] for key in ("candidate", "formal", "lock", "production")} == {
        "OFF"
    }

    for evidence in (
        f"CURRENT_MAIN_SHA = {CURRENT_SHA}",
        f"DEPLOYED_SHA = {CURRENT_SHA}",
        "DASHBOARD_REAL_DATA_RECOVERY = PASS",
        "PUBLIC_DASHBOARD_CARDS = 51",
        "PRODUCTION_FUTURE_FIXTURES = 51",
        "PROVIDER_REQUEST_DELTA = 58",
        "ENDPOINT_CAPTURE_DELTA = 58",
        "PROVIDER_ERRORS = 0",
        "PERSISTENT_SCHEDULER = ON_CONTROLLED",
        "SCHEDULER_CONCURRENCY = 1",
        "PROVIDER_ATTEMPTS = 1",
        "DAILY_HARD_CAP = 120",
        "TICK_HARD_CAP = 30",
        "DYNAMIC_EVALUATION_V2 = 0",
        "EXPLICIT_NOT_READY_CARDS = 51",
        "EVAL-03 = NOT STARTED",
        "COLD_PULL_SLO = NOT_PROVEN",
        f"ACTIVE_NEXT_ACTION = {ACTIVE_NEXT_ACTION}",
    ):
        assert evidence in receipt

    for redacted_field in (
        "FIXTURE_ID =",
        "VPS_ADDRESS =",
        "PUBLIC_URL =",
        "DATABASE_NAME =",
        "DATABASE_URL =",
        "CONTAINER_ID =",
        "RAW_PAYLOAD =",
        "API" + "_KEY =",
        "PASS" + "WORD =",
    ):
        assert redacted_field not in receipt.upper()


def test_handoff_documents_are_synchronized_to_v5() -> None:
    context = read(CONTEXT_PATH)
    next_action = read("NEXT_ACTION.md")
    agents = read("AGENTS.md")
    copilot = read(".github/copilot-instructions.md")
    registry = read(REGISTRY_PATH)
    asset_audit = read(ASSET_AUDIT_PATH)

    handoff_documents = (context, next_action, agents, copilot)
    for text in handoff_documents:
        assert "TOP_LEVEL_TASK = EVAL-02B" in text
        assert f"ACTIVE_NEXT_ACTION = {ACTIVE_NEXT_ACTION}" in text
        assert "ACTIVE_CONTEXT_PR = NONE" in text
        assert f"CURRENT_WORKSTREAM = {ACTIVE_NEXT_ACTION}" in text
        assert "CURRENT_PHASE = PRODUCTION_RECOVERY_CONTEXT_CLOSURE_COMPLETE" in text
        assert "AUDIT_BASELINE_SHA = dbc8e1e8aa74a7613fd7121bf6026890c3ee06c6" in text
        assert f"CURRENT_MAIN_SHA = {CURRENT_SHA}" in text
        assert f"DEPLOYED_SHA = {CURRENT_SHA}" in text
        assert "DASHBOARD_REAL_DATA_RECOVERY = PASS" in text
        assert "PUBLIC_DASHBOARD_CARDS = 51" in text
        assert "PRODUCTION_FUTURE_FIXTURES = 51" in text
        assert "PROVIDER_REQUEST_DELTA = 58" in text
        assert "ENDPOINT_CAPTURE_DELTA = 58" in text
        assert "PROVIDER_ERRORS = 0" in text
        assert (
            "COLLECTION_READY_COMPETITIONS = "
            "brasileirao_serie_a,chinese_super_league,allsvenskan,eliteserien"
        ) in text
        assert "PROVIDER = ON_CONTROLLED" in text
        assert "REAL_PROVIDER = ON_CONTROLLED" in text
        assert "PERSISTENT_SCHEDULER = ON_CONTROLLED" in text
        assert "SCHEDULER_CONCURRENCY = 1" in text
        assert "PROVIDER_ATTEMPTS = 1" in text
        assert "DAILY_HARD_CAP = 120" in text
        assert "TICK_HARD_CAP = 30" in text
        assert "DYNAMIC_EVALUATION_V2 = 0" in text
        assert "EXPLICIT_NOT_READY_CARDS = 51" in text
        assert "DYNAMIC_EVALUATION_PRODUCTION_RECOVERY = PENDING" in text
        assert "EVAL-03 = NOT STARTED" in text
        assert "COLD_PULL_SLO = NOT_PROVEN" in text
        assert "NEXT_CODE_ACTION = NONE_AUTHORIZED" in text
        assert "CANDIDATE = OFF" in text
        assert "FORMAL = OFF" in text
        assert "LOCK = OFF" in text
        assert "PRODUCTION = OFF" in text
        assert "AUTO_MERGE = FORBIDDEN" in text
        assert SUPERSEDED_A148_ACTION not in text
        for competition_id in (
            "argentina_primera",
            "bundesliga",
            "eredivisie",
            "la_liga",
            "ligue_1",
            "mls",
            "premier_league",
            "primeira_liga",
            "serie_a",
        ):
            assert competition_id in text

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
        "WAVE_1": "PASS_AND_FROZEN",
        "T00_RERUN": "FORBIDDEN_UNLESS_NEW_APPROVED_EVIDENCE",
        "NEXT_CODE_ACTION": "NONE_AUTHORIZED",
        "PR_450": "ACCEPTED_HEAD_FOR_FINAL_INTEGRATION",
        "PR_450_FINAL_ACCEPTANCE_REVIEW": "COMPLETED",
        "PREDEPLOY_C9": "PASS",
        "PROVIDER": "ON_CONTROLLED",
        "REAL_PROVIDER": "ON_CONTROLLED",
        "REAL_CANARY": "PASS",
        "PERSISTENT_SCHEDULER": "ON_CONTROLLED",
        "AUTO_MERGE": "FORBIDDEN",
    }
    for key, value in expected_active_state.items():
        assert state[key] == value
    assert state["WAVE_3"] == "PASS"
    assert state["WAVE_4_REAL_CANARY"] == "PASS"
    assert state["active_context_pr"] is None

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
    assert state["current_workstream"] == ACTIVE_NEXT_ACTION

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
