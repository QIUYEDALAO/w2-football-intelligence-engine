from __future__ import annotations

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
GOVERNANCE_AUTHORITY = (
    "https://github.com/QIUYEDALAO/w2-football-intelligence-engine/issues/455"
)
COMPUTATION_AUTHORITY = (
    "https://github.com/QIUYEDALAO/w2-football-intelligence-engine/issues/456"
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


def test_project_state_v5_records_current_execution_and_r5_blocker() -> None:
    state = yaml.safe_load(read("PROJECT_STATE.yaml"))

    assert state["schema_version"] == "w2.project_state.v5"
    assert state["current_state_authority"] == "PROJECT_STATE.yaml"
    assert state["task_authority"] == EXECUTION_AUTHORITY
    assert state["handoff_authority"] == CONTEXT_PATH
    assert state["independent_audit_authority"] == AUDIT_PATH
    assert state["asset_uniqueness_audit_authority"] == ASSET_AUDIT_PATH
    assert state["audit_perspective_registry_authority"] == REGISTRY_PATH
    assert state["governance_incident_authority"] == GOVERNANCE_AUTHORITY
    assert state["computation_authority_issue"] == COMPUTATION_AUTHORITY

    assert state["current_task"] == "EVAL-02B-T00"
    assert state["current_status"] == (
        "BLOCKED_GOVERNANCE_RUNTIME_AND_COMPUTATION_AUTHORITY_REMEDIATION"
    )
    assert state["quarantined_pr"] == 453
    assert set(state["active_issues"]) == {454, 455, 456}
    assert state["next_required_action"] == (
        "T00_GOV_THEN_T00_SAFE_R1_R5_THEN_CANONICAL_SERIALIZATION_"
        "THEN_TRUSTED_C9_REBUILD"
    )

    assert tuple(state["risk_families"]) == RISK_FAMILIES
    assert all(
        state["risk_families"][family] == "OPEN_SCAN_REQUIRED"
        for family in RISK_FAMILIES
    )

    asset = state["asset_uniqueness"]
    assert asset["issue"] == 456
    assert asset["storage_layer"]["current_conclusion"] == (
        "NO_CURRENT_EVIDENCE_OF_DELETION_RESIDUALS"
    )
    assert asset["storage_layer"]["reproducible_inventory_required"] is True
    computation = asset["computation_layer"]
    assert computation["status"] == "OPEN_BLOCKER"
    assert computation["known_runtime_canonical_serializer_minimum_count"] == 6
    assert computation["definitive_implementation_count"] == "PENDING_T00_R5"
    assert computation["canonical_serializer_authority_count_target"] == 1
    assert computation["pair_identity_contract_incomplete"] is True
    assert computation["ensure_ascii_decision"] == "PENDING_MIGRATION_INVENTORY"
    assert computation["historical_hash_in_place_rewrite_forbidden"] is True
    assert computation["serializer_version_required"] is True

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
    assert eval_02b["current_execution_manifest_issue"] == 454
    assert eval_02b["current_governance_incident_issue"] == 455
    assert eval_02b["current_computation_authority_issue"] == 456
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


def test_canary_contract_requires_positive_lineage_and_hash_recomputation() -> None:
    state = yaml.safe_load(read("PROJECT_STATE.yaml"))
    canary = state["canary_acceptance"]

    assert canary["status"] == "NOT_AUTHORIZED"
    assert canary["decision_rule"] == (
        "ALL_REQUIRED_DELTAS_POSITIVE_FULL_LINEAGE_AND_"
        "INDEPENDENT_HASH_RECOMPUTATION"
    )
    assert tuple(canary["required_deltas"]) == REQUIRED_CANARY_DELTAS
    assert all(canary["required_deltas"][key] == ">0" for key in REQUIRED_CANARY_DELTAS)
    assert canary["zero_required_delta_result"] == "FAILED"
    assert canary["lineage_mismatch_result"] == "FAILED"
    assert canary["independent_hash_mismatch_result"] == "FAILED"
    assert canary["nan_or_infinity_result"] == "FAILED"
    assert canary["auto_retry"] is False
    assert canary["authorization_restored_disabled_required"] is True

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

    stop = state["codex_stop_line"]
    assert stop["real_provider_call_executed"] is False
    assert stop["real_canary_authorization_created"] is False
    assert stop["auto_merge_executed"] is False
    assert stop["stop_after_offline_evidence_package"] is True


def test_handoff_documents_expose_r5_without_premature_serializer_decision() -> None:
    context = read(CONTEXT_PATH)
    next_action = read("NEXT_ACTION.md")
    audit = read(AUDIT_PATH)
    asset_audit = read(ASSET_AUDIT_PATH)
    registry = read(REGISTRY_PATH)
    agents = read("AGENTS.md")
    copilot = read(".github/copilot-instructions.md")

    for path in (
        CONTEXT_PATH,
        "PROJECT_STATE.yaml",
        AUDIT_PATH,
        ASSET_AUDIT_PATH,
        REGISTRY_PATH,
    ):
        assert path in next_action

    for text in (context, next_action, registry, agents, copilot):
        assert "R5" in text
        assert "#456" in text

    assert "canonical serialization" in context.lower()
    assert "canonical serialization" in next_action.lower()
    assert "PENDING CONTRACT/MIGRATION DECISION" in next_action
    assert "Do **not** choose `ensure_ascii=True` or `False`" in next_action
    assert "ensure_ascii=True" in asset_audit
    assert "ensure_ascii=False" in asset_audit
    assert "allow_nan=False" in asset_audit
    assert "97c6d410cc9167d2" in asset_audit
    assert "3c6fe4e44f3ad08f" in asset_audit
    assert "计算权威唯一性" in registry
    assert "One business fact has one computation authority" in agents
    assert "Do **not** choose `ensure_ascii=True` or `False`" in copilot

    for item in range(1, 12):
        assert f"### C{item}." in audit
    assert "Valid split-line averaging is intentional" in audit
    assert "`readiness.py` is not a live-call path" in audit
    assert "actual_provider_calls_delta      > 0" in audit
    assert "exact_pair_delta                 > 0" in audit

    state = yaml.safe_load(read("PROJECT_STATE.yaml"))
    assert state["asset_uniqueness"]["computation_layer"]["ensure_ascii_decision"] == (
        "PENDING_MIGRATION_INVENTORY"
    )


def test_master_checklist_remains_frozen_contract_history_and_exposes_gap() -> None:
    checklist = read(CHECKLIST_PATH)

    assert "`PROJECT_STATE.yaml` 是 W2 **唯一当前机器可读状态快照**" in checklist
    assert "唯一任务顺序、任务规格和已合并完成回执权威" in checklist
    assert "Status: BLOCKED" in checklist
    assert "EVAL_02B_START_AUTHORIZED = false" in checklist
    assert "PAIR_SCOPE = PER_COMPETITION_X_MARKET" in checklist
    assert "MINIMUM_ELIGIBLE_TOTAL_PAIRS = 120" in checklist
    assert "TIME_SPLIT = STRICT_CHRONOLOGICAL_70_30" in checklist
    assert "BOOTSTRAP_ITERATIONS = 10000" in checklist
    assert "PROBABILITY_SUM_TOLERANCE = 1e-9" in checklist
    assert "PRE_ELIGIBILITY_TIME_AUTHORITY = capture_at" in checklist
    assert "POST_ELIGIBILITY_TIME_AUTHORITY = capture_at" in checklist
    assert "PAIR_IDENTITY_SERIALIZATION" in checklist
    assert "UTF8_CANONICAL_JSON_SORTED_KEYS_COMPACT" in checklist
    assert "Canonical JSON 禁止 NaN/Infinity" in checklist
    assert "LEGACY_35_RESULTS_EXCLUDED_FROM_EVAL_02B" in checklist
    assert "WRITE_SIDE_IMPLEMENTATION_04 = DONE" in checklist
    assert "EVAL_03 = NOT_STARTED" in checklist

    # The current frozen text does not settle ensure_ascii/version semantics.
    # Project state and #456 therefore correctly retain a Gate-A contract blocker.
    assert "ensure_ascii" not in checklist
    state = yaml.safe_load(read("PROJECT_STATE.yaml"))
    assert state["tasks"]["EVAL-02B"]["contract_authority"] == (
        "FROZEN_BUT_PAIR_SERIALIZATION_INCOMPLETE"
    )
