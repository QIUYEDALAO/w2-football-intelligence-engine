from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CHECKLIST_PATH = (
    "docs/operations/architecture_convergence/"
    "W2_ARCHITECTURE_CONVERGENCE_MASTER_CHECKLIST.md"
)
AUDIT_PATH = "docs/operations/W2_INDEPENDENT_FINAL_AUDIT_20260731.md"
CONTEXT_PATH = "AI_PROJECT_CONTEXT.md"

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


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_project_state_v4_is_compact_current_authority() -> None:
    state = yaml.safe_load(read("PROJECT_STATE.yaml"))

    assert state["schema_version"] == "w2.project_state.v4"
    assert state["current_state_authority"] == "PROJECT_STATE.yaml"
    assert state["task_authority"] == CHECKLIST_PATH
    assert state["handoff_authority"] == CONTEXT_PATH
    assert state["independent_audit_authority"] == AUDIT_PATH
    assert state["current_task"] == "EVAL-02B"
    assert state["current_status"] == "BLOCKED"
    assert state["current_pr"] is None
    assert state["next_task"] == "EVAL-02B"
    assert state["next_required_action"] == (
        "RUNTIME_SAFETY_AND_CONCURRENCY_REMEDIATION"
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
    assert eval_02b["contract_authority"] == "FROZEN"
    assert eval_02b["write_side_execution_tranche"] == "COMPLETED"
    for number in ("01", "02", "03", "04"):
        assert eval_02b[f"write_side_implementation_{number}"] == "DONE"
    assert eval_02b["write_side_ready"] is True
    assert eval_02b["end_to_end_status"] == "NOT_VALIDATED"
    assert eval_02b["independent_rehearsal_receipt_review"] == "COMPLETE"
    assert eval_02b["a148_supervised_rehearsal"] == "SAFE_FAIL_CLOSED_ONLY"
    assert eval_02b["rehearsal_command_executed"] is False
    assert eval_02b["actual_provider_calls"] == 0
    assert tuple(eval_02b["critical_blockers"]) == CRITICAL_BLOCKERS
    assert eval_02b["runtime_safety_remediation"] == "REQUIRED"
    assert eval_02b["identity_provenance_gap_decision"] == (
        "LEGACY_35_RESULTS_EXCLUDED_FROM_EVAL_02B"
    )
    assert eval_02b["legacy_result_facts_retained"] is True
    assert eval_02b["legacy_result_facts_mutated"] is False
    assert eval_02b["legacy_result_eval_eligibility"] is False
    assert eval_02b["future_only_pair_collection_required"] is True
    assert eval_02b["scoring_implementation"] == "BLOCKED"
    assert eval_02b["next_required_action"] == (
        "RUNTIME_SAFETY_AND_CONCURRENCY_REMEDIATION"
    )
    for key in (
        "provider_calls_authorized",
        "runtime_collection_authorized",
        "scheduler_start_authorized",
        "persistent_scheduler_authorized",
        "continuous_collection_authorized",
        "recommendation_enabled",
        "candidate_enabled",
        "formal_recommendation_enabled",
        "lock_enabled",
        "production_release",
    ):
        assert eval_02b[key] is False

    assert state["tasks"]["EVAL-03"]["status"] == "NOT_STARTED"
    assert state["architecture_convergence"]["status"] == "PASS"


def test_canary_contract_rejects_any_zero_required_delta() -> None:
    state = yaml.safe_load(read("PROJECT_STATE.yaml"))
    canary = state["canary_acceptance"]

    assert canary["status"] == "NOT_AUTHORIZED"
    assert canary["decision_rule"] == (
        "ALL_REQUIRED_DELTAS_POSITIVE_AND_FULL_LINEAGE_RECONCILED"
    )
    assert tuple(canary["required_deltas"]) == REQUIRED_CANARY_DELTAS
    assert all(canary["required_deltas"][key] == ">0" for key in REQUIRED_CANARY_DELTAS)
    assert canary["zero_required_delta_result"] == "FAILED"
    assert canary["lineage_mismatch_result"] == "FAILED"
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
    } <= required_lineage


def test_ai_handoff_and_next_action_are_answer_first_and_safe() -> None:
    context = read(CONTEXT_PATH)
    next_action = read("NEXT_ACTION.md")
    ledger = read("PROJECT_LEDGER.md")
    audit = read(AUDIT_PATH)
    agents = read("AGENTS.md")
    copilot = read(".github/copilot-instructions.md")

    for heading in (
        "### Completed",
        "### Current state",
        "### Core engineering rules",
        "### Real canary hard contract",
        "## Critical remediation backlog",
        "## Next action",
    ):
        assert heading in context

    for link in (
        "[AI_PROJECT_CONTEXT.md](AI_PROJECT_CONTEXT.md)",
        "[PROJECT_STATE.yaml](PROJECT_STATE.yaml)",
        AUDIT_PATH,
        CHECKLIST_PATH,
    ):
        assert link in next_action

    assert "SAFE_FAIL_CLOSED_ONLY" in context
    assert "SAFE_FAIL_CLOSED_ONLY" in next_action
    assert "RUNTIME_SAFETY_AND_CONCURRENCY_REMEDIATION" in next_action
    assert "Any required zero delta" in context
    assert "CANARY_FAILED" in next_action
    assert "real canary" in next_action.lower()
    assert "not authorized" in next_action.lower()

    assert "human decisions only" in ledger
    assert "AI_PROJECT_CONTEXT.md" in ledger
    assert "missing or unknown safety inputs deny execution" in ledger
    assert "Any required zero delta" in ledger
    assert not re.search(r"\b[0-9a-f]{40}\b|CI:\s*\d+", ledger)
    assert not re.search(r"\b[0-9a-f]{40}\b|CI:\s*\d+", next_action)

    for item in range(1, 12):
        assert f"### C{item}." in audit
    assert "Valid split-line averaging is intentional" in audit
    assert "`readiness.py` is not a live-call path" in audit
    assert "actual_provider_calls_delta      > 0" in audit
    assert "exact_pair_delta                 > 0" in audit
    assert "AI_PROJECT_CONTEXT.md" in agents
    assert "A real canary fails if any required delta is zero" in agents
    assert "Read `/AI_PROJECT_CONTEXT.md`" in copilot
    assert "Required zero evidence is failure" in copilot


def test_master_checklist_remains_task_and_frozen_contract_authority() -> None:
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
    assert (
        "SAME_PROVIDER_X_BOOKMAKER_X_MARKET_X_SELECTION_X_EXACT_LINE"
        in checklist
    )
    assert "LEGACY_35_RESULTS_EXCLUDED_FROM_EVAL_02B" in checklist
    assert "WRITE_SIDE_IMPLEMENTATION_04 = DONE" in checklist
    assert "EVAL_03 = NOT_STARTED" in checklist
