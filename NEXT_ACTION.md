# NEXT ACTION

当前唯一动作：`POSTDEPLOY_OBSERVATION_AND_COLLECTION_POLICY_ROLLOUT`。正式 main
`fe03a8267d7086c87557c267afb12d32433bd2cf` 已部署并通过 postdeploy 验收；后续仍不得调用
Provider、启动 scheduler 或开放 Candidate、Formal、Lock、Production，除非 #454 给出新的
binding execution decision。

```text
TOP_LEVEL_TASK = EVAL-02B
ACTIVE_NEXT_ACTION = POSTDEPLOY_OBSERVATION_AND_COLLECTION_POLICY_ROLLOUT
ACTIVE_CONTEXT_PR = POSTDEPLOY_CONTEXT_PR_PENDING
CURRENT_WORKSTREAM = POSTDEPLOY_OBSERVATION_AND_COLLECTION_POLICY_ROLLOUT
CURRENT_PHASE = POSTDEPLOY_CLOSURE_COMPLETE
AUDIT_BASELINE_SHA = dbc8e1e8aa74a7613fd7121bf6026890c3ee06c6
CURRENT_MAIN_SHA = fe03a8267d7086c87557c267afb12d32433bd2cf
DEPLOYED_SHA = fe03a8267d7086c87557c267afb12d32433bd2cf
VPS_DEPLOYMENT = PASS
MIGRATION_HEAD = 0050_gate_a_runtime_selection
RELEASE_SYNC = PASS
REAL_PROVIDER_CALL_DELTA = 0
CANARY_DATABASE_DELETED = true
WAVE_1 = PASS_AND_FROZEN
WAVE_1_FINAL = PASS_WITH_BOUNDED_CARRY_FORWARD
WAVE_2 = PASS
WAVE_3 = PASS
WAVE_4_REAL_CANARY = PASS
EVAL_02B_REAL_CHAIN = PROVEN
REAL_CANARY_PROVIDER_CALLS = 5
REAL_CANARY_EVIDENCE_SHA256 = 30e961cbedee33b5ec74bf3eabbd80a202ced3b9b21483160896812442ddd1f4
T00_RERUN = FORBIDDEN_UNLESS_NEW_APPROVED_EVIDENCE
FINAL_GATE_A_GROUPS = 28
FINAL_EXACT_C1_C11_MAPPINGS = 35
FINAL_TEST_CONTRACT_SKELETONS = 30
ISSUE_457_PROJECT_GATE = CLOSED_WITH_OWNER_RISK_ACCEPTANCE
SER_05_INDEPENDENT_ORACLE = PASS
PR_461 = INTEGRATED_INTO_PR_460
NEXT_CODE_ACTION = NONE_AUTHORIZED
PR_450 = ACCEPTED_HEAD_FOR_FINAL_INTEGRATION
PR_450_FINAL_ACCEPTANCE_REVIEW = COMPLETED
PREDEPLOY_C9 = PASS
PROVIDER = OFF
REAL_PROVIDER = OFF
REAL_CANARY = PASS
PERSISTENT_SCHEDULER = OFF
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
AUTO_MERGE = FORBIDDEN
```

- Machine-readable status: [PROJECT_STATE.yaml](PROJECT_STATE.yaml)
- Task specifications and merged receipts: [W2 architecture convergence master checklist](docs/operations/architecture_convergence/W2_ARCHITECTURE_CONVERGENCE_MASTER_CHECKLIST.md)
- Active execution authority: GitHub Issue #454 v5
- R5 computation authority: GitHub Issue #456
- Wave 4 sanitized receipt: [W2 Wave 4 Real Canary Receipt](docs/operations/W2_WAVE4_REAL_CANARY_RECEIPT_20260802.md)
- Postdeploy sanitized receipt: [W2 VPS Postdeploy Receipt](docs/operations/W2_VPS_POSTDEPLOY_RECEIPT_20260802.md)

`current_pr: null` 只表示当前没有业务实现 PR；`active_context_pr` 将在本次 postdeploy
context PR 创建后回填。PR #450 仍是历史守卫来源，不再是当前上下文 PR。

## Historical receipt / 历史回执

A148 的旧动作和证据仅保存在 `PROJECT_STATE.yaml` 的 `historical_receipts.a148`。
该历史回执继续保护当时的 fail-closed、Provider 零调用、业务零写入、scheduler/Celery
未启动、一次性授权撤销和端到端链路未验收事实；它不覆盖此后验收通过的 Wave 4 真实
Canary 回执。Wave 1 的 T00-R5 inventory 与 Issue #456 继续冻结，不得重跑或改分母。

## Stop line

本轮不得调用 Provider、创建新的真实授权、启动 persistent scheduler、再次部署、开放
Candidate/Formal/Lock/Production 或自动 merge。观察期与采集 policy rollout 需要新的
binding execution decision 才能改变当前关闭状态。
