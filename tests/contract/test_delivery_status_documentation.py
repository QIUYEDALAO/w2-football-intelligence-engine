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
    assert state["current_status"] == "PASS"
    assert "current_pr" in state
    assert state["current_pr_semantics"] == "CURRENT_BUSINESS_IMPLEMENTATION_PR_ONLY"
    assert state["active_context_pr"] == 450
    assert state["active_context_pr_semantics"] == "CURRENT_CONTEXT_AND_GUARD_PR"
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
        "status": "PASS",
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
        "forward_collection_activation_review": "PASS",
        "forward_collection_activation_review_status": "DONE",
        "existing_collection_pipeline": "REUSED",
        "a148_supervised_rehearsal": "BLOCKED_PRECONDITION",
        "rehearsal_status": "BLOCKED",
        "rehearsal_as_of": "2026-07-31T05:10:47.160608Z",
        "pr_448_head": "3466bd4419ff2339233fd659199a1dbf87370113",
        "pr_448_merge_sha": "c61bff2e50248db8e37b154fd233d456b18e7d0e",
        "pr_448_main_ci": 30605554667,
        "new_guard_framework": False,
        "new_activation_manifest_framework": False,
        "new_canary_cli": False,
        "provider_control_rewrite": False,
        "new_collection_pipeline": False,
        "rehearsal_competition_id": "brasileirao_serie_a",
        "rehearsal_season": "2026",
        "rehearsal_competition_audit_order": 1,
        "market_scope": ["ASIAN_HANDICAP", "TOTALS"],
        "endpoint_scope": ["status", "fixtures", "odds", "lineups"],
        "capture_cadence": "ONE_SUPERVISED_REFRESH_RUN",
        "provider_call_limit": 30,
        "daily_request_budget": 120,
        "scheduler_mode": "NOT_STARTED",
        "scheduler_restart_policy": "no",
        "scheduler_restart_policy_observed": "unless-stopped",
        "scheduler_restart_policy_validation": "FAIL",
        "scheduler_container_started": False,
        "rehearsal_execution_mode": "MANUAL_FOREGROUND_ONE_SHOT",
        "rehearsal_entrypoint": "scripts/run_prematch_refresh.py",
        "rehearsal_command_executed": False,
        "projected_provider_calls": 10,
        "actual_provider_calls": 0,
        "request_count_by_endpoint": {},
        "provider_request_ledger_delta": 0,
        "raw_payload_delta": 0,
        "endpoint_capture_delta": 0,
        "checkpoint_audit_delta": 0,
        "lineup_event_delta": 0,
        "dynamic_evaluation_v2_delta": 0,
        "five_state_snapshot_delta": 0,
        "exact_pair_delta": 0,
        "materialized_fixture_ids": [],
        "read_model_data_time_before": "2026-07-30T15:05:44.392619Z",
        "read_model_data_time_after": "2026-07-30T15:05:44.392619Z",
        "dashboard_data_time_before": "2026-07-30T15:05:44.392619Z",
        "dashboard_data_time_after": "2026-07-30T15:05:44.392619Z",
        "celery_tasks_queued": 0,
        "checkpoint_claim_delta": 0,
        "flags_restored_disabled": True,
        "rehearsal_blockers": [
            "SCHEDULER_RESTART_POLICY_MISMATCH_EXPECTED_NO_OBSERVED_UNLESS_STOPPED"
        ],
        "auto_retry": False,
        "runtime_collection_authorized": False,
        "runtime_collection_authorized_scope": "NOT_APPLICABLE",
        "persistent_scheduler_authorized": False,
        "continuous_collection_authorized": False,
        "identity_remediation_design": "BLOCKED",
        "identity_remediation_execution_authorized": False,
        "identity_remediation_audit_as_of": "2026-07-30T17:31:23.303986Z",
        "identity_remediation_audit_sha256": (
            "8871fa588091b2daa8c72bd36837e044f462c194f9bc7804bcde27015d063ad0"
        ),
        "exact_unique_candidate_count": 0,
        "unresolved_result_count": 35,
        "identity_provenance_gap_decision": (
            "LEGACY_35_RESULTS_EXCLUDED_FROM_EVAL_02B"
        ),
        "legacy_result_facts_retained": True,
        "legacy_result_facts_mutated": False,
        "legacy_result_eval_eligibility": False,
        "legacy_identity_remediation_closed": True,
        "future_only_pair_collection_required": True,
        "new_provider_fetch_can_restore_legacy_provenance": False,
        "fuzzy_identity_reconstruction_allowed": False,
        "team_name_match_allowed": False,
        "approximate_time_match_allowed": False,
        "manual_competition_season_guess_allowed": False,
        "legacy_remediation_reopen_condition": "EXACT_ORIGINAL_RAW_BLOB_RECOVERED",
        "required_blob_verification": (
            "SHA256(blob) == result.source_payload_sha256"
        ),
        "reopen_scope": "IDENTITY_REMEDIATION_ONLY",
        "write_side_implementation_authorized": False,
        "write_side_execution_tranche": "COMPLETED",
        "write_side_implementation_01": "DONE",
        "write_side_implementation_01_pr": 441,
        "write_side_implementation_01_merge_sha": (
            "5c52a40a6f0b3afb8589c251bea0b7ba611012f5"
        ),
        "write_side_implementation_01_main_ci": 30583359805,
        "write_side_implementation_02": "DONE",
        "write_side_implementation_02_pr": 443,
        "write_side_implementation_02_head": (
            "8eaf04699414a1ebe65077e419651f567910c45d"
        ),
        "write_side_implementation_02_merge_sha": (
            "532e58c44fe388d7053d8c0b3c3b7d5fa934cacb"
        ),
        "write_side_implementation_02_main_ci": 30598884065,
        "write_side_implementation_03": "DONE",
        "write_side_implementation_03_pr": 444,
        "write_side_implementation_03_head": (
            "b959e4a3a406fcc9898695643a17fac9c069281f"
        ),
        "write_side_implementation_03_merge_sha": (
            "882f69650d4773757529999e3f8292e8689231a2"
        ),
        "write_side_implementation_03_main_ci": 30599432182,
        "write_side_implementation_04": "DONE",
        "write_side_implementation_04_pr": 445,
        "write_side_implementation_04_head": (
            "05b55b5e1fc6583abbdee705a6b39bd263da4372"
        ),
        "write_side_implementation_04_merge_sha": (
            "308e1edc9ed1748a18cd64c9325521e54a5777ba"
        ),
        "write_side_implementation_04_main_ci": 30599981432,
        "provider_calls_authorized": False,
        "provider_calls_authorized_scope": "NOT_APPLICABLE",
        "scheduler_start_authorized": False,
        "scheduler_start_authorized_scope": "NOT_APPLICABLE",
        "write_side_readiness_design": "FROZEN",
        "write_side_ready": True,
        "new_table_count": 0,
        "new_migration_count": 0,
        "lineup_event_production_caller": "IMPLEMENTED",
        "canonical_lineup_event_atomic_write": "IMPLEMENTED",
        "post_lineup_refresh_plan_production_caller": "IMPLEMENTED",
        "dynamic_evaluation_v2": "IMPLEMENTED",
        "five_state_snapshot": "IMPLEMENTED",
        "exact_pair_projector": "IMPLEMENTED",
        "pair_evidence_authority": "IMMUTABLE_ORIGINAL_EVALUATION",
        "lifecycle_supersession_effect": "DIAGNOSTIC_ONLY",
        "pre_post_eligibility_requires_not_superseded": False,
        "recommendation_enabled": False,
        "candidate_enabled": False,
        "formal_recommendation_enabled": False,
        "lock_enabled": False,
        "production_release": False,
        "scoring_implementation": "BLOCKED",
        "real_canary_provider_calls": 5,
        "real_canary_evidence_sha256": (
            "30e961cbedee33b5ec74bf3eabbd80a202ced3b9b21483160896812442ddd1f4"
        ),
        "real_chain": "PROVEN",
        "next_required_action": "VPS_DEPLOYMENT_AND_POSTDEPLOY_CLOSURE",
    }
    assert state["tasks"]["EVAL-03"]["status"] == "NOT_STARTED"
    assert state["architecture_convergence"]["status"] == "PASS"
    assert "[PROJECT_STATE.yaml](PROJECT_STATE.yaml)" in next_action
    assert CHECKLIST_PATH in next_action
    assert "ACTIVE_NEXT_ACTION = VPS_DEPLOYMENT_AND_POSTDEPLOY_CLOSURE" in next_action
    assert "NEXT_CODE_ACTION = NONE_AUTHORIZED" in next_action
    assert "T00_RERUN = FORBIDDEN_UNLESS_NEW_APPROVED_EVIDENCE" in next_action
    assert "Historical receipt / 历史回执" in next_action
    a148 = state["historical_receipts"]["a148"]
    assert a148["previous_next_required_action"] == (
        "INDEPENDENT_REHEARSAL_RECEIPT_REVIEW"
    )
    assert a148["fail_closed_barrier"] == "PASS"
    assert a148["provider_execution"] == "NOT_EXECUTED"
    assert a148["actual_provider_calls"] == 0
    assert a148["business_db_writes"] == 0
    assert a148["scheduler_started"] is False
    assert a148["celery_tasks_queued"] == 0
    assert a148["one_shot_authorization_revoked"] is True
    assert a148["end_to_end_chain"] == "NOT_VALIDATED"
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
    assert (
        "START_QUALIFICATION_AUDIT_AS_OF = 2026-07-30T16:06:59.736350Z"
        in b5
    )
    assert (
        "START_QUALIFICATION_AUDIT_SHA256 = "
        "c4099f973f46514c3105911eee9bf87accd20f98b2430998868716d8ae13e70d"
        in b5
    )
    assert "AUDIT_AS_OF = 2026-07-30T17:31:23.303986Z" in b5
    assert (
        "AUDIT_SHA256 = "
        "8871fa588091b2daa8c72bd36837e044f462c194f9bc7804bcde27015d063ad0"
        in b5
    )
    assert "EXACT_UNIQUE_CANDIDATE_COUNT = 0" in b5
    assert "UNRESOLVED_RESULT_COUNT = 35" in b5
    assert "dynamic_prematch_evaluations 0" in b5
    assert "lineup_confirmed_events 0" in b5
    assert "exact pre/post pairs 0" in b5
    assert "35 results 缺唯一 canonical competition/season identity" in b5
    for frozen_coordinate in (
        "CONTRACT_AUTHORITY = FROZEN",
        "DATA_ACQUISITION_PLAN = AUTHORIZED",
        "FORWARD_COLLECTION_ACTIVATION_REVIEW = PASS",
        "FORWARD_COLLECTION_ACTIVATION_REVIEW_STATUS = DONE",
        "EXISTING_COLLECTION_PIPELINE = REUSED",
        "A148_SUPERVISED_REHEARSAL = BLOCKED_PRECONDITION",
        "NEW_GUARD_FRAMEWORK = false",
        "NEW_ACTIVATION_MANIFEST_FRAMEWORK = false",
        "NEW_CANARY_CLI = false",
        "PROVIDER_CONTROL_REWRITE = false",
        "NEW_COLLECTION_PIPELINE = false",
        "REHEARSAL_COMPETITION_ID = brasileirao_serie_a",
        "REHEARSAL_SEASON = 2026",
        "MARKET_SCOPE =",
        "ASIAN_HANDICAP",
        "TOTALS",
        "ENDPOINT_SCOPE =",
        "status",
        "fixtures",
        "odds",
        "lineups",
        "CAPTURE_CADENCE =",
        "ONE_SUPERVISED_REFRESH_RUN",
        "PROVIDER_CALL_LIMIT = 30",
        "DAILY_REQUEST_BUDGET = 120",
        "SCHEDULER_MODE =",
        "NOT_STARTED",
        "REHEARSAL_EXECUTION_MODE =",
        "MANUAL_FOREGROUND_ONE_SHOT",
        "REHEARSAL_ENTRYPOINT =",
        "scripts/run_prematch_refresh.py",
        "SCHEDULER_RESTART_POLICY = no",
        "SCHEDULER_CONTAINER_STARTED = false",
        "AUTO_RETRY = false",
        "RUNTIME_COLLECTION_AUTHORIZED = false",
        "RUNTIME_COLLECTION_AUTHORIZED_SCOPE =",
        "NOT_APPLICABLE",
        "PERSISTENT_SCHEDULER_AUTHORIZED = false",
        "CONTINUOUS_COLLECTION_AUTHORIZED = false",
        "IDENTITY_REMEDIATION_DESIGN = BLOCKED",
        "IDENTITY_REMEDIATION_EXECUTION_AUTHORIZED = false",
        "IDENTITY_PROVENANCE_GAP_DECISION =",
        "LEGACY_35_RESULTS_EXCLUDED_FROM_EVAL_02B",
        "LEGACY_RESULT_FACTS_RETAINED = true",
        "LEGACY_RESULT_FACTS_MUTATED = false",
        "LEGACY_RESULT_EVAL_ELIGIBILITY = false",
        "LEGACY_IDENTITY_REMEDIATION_CLOSED = true",
        "FUTURE_ONLY_PAIR_COLLECTION_REQUIRED = true",
        "WRITE_SIDE_IMPLEMENTATION_01 = DONE",
        "WRITE_SIDE_IMPLEMENTATION_01_PR = 441",
        "WRITE_SIDE_IMPLEMENTATION_01_MERGE_SHA =",
        "5c52a40a6f0b3afb8589c251bea0b7ba611012f5",
        "WRITE_SIDE_IMPLEMENTATION_01_MAIN_CI = 30583359805",
        "WRITE_SIDE_IMPLEMENTATION_AUTHORIZED = false",
        "WRITE_SIDE_EXECUTION_TRANCHE = COMPLETED",
        "WRITE_SIDE_IMPLEMENTATION_02 = DONE",
        "WRITE_SIDE_IMPLEMENTATION_02_PR = 443",
        "WRITE_SIDE_IMPLEMENTATION_02_HEAD =",
        "8eaf04699414a1ebe65077e419651f567910c45d",
        "WRITE_SIDE_IMPLEMENTATION_02_MERGE_SHA =",
        "532e58c44fe388d7053d8c0b3c3b7d5fa934cacb",
        "WRITE_SIDE_IMPLEMENTATION_02_MAIN_CI = 30598884065",
        "WRITE_SIDE_IMPLEMENTATION_03 = DONE",
        "WRITE_SIDE_IMPLEMENTATION_03_PR = 444",
        "WRITE_SIDE_IMPLEMENTATION_03_HEAD =",
        "b959e4a3a406fcc9898695643a17fac9c069281f",
        "WRITE_SIDE_IMPLEMENTATION_03_MERGE_SHA =",
        "882f69650d4773757529999e3f8292e8689231a2",
        "WRITE_SIDE_IMPLEMENTATION_03_MAIN_CI = 30599432182",
        "WRITE_SIDE_IMPLEMENTATION_04 = DONE",
        "WRITE_SIDE_IMPLEMENTATION_04_PR = 445",
        "WRITE_SIDE_IMPLEMENTATION_04_HEAD =",
        "05b55b5e1fc6583abbdee705a6b39bd263da4372",
        "WRITE_SIDE_IMPLEMENTATION_04_MERGE_SHA =",
        "308e1edc9ed1748a18cd64c9325521e54a5777ba",
        "WRITE_SIDE_IMPLEMENTATION_04_MAIN_CI = 30599981432",
        "PROVIDER_CALLS_AUTHORIZED = false",
        "PROVIDER_CALLS_AUTHORIZED_SCOPE =",
        "SCHEDULER_START_AUTHORIZED = false",
        "SCHEDULER_START_AUTHORIZED_SCOPE =",
        "NOT_APPLICABLE",
        "WRITE_SIDE_READINESS_DESIGN = FROZEN",
        "WRITE_SIDE_READY = true",
        "LINEUP_EVENT_PRODUCTION_CALLER = IMPLEMENTED",
        "CANONICAL_LINEUP_EVENT_ATOMIC_WRITE = IMPLEMENTED",
        "POST_LINEUP_REFRESH_PLAN_PRODUCTION_CALLER = IMPLEMENTED",
        "DYNAMIC_EVALUATION_V2 = IMPLEMENTED",
        "FIVE_STATE_SNAPSHOT = IMPLEMENTED",
        "EXACT_PAIR_PROJECTOR = IMPLEMENTED",
        "PAIR_EVIDENCE_AUTHORITY =",
        "IMMUTABLE_ORIGINAL_EVALUATION",
        "LIFECYCLE_SUPERSESSION_EFFECT =",
        "DIAGNOSTIC_ONLY",
        "PRE_POST_ELIGIBILITY_REQUIRES_NOT_SUPERSEDED = false",
        "RECOMMENDATION_ENABLED = false",
        "CANDIDATE_ENABLED = false",
        "FORMAL_RECOMMENDATION_ENABLED = false",
        "LOCK_ENABLED = false",
        "PRODUCTION_RELEASE = false",
        "SCORING_IMPLEMENTATION = BLOCKED",
        "NEXT_REQUIRED_ACTION =",
        "INDEPENDENT_REHEARSAL_RECEIPT_REVIEW",
        "NEW_PROVIDER_FETCH_CAN_RESTORE_LEGACY_PROVENANCE = false",
        "FUZZY_IDENTITY_RECONSTRUCTION_ALLOWED = false",
        "TEAM_NAME_MATCH_ALLOWED = false",
        "APPROXIMATE_TIME_MATCH_ALLOWED = false",
        "MANUAL_COMPETITION_SEASON_GUESS_ALLOWED = false",
        "LEGACY_REMEDIATION_REOPEN_CONDITION =",
        "EXACT_ORIGINAL_RAW_BLOB_RECOVERED",
        "REQUIRED_BLOB_VERIFICATION =",
        "SHA256(blob) == result.source_payload_sha256",
        "REOPEN_SCOPE =",
        "IDENTITY_REMEDIATION_ONLY",
        "EVAL_02B = BLOCKED",
        "EVAL_03 = NOT_STARTED",
        "PAIR_SCOPE = PER_COMPETITION_X_MARKET",
        "PAIR_GRAIN = ONE_CANONICAL_FIXTURE_PAIR",
        "MINIMUM_ELIGIBLE_TOTAL_PAIRS = 120",
        "TIME_SPLIT = STRICT_CHRONOLOGICAL_70_30",
        "MINIMUM_VALIDATION_PAIRS = 36",
        "BOOTSTRAP_ITERATIONS = 10000",
        "BOOTSTRAP_UNIT = PAIRED_VALIDATION_FIXTURE",
        "MINIMUM_COMPETITIONS = NOT_APPLICABLE",
        "SETTLEMENT_STATE_ORDER =",
        "WIN, HALF_WIN, PUSH, HALF_LOSS, LOSS",
        "BASELINE_DISTRIBUTION =",
        "baseline_probability_by_settlement_state",
        "CANDIDATE_DISTRIBUTION =",
        "candidate_probability_by_settlement_state",
        "DISTRIBUTIONS_SHARE_IDENTICAL_STATE_SPACE = true",
        "DISTRIBUTION_VALUES_MAY_DIFFER = true",
        "PROBABILITY_VALUES = FINITE_AND_NON_NEGATIVE",
        "PROBABILITY_SUM_TOLERANCE = 1e-9",
        "LOG_LOSS_EPSILON = 1e-9",
        "OBSERVED_SETTLEMENT_STATE = REQUIRED",
        "MISSING_OR_INVALID_DISTRIBUTION = FAIL_CLOSED",
        "LL(distribution, observed_state) =",
        "-ln(max(distribution[observed_state], LOG_LOSS_EPSILON))",
        "paired_log_loss_improvement =",
        "LL(baseline_distribution, observed_state)",
        "LL(candidate_distribution, observed_state)",
        "GATE_PASS =",
        "log_loss_improvement_ci_low > 0",
        "SCORING_IMPLEMENTATION = BLOCKED",
        "SCORING_IMPLEMENTATION_BLOCKER =",
        (
            "COMPLETE_PERSISTED_BASELINE_AND_CANDIDATE_"
            "FIVE_STATE_DISTRIBUTIONS_UNAVAILABLE"
        ),
        "CONTRACT_VERSION = w2.eval_02b_gate.v1",
        "ORDER_BY =",
        "kickoff_at ASC, canonical_fixture_id ASC",
        "VALIDATION_START_INDEX =",
        "floor(total_eligible_pairs * 0.70)",
        "VALIDATION_SET =",
        "ordered_pairs[VALIDATION_START_INDEX:]",
        "PAIR_IDENTITY_SERIALIZATION =",
        "UTF8_CANONICAL_JSON_SORTED_KEYS_COMPACT",
        "PAIR_IDENTITY_SERIALIZER_VERSION =",
        "w2.canonical-json.v2",
        "PAIR_IDENTITY_ENSURE_ASCII = false",
        "PAIR_IDENTITY_UNICODE = NFC",
        "PAIR_IDENTITY_ALLOW_NAN = false",
        "PAIR_IDENTITY_TYPE_RULES =",
        "PAIR_IDENTITY_HASH =",
        "SHA256(PAIR_IDENTITY_SERIALIZATION)",
        "BOOTSTRAP_SEED_PAYLOAD =",
        "canonical_json({",
        "contract_version,",
        "validation_pair_identity_hashes:",
        "sorted(validation_pair_identity_hashes)",
        "BOOTSTRAP_SEED_HASH =",
        "SHA256(BOOTSTRAP_SEED_PAYLOAD)",
        "BOOTSTRAP_SEED =",
        "UNSIGNED_BIG_ENDIAN_UINT64(",
        "FIRST_8_BYTES(BOOTSTRAP_SEED_HASH)",
        "RPS_ROLE = DIAGNOSTIC_ONLY",
        "COVERAGE_ROLE = DIAGNOSTIC_ONLY",
        "REVALIDATE_AFTER_DAYS = 90",
        "REVALIDATE_AFTER_NEW_PAIRS = 60",
        "CI_CONTAINS_ZERO = FREEZE_ADJUSTMENT_TO_ZERO",
        "pre.capture_at < lineup_confirmed_at <= post.capture_at",
        "LEAGUE_SCOPE",
        "MARKET_SCOPE",
        "ENDPOINT_SCOPE",
        "CAPTURE_CADENCE",
        "DAILY_REQUEST_BUDGET",
        "ROLLBACK",
        "PROVIDER_CALL_LIMIT",
        "PAIR_QUOTE_SCOPE =",
        "SAME_PROVIDER_X_BOOKMAKER_X_MARKET_X_SELECTION_X_EXACT_LINE",
        "PRE_POST_PROVIDER_ID = SAME",
        "PRE_POST_BOOKMAKER_ID = SAME",
        "CAPTURE_ID = MAY_DIFFER",
        "QUOTE_IDENTITY_MISSING_OR_CONFLICTING = FAIL_CLOSED",
        "PAIR_IDENTITY_HASH_MINIMUM_FIELDS =",
        "canonical_fixture_id",
        "competition_id",
        "season_id",
        "provider_id",
        "bookmaker_id",
        "market",
        "selection",
        "exact_line",
        "pre_evaluation_id",
        "post_evaluation_id",
        "RESULT_AUTHORITY = results",
        "FIXTURE_IDENTITY_AUTHORITY = matchday_fixture_identities",
        "LEAGUE_MAPPING_AUTHORITY = league_profile + league_season",
        "RESULT_ROWS_MUTABLE = false",
        "IDENTITY_REMEDIATION_MODE = INSERT_MISSING_ONLY",
        "NEW_TABLE_COUNT = 0",
        "NEW_MIGRATION_COUNT = 0",
        "DIRECT_SQL_WRITE_ALLOWED = false",
        "result.fixture_id",
        "result.source_payload_sha256",
        "result.source_capture_id",
        "→ raw_payload（raw_payloads authority 的当前物理表）",
        "→ matchday_endpoint_captures（存在时）",
        "→ raw fixtures response",
        "→ league_profile / league_season",
        "→ proposed MatchdayFixtureIdentityV1",
        "provider + provider_league_id + provider_season",
        "COMPETITION_SEASON_MAPPING_MISSING",
        "COMPETITION_SEASON_MAPPING_AMBIGUOUS",
        "COMPETITION_SEASON_PROVENANCE_CONFLICT",
        "kickoff_utc",
        "home_provider_team_id",
        "away_provider_team_id",
        "home_w2_team_id",
        "away_w2_team_id",
        "team_identity_status",
        "raw_payload_sha256",
        "endpoint_capture_id",
        "captured_at",
        "identity_hash",
        "RESULT_COUNT = 35",
        "SOURCE_CAPTURE_ID_PRESENT = 0",
        "RAW_PAYLOAD_EXACT = 0",
        "RAW_FIXTURE_EXACT = 0",
        "CAPTURE_EXACT = 0",
        "REGISTRY_EXACT = 0",
        "WOULD_INSERT = 0",
        "ALREADY_EXACT = 0",
        "BLOCKED_MISSING = 35",
        "BLOCKED_AMBIGUOUS = 0",
        "BLOCKED_CONFLICT = 0",
        "RAW_PAYLOAD_NOT_FOUND = 35",
        "RAW_FIXTURE_PROVENANCE_MISSING = 35",
        "COMPETITION_SEASON_MAPPING_MISSING = 35",
        "DB_WRITE_DELTA = 0",
        "PROVIDER_CALL_DELTA = 0",
        "canonical remediation manifest",
        "MatchdayRuntimeRepository.upsert_fixture_identities_with_business_changes()",
        "manifest_hash",
        "preexisting",
        "inserted_at",
    ):
        assert frozen_coordinate in b5
    for identity_rule in (
        "同一 canonical fixture、competition、season、market、selection",
        "首发确认前最后一个合格持久化评估",
        "首发确认后第一个使用 fresh",
        "每场 fixture",
        "只允许一个 pair",
        "跨赛季、跨联赛、marker-only 和原始状态不合格的数据",
        "lifecycle supersession relation 仅作诊断",
        "不影响原始合格 evidence",
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
    assert (
        "fixture_id\n"
        "provider\n"
        "provider_fixture_id\n"
        "competition_id\n"
        "provider_league_id\n"
        "season\n"
        "kickoff_utc\n"
        "fixture_status\n"
        "home_provider_team_id\n"
        "away_provider_team_id\n"
        "home_w2_team_id\n"
        "away_w2_team_id\n"
        "team_identity_status\n"
        "raw_payload_sha256\n"
        "endpoint_capture_id\n"
        "captured_at\n"
        "payload\n"
        "identity_hash"
    ) in b5
    assert (
        "WOULD_INSERT\n"
        "ALREADY_EXACT\n"
        "BLOCKED_MISSING\n"
        "BLOCKED_AMBIGUOUS\n"
        "BLOCKED_CONFLICT"
    ) in b5
    for remediation_rule in (
        "`results` 不得修改、删除、重建或增加 competition/season 字段",
        "不得新建平行 identity",
        "不得以名称、球队或时间作模糊匹配",
        "fixture status、fulltime 比分必须与 Result 一致",
        "禁止 team name、league name 或近似时间匹配",
        "W2 team IDs 仅可取 reviewed exact",
        "identity_hash` 必须复用 repository 既有 semantic hash",
        "写入前必须重新核验 DB snapshot 与 manifest hash",
        "`ALREADY_EXACT` 必须零写",
        "稳定字段不同必须整批 fail-closed",
        "第二次执行必须",
        "零写且 manifest hash 一致",
        "回滚只可删除 `preexisting = false`",
        "身份已变化或已被下游消费时",
        "自动回滚必须",
        "fail-closed",
        "35 条 `results` 继续保留为不可变历史比分事实",
        "不删除、不修改，也不补造",
        "它们不参与 EVAL-02B 的 sample count、time split、bootstrap、",
        "评分或门禁",
        "`MINIMUM_ELIGIBLE_TOTAL_PAIRS = 120` 必须完全由未来合法数据满足",
        "不得重新调用 Provider 下载同一比赛后替换原 source hash",
        "不得用新 payload 冒充旧",
        "不得根据球队名、联赛名、比分、日期或近似开球时间补建身份",
        "不得修改 Result",
        "的 source hash 或 capture ID",
        "不得通过 direct SQL 将旧结果强行接入 EVAL-02B",
        "原始 blob 还必须来自 fixtures endpoint",
        "provider fixture、比分和状态精确一致",
        "provenance chain 无歧义",
        "满足时只重新打开身份修复子任务",
        "`WRITE_SIDE_READINESS_DESIGN` 仅审查和设计未来",
        "baseline/candidate",
        "Pre/Post exact pairing identity",
        "本 PR 不授权代码实施",
    ):
        assert remediation_rule in b5
    for write_side_coordinate in (
        "DYNAMIC_EVALUATION_TABLE = EXISTS",
        "DYNAMIC_EVALUATION_APPEND_API = EXISTS",
        "DYNAMIC_EVALUATION_TRANSACTIONAL_PROJECTION = EXISTS",
        "LINEUP_CONFIRMED_EVENT_TABLE = EXISTS",
        "LINEUP_CONFIRMED_EVENT_APPEND_API = EXISTS",
        "LINEUP_CONFIRMED_EVENT_PRODUCTION_CALLER = MISSING",
        "LINEUP_CHANGED_PROJECTION_EVENT = EXISTS",
        "POST_LINEUP_REFRESH_PLAN_FACTORY = EXISTS",
        "POST_LINEUP_REFRESH_PLAN_PRODUCTION_CALLER = MISSING",
        "MODEL_FIVE_STATE_DISTRIBUTION_SOURCE = EXISTS",
        "MODEL_FIVE_STATE_DISTRIBUTION_PERSISTED_IN_DYNAMIC_EVALUATION = MISSING",
        "EXPLICIT_PROVIDER_IN_DYNAMIC_EVALUATION = MISSING",
        "CANONICAL_LINEUP_HASH_SHARED_BY_EVENT_AND_EVALUATION = MISSING",
        "EXACT_PRE_POST_PAIR_PROJECTOR = MISSING",
        "NEW_PARALLEL_WRITE_PIPELINE = false",
        "NEW_TABLE_COUNT = 0",
        "NEW_MIGRATION_COUNT = 0",
        "DYNAMIC_WRITE_BOUNDARY =",
        "write_frozen_analysis_artifacts",
        "LINEUP_EVENT_AND_DYNAMIC_EVALUATION_UNIT_OF_WORK =",
        "SAME_DATABASE_TRANSACTION",
        "READ_MODEL_CHECKPOINT_AND_DYNAMIC_EVALUATION_UNIT_OF_WORK =",
        "LINEUP_INPUT_HASH_AUTHORITY =",
        "confirmed_lineup_business_identity",
        "LINEUP_EVENT_LINEUP_INPUT_HASH =",
        "POST_EVALUATION_LINEUP_INPUT_HASH =",
        "CANONICAL_LINEUP_IDENTITY_FIELDS =",
        "home_team_external_id",
        "home_sorted_starter_ids",
        "away_team_external_id",
        "away_sorted_starter_ids",
        "LINEUP_INPUT_HASH_EXCLUDED_FIELDS =",
        "captured_at",
        "raw_sha256",
        "baseline_artifact_hashes",
        "lineup_change_features",
        "model_version",
        "release_sha",
        "AUTHORITATIVE_LINEUP_EVENT_POLICY =",
        "FIRST_COMPLETE_CONFIRMED_LINEUP_IDENTITY",
        "AUTHORITATIVE_EVENT_TIME =",
        "EARLIEST_COMPLETE_CONFIRMED_CAPTURE_AT",
        "ELIGIBLE_LINEUP_EVENT_COUNT_PER_FIXTURE = 1",
        "SAME_FIXTURE_SAME_LINEUP_HASH_SAME_CAPTURE =",
        "ZERO_WRITE_EXACT_REPLAY",
        "SAME_FIXTURE_SAME_LINEUP_HASH_DIFFERENT_CAPTURE =",
        "ZERO_WRITE_REOBSERVATION",
        "REOBSERVATION_PRESERVES_ORIGINAL_EVENT_TIME = true",
        "REOBSERVATION_PRESERVES_ORIGINAL_EVENT_PAYLOAD = true",
        "SAME_FIXTURE_DIFFERENT_LINEUP_HASH =",
        "LINEUP_CONFIRMATION_CONFLICT",
        "LINEUP_CONFIRMATION_CONFLICT_EVAL_02B_ELIGIBLE = false",
        "SECOND_ELIGIBLE_LINEUP_EVENT_ALLOWED = false",
        "DYNAMIC_EVALUATION_SCHEMA_VERSION =",
        "w2.dynamic_quote_evaluation.v2",
        "DYNAMIC_EVALUATION_V1_EVAL_02B_ELIGIBLE = false",
        "DYNAMIC_EVALUATION_V2_SCHEMA_ELIGIBILITY =",
        "NECESSARY_NOT_SUFFICIENT",
        "EVAL_02B_EVALUATION_ROLES =",
        "PRE_CONFIRMATION / POST_CONFIRMATION",
        "PRE_CONFIRMATION_ELIGIBILITY =",
        "POST_CONFIRMATION_ELIGIBILITY =",
        "schema_version == w2.dynamic_quote_evaluation.v2",
        "capture_at < authoritative_lineup_event.captured_at",
        "capture_at >= authoritative_lineup_event.captured_at",
        "lineup_input_hash == null",
        "lineup_input_hash == authoritative_lineup_event.lineup_input_hash",
        "post_lineup_quote == true",
        "quote_fresh == true",
        "exact_quote_identity_complete == true",
        "model_settlement_distribution_valid == true",
        "state_not_marker_or_not_ready == true",
        "original_state in ANALYSIS_PICK_ACTIVE | NO_EDGE_CURRENT",
        "PRE_LINEUP_INPUT_HASH_REQUIRED = false",
        "POST_LINEUP_INPUT_HASH_REQUIRED = true",
        "DYNAMIC_EVALUATION_V2_FIELDS =",
        "competition_id",
        "provider",
        "quote_identity_hash",
        "model_input_hash",
        "lineup_input_hash",
        "model_settlement_distribution",
        "MODEL_SETTLEMENT_DISTRIBUTION_STATE_ORDER =",
        "BASELINE_DISTRIBUTION = PRE.model_settlement_distribution",
        "CANDIDATE_DISTRIBUTION = POST.model_settlement_distribution",
        "STATE_SET_EXACT = true",
        "FINITE_AND_NON_NEGATIVE = true",
        "ABS(SUM - 1) <= 1e-9",
        "MISSING_OR_INVALID = FAIL_CLOSED",
        "LINEUP_EVENT_V2_FIELDS =",
        "home_lineup_identity_hash",
        "away_lineup_identity_hash",
        "source_capture_id",
        "SAME_NATURAL_IDENTITY_AND_SAME_PAYLOAD = ZERO_WRITE",
        "SAME_NATURAL_IDENTITY_AND_DIFFERENT_PAYLOAD = FAIL_CLOSED",
        "checkpoint = LINEUP_CONFIRMED",
        "endpoint = odds",
        "scheduled_at = lineup_event.captured_at",
        "fixture_id = lineup_event.fixture_id",
        "LINEUP_EVENT_WITHOUT_POST_LINEUP_ODDS_PLAN =",
        "WRITE_SIDE_NOT_READY",
        "PLAN_EXISTS_BUT_PROVIDER_NOT_ACTIVATED =",
        "READY_FOR_ACTIVATION_REVIEW",
        "PAIR_PROJECTOR_REQUIRES =",
        "EXACTLY_ONE_AUTHORITATIVE_ELIGIBLE_LINEUP_EVENT",
        "ZERO_AUTHORITATIVE_EVENTS =",
        "BLOCKED_LINEUP_EVENT_MISSING",
        "MULTIPLE_OR_CONFLICTING_EVENTS =",
        "BLOCKED_LINEUP_EVENT_CONFLICT",
        "last eligible PRE_CONFIRMATION evaluation",
        "before authoritative event",
        "first eligible POST_CONFIRMATION evaluation",
        "after authoritative event",
        "PRE_POST_EXACT_MATCH_FIELDS =",
        "PAIR_STORAGE_MODE = DERIVED_READ_MODEL",
        "NEW_PAIR_TABLE_COUNT = 0",
        "WRITE_SIDE_IMPLEMENTATION_01 =",
        "CANONICAL_LINEUP_EVENT_AND_ATOMIC_WRITE",
        "WRITE_SIDE_IMPLEMENTATION_02 =",
        "DYNAMIC_EVALUATION_V2_AND_FIVE_STATE_SNAPSHOT",
        "WRITE_SIDE_IMPLEMENTATION_03 =",
        "POST_LINEUP_ODDS_PLAN_PRODUCER",
        "WRITE_SIDE_IMPLEMENTATION_04 =",
        "READ_ONLY_EXACT_PAIR_PROJECTOR",
        "WRITE_SIDE_IMPLEMENTATION_ORDER =",
        "01 -> 02 -> 03 -> 04",
        "WRITE_SIDE_READINESS_DESIGN = FROZEN",
        "WRITE_SIDE_READY = true",
        "WRITE_SIDE_IMPLEMENTATION_AUTHORIZED = false",
        "WRITE_SIDE_EXECUTION_TRANCHE = COMPLETED",
        "WRITE_SIDE_IMPLEMENTATION_02 = DONE",
        "WRITE_SIDE_IMPLEMENTATION_03 = DONE",
        "WRITE_SIDE_IMPLEMENTATION_04 = DONE",
        "DYNAMIC_EVALUATION_V2 = IMPLEMENTED",
        "FIVE_STATE_SNAPSHOT = IMPLEMENTED",
        "POST_LINEUP_REFRESH_PLAN_PRODUCTION_CALLER = IMPLEMENTED",
        "EXACT_PAIR_PROJECTOR = IMPLEMENTED",
        "PAIR_EVIDENCE_AUTHORITY =",
        "IMMUTABLE_ORIGINAL_EVALUATION",
        "LIFECYCLE_SUPERSESSION_EFFECT =",
        "DIAGNOSTIC_ONLY",
        "PRE_POST_ELIGIBILITY_REQUIRES_NOT_SUPERSEDED = false",
        "NEXT_REQUIRED_ACTION =",
        "INDEPENDENT_REHEARSAL_RECEIPT_REVIEW",
    ):
        assert write_side_coordinate in b5
    assert "pre.capture_at < lineup_confirmed_at <= post.capture_at" in b5
    assert "PRE_ELIGIBILITY_TIME_AUTHORITY = capture_at" in b5
    assert "POST_ELIGIBILITY_TIME_AUTHORITY = capture_at" in b5
    assert "PRE_EVALUATED_AT_ROLE =" in b5
    assert "POST_EVALUATED_AT_ROLE =" in b5
    assert "DETERMINISTIC_TIE_BREAKER_ONLY" in b5
    assert "pre.evaluated_at < lineup_confirmed_at" not in b5
    assert (
        "PRE_ORDER =\n"
        "capture_at DESC\n"
        "evaluated_at DESC\n"
        "evaluation_id DESC"
    ) in b5
    assert (
        "POST_ORDER =\n"
        "capture_at ASC\n"
        "evaluated_at ASC\n"
        "evaluation_id ASC"
    ) in b5
    for write_side_rule in (
        "唯一方案是复用当前 production projection graph",
        "不新建平行写侧",
        "`append_lineup_event_in_session()`",
        "canonical lineup event、dynamic",
        "evaluation、supersession、shadow read-model checkpoint",
        "任一步冲突必须整批 rollback",
        "API/read path 不得写数据库",
        "future refresh 不得另建独立 evaluation writer",
        "不得新增",
        "第二个 event/outbox 表",
        "不得使用 direct SQL",
        "排除字段属于 provenance 或 `model_input_hash`",
        "主客各 11 名首发、22 个",
        "球员 ID 唯一",
        "两队 snapshot 属于同一 capture",
        "capture 在开球前",
        "任一条件不满足均不写 event",
        "同一套 XI 后续再次被观测时，不创建新 event、不修改最早确认时间",
        "也不视为冲突",
        "Reobservation 不作为新的 authoritative payload",
        "首次确认后出现不同",
        "`lineup_input_hash`，该 fixture 整体不得产生 EVAL-02B pair",
        "v2 schema 本身只提供必要条件，不能自动赋予 EVAL-02B 资格",
        "Pre 的",
        "`lineup_input_hash` 必须为空",
        "Post 的 hash 必须精确匹配 authoritative event",
        "NOT_READY、marker 和其他原始状态不合格的 evaluation 均不合格",
        "supersession relation 只输出诊断信息",
        "必须全部参与 v2 identity hash",
        "继续使用现有 JSON payload，不改数据库表",
        "不得在一条 evaluation 同时保存",
        "baseline 和 candidate",
        "`complete_five_state_distribution()` 的 `1e-6` 容差",
        "`1e-9`",
        "PUSH、HALF_WIN、HALF_LOSS 不得转换为二元概率",
        "未来实现必须显式比较已存 payload",
        "不得新建 scheduler 或",
        "plan 表",
        "只有恰好一个 authoritative eligible lineup event 时才允许选择 Pre/Post",
        "0 个或多个/",
        "冲突 event 必须按上述 blocker fail-closed",
        "每场 fixture 最多一个 pair",
        "不得跨 provider、bookmaker、line 或 selection 配对",
        "不新建 pair 表",
        "分别通过独立、可回滚 PR",
        "不得自动开启 Provider、",
        "scheduler 或运行采集",
        "Forward collection activation review（已完成）",
        "不得建立平行 guard、",
        "python scripts/run_prematch_refresh.py",
        "--competition-id brasileirao_serie_a",
        "--persistence db",
        "本整改 PR 阶段不得执行该命令",
        "`apps.scheduler.main.run_forever`",
        "Celery scheduler dispatch",
        "未进入首发确认窗口时",
        "不自动判失败",
        "rehearsal receipt",
        "state PR",
        "不得直接开启持续采集",
        "EVAL-02B gate 与 EVAL-03 均不得启动",
    ):
        assert write_side_rule in b5
    for activation_receipt_field in (
        "projected_provider_calls",
        "actual_provider_calls",
        "request_count_by_endpoint",
        "provider_request_ledger_delta",
        "raw_payload_delta",
        "endpoint_capture_delta",
        "checkpoint_audit_delta",
        "lineup_event_delta",
        "dynamic_evaluation_v2_delta",
        "five_state_snapshot_delta",
        "exact_pair_delta",
        "materialized_fixture_ids",
        "read_model_data_time_before",
        "read_model_data_time_after",
        "dashboard_data_time_before",
        "dashboard_data_time_after",
        "scheduler_restart_policy",
        "blockers",
        "execution_mode",
        "execution_entrypoint",
        "scheduler_started",
        "celery_tasks_queued",
        "checkpoint_claim_delta",
        "REHEARSAL_COMMAND_EXECUTED",
        "expected_scheduler_restart_policy",
        "observed_scheduler_restart_policy",
        "flags_restored_disabled",
    ):
        assert activation_receipt_field in b5
    for activation_boundary in (
        "DB `audit_order` 最小值（1）作为唯一演练 scope",
        "execution_mode = MANUAL_FOREGROUND_ONE_SHOT",
        "execution_entrypoint = scripts/run_prematch_refresh.py",
        "scheduler_started = false",
        "celery_tasks_queued = 0",
        "checkpoint_claim_delta = 0",
        "`checkpoint_audit_delta = 0` 是允许结果",
        "不得伪造 checkpoint cycle",
        "lineup_event_delta = 0",
        "exact_pair_delta = 0",
        "scheduler container 未启动且 `restart=no`",
        "future-refresh flags 全部恢复",
        "不得扩大 endpoint allowlist",
        "增加 Provider budget",
        "自动重试",
        "REHEARSAL_STATUS = BLOCKED",
        "REHEARSAL_COMMAND_EXECUTED = false",
        "PR_448_MERGED_HEAD = 3466bd4419ff2339233fd659199a1dbf87370113",
        "PR_448_MERGE_SHA = c61bff2e50248db8e37b154fd233d456b18e7d0e",
        "PR_448_MAIN_CI = 30605554667 / SUCCESS",
        "projected_provider_calls = 10",
        "actual_provider_calls = 0",
        "provider_request_ledger_delta = 0",
        "raw_payload_delta = 0",
        "endpoint_capture_delta = 0",
        "dynamic_evaluation_v2_delta = 0",
        "five_state_snapshot_delta = 0",
        "materialized_fixture_ids = []",
        "expected_scheduler_restart_policy = no",
        "observed_scheduler_restart_policy = unless-stopped",
        "flags_restored_disabled = true",
        "SCHEDULER_RESTART_POLICY_MISMATCH_EXPECTED_NO_OBSERVED_UNLESS_STOPPED",
    ):
        assert activation_boundary in b5
    assert "SCHEDULER_START_AUTHORIZED = true" not in b5
    assert "PROVIDER_CALLS_AUTHORIZED = true" not in b5
    assert "RUNTIME_COLLECTION_AUTHORIZED = true" not in b5
    assert "A148_ONE_SUPERVISED_REHEARSAL" not in b5
    assert "SCHEDULER_MODE =\nFOREGROUND_ONE_CYCLE" not in b5
    assert "ONE_SUPERVISED_CHECKPOINT_CYCLE" not in b5
    assert "DYNAMIC_EVALUATION_V2_EVAL_02B_ELIGIBLE = true" not in b5
    assert (
        "PRE_CONFIRMATION_ELIGIBILITY =\n"
        "schema_version == w2.dynamic_quote_evaluation.v2\n"
        "capture_at < authoritative_lineup_event.captured_at\n"
        "lineup_input_hash == null\n"
        "exact_quote_identity_complete == true\n"
        "model_settlement_distribution_valid == true\n"
        "state_not_marker_or_not_ready == true\n"
        "original_state in ANALYSIS_PICK_ACTIVE | NO_EDGE_CURRENT"
    ) in b5
    assert (
        "POST_CONFIRMATION_ELIGIBILITY =\n"
        "schema_version == w2.dynamic_quote_evaluation.v2\n"
        "capture_at >= authoritative_lineup_event.captured_at\n"
        "lineup_input_hash == authoritative_lineup_event.lineup_input_hash\n"
        "post_lineup_quote == true\n"
        "quote_fresh == true\n"
        "exact_quote_identity_complete == true\n"
        "model_settlement_distribution_valid == true\n"
        "state_not_marker_or_not_ready == true\n"
        "original_state in ANALYSIS_PICK_ACTIVE | NO_EDGE_CURRENT"
    ) in b5
    assert "superseded == false" not in b5
    assert (
        "EVAL-01A\n"
        "EVAL-01B\n"
        "EVAL-01C\n"
        "EVAL-02A\n"
        "EVAL-02B_PREREGISTRATION_CONTRACT"
    ) in b5
    assert ".audit/" not in b5
    assert "/Users/" not in b5
    assert "500 个验证样本" in b5
    assert "Baseline 与 candidate 是两套独立概率向量" in b5
    assert "相同、有序的五态空间" in b5
    assert "不要求" in b5
    assert "概率值相等" in b5
    assert "概率和与 1 的差不得超过 `1e-9`" in b5
    assert "observed" in b5
    assert "settlement state 必须属于冻结五态" in b5
    assert "任一分布缺失或非法均 fail-closed" in b5
    assert (
        "paired_log_loss_improvement =\n"
        "LL(baseline_distribution, observed_state)\n"
        "-\n"
        "LL(candidate_distribution, observed_state)\n\n"
        "GATE_PASS =\n"
        "log_loss_improvement_ci_low > 0"
    ) in b5
    assert "整数盘、半盘和" in b5
    assert "四分之一盘统一使用上述合同" in b5
    assert "不得把 PUSH、HALF_WIN" in b5
    assert "或 HALF_LOSS 转成二元 outcome" in b5
    assert "不得发明新公式" in b5
    assert "EVAL-02B 继续 fail-closed" in b5
    assert "Bootstrap 只重采样 validation fixture pairs" in b5
    assert "2.5% 与 97.5% 分位数" in b5
    assert "Canonical JSON 禁止 NaN/Infinity" in b5
    assert "key 必须排序并使用 compact separators" in b5
    assert "validation pair 集合必须产生完全相同的整数 seed" in b5
    assert "相同输入必须产生相同的 split、" in b5
    assert "seed 和 bootstrap 区间" in b5
    assert (
        "BOOTSTRAP_SEED_PAYLOAD =\n"
        "canonical_json({\n"
        "  contract_version,\n"
        "  validation_pair_identity_hashes:\n"
        "    sorted(validation_pair_identity_hashes)\n"
        "})"
    ) in b5
    assert (
        "BOOTSTRAP_SEED =\n"
        "UNSIGNED_BIG_ENDIAN_UINT64(\n"
        "  FIRST_8_BYTES(BOOTSTRAP_SEED_HASH)\n"
        ")"
    ) in b5
    assert "RPS 与 coverage 必须输出" in b5
    assert "不得作为 blocker" in b5
    assert "不得跨 provider、bookmaker、selection 或 line 配对" in b5
    for obsolete_coordinate in (
        "SCORING_DISTRIBUTION =",
        "BASELINE_AND_CANDIDATE_DISTRIBUTION_SCHEMA =",
        "PAIR_LOG_LOSS =",
        "PROBABILITY_SUM = 1_WITHIN_TOLERANCE",
        "BOOTSTRAP_SEED_INPUT =",
    ):
        assert obsolete_coordinate not in b5
    b7 = checklist[
        checklist.index("#### B7. EVAL-03") : checklist.index("### 模型升级")
    ]
    assert "Status: NOT_STARTED" in b7
    assert "W2_ARCHITECTURE_CONVERGENCE_COMPLETE = PASS" in checklist
    for task in FORBIDDEN_TASKS:
        assert task not in state
        if task != "CLOSURE":
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
