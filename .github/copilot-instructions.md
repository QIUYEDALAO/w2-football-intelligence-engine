# W2 GitHub Copilot Instructions

先读 `AI_PROJECT_CONTEXT.md`、`PROJECT_STATE.yaml`、`NEXT_ACTION.md`、两份审计、视角登记表，以及 GitHub Issue #454 v5、#455、#456。

## 权威与任务

```text
TOP_LEVEL_TASK = EVAL-02B
ACTIVE_NEXT_ACTION = POSTDEPLOY_OBSERVATION_AND_COLLECTION_POLICY_ROLLOUT
ACTIVE_CONTEXT_PR = 465
CURRENT_WORKSTREAM = POSTDEPLOY_OBSERVATION_AND_COLLECTION_POLICY_ROLLOUT
CURRENT_PHASE = POSTDEPLOY_CLOSURE_COMPLETE
TASK_AUTHORITY = docs/operations/architecture_convergence/W2_ARCHITECTURE_CONVERGENCE_MASTER_CHECKLIST.md
ACTIVE_EXECUTION_AUTHORITY = Issue #454 v5
AUDIT_BASELINE_SHA = dbc8e1e8aa74a7613fd7121bf6026890c3ee06c6
CURRENT_MAIN_SHA = fe03a8267d7086c87557c267afb12d32433bd2cf
DEPLOYED_SHA = fe03a8267d7086c87557c267afb12d32433bd2cf
```

#457 可保持 OPEN 作为运维风险记录；项目 gate 已由 binding decision 以 owner risk acceptance 关闭。
Wave 1 / T00 已完成并冻结；除非出现新的、明确批准的证据，不得重跑 T00。
Wave 2、Wave 3 和 Wave 4 单次真实 Canary 已通过，EVAL-02B 真实链路已证明。

## Source rules

- 先 `git fetch --all --prune --tags` 并核对 current main `fe03a826...`；`dbc8e1e8...`
  只作为历史审计基线。
- 从可信 main 的本地 clean worktree 工作。
- 不使用 PR #453、`agent/eval-02b-c9-*`、`e875050f...` 或其他 automation-authored remediation。
- 不创建会使用写权限改写业务 PR 分支的 workflow。
- 仅通过正常 local edit/commit/push/PR 提交实现；本 final integration PR 必须非 Draft，
  只允许 merge commit，禁止 squash 与 auto-merge。

## Core rules

- Missing/unknown safety input = BLOCKED。
- Provider 可能送达后，失败必须显式、持久化、停后续调用、禁止自动 retry。
- 幂等需要预期约束和全部业务字段核验。
- Required zero evidence = FAILED。
- 一个事实只有一个版本化计算权威；历史 hash 不得无迁移覆盖。
- 不得放宽 event、五态 `1e-9`、package matrix、delta、lineage、migration、fault-injection 或历史守卫。
- `2/2.5 -> 2.25` 是已验证合同。
- `readiness.py` 不是 Provider live-call 入口。

## R5

在 SER-02 前不得选择 `ensure_ascii`。SER-05 independent oracle 必须由不同作者实现、不得 import 生产 serializer，并记录独立 reviewer。

## Post-Wave-1 freeze

```text
WAVE_1_FINAL = PASS_WITH_BOUNDED_CARRY_FORWARD
WAVE_1 = PASS_AND_FROZEN
T00_RERUN = FORBIDDEN_UNLESS_NEW_APPROVED_EVIDENCE
FINAL_GATE_A_GROUPS = 28
FINAL_EXACT_C1_C11_MAPPINGS = 35
FINAL_TEST_CONTRACT_SKELETONS = 30
ROLE_FIELDS_CARRIED_TO_PR450 = 145
ROLE_FIELD_DISPOSITION = CARRY_TO_PR450_DOCUMENTATION_REPAIR
ISSUE_457_PROJECT_GATE = CLOSED_WITH_OWNER_RISK_ACCEPTANCE
WAVE_2 = PASS
WAVE_3 = PASS
WAVE_4_REAL_CANARY = PASS
EVAL_02B_REAL_CHAIN = PROVEN
REAL_CANARY_PROVIDER_CALLS = 5
REAL_CANARY_EVIDENCE_SHA256 = 30e961cbedee33b5ec74bf3eabbd80a202ced3b9b21483160896812442ddd1f4
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

PR #450 只允许上下文和守卫收口：保留全部历史守卫，硬校验 authority matrix
表头名称、顺序与列数，并显式承接 145 个 `role` 字段。不得重新计算或重新分组
Wave 1 分母。PR #450 final acceptance review 已发生，其 accepted head 已纳入 final
integration；不得重新执行已经通过的 C9、Gate A 或真实 Canary。

## Canary hard failures

```text
SERIALIZER_VERSION_MISSING
INDEPENDENT_PAIR_HASH_MISMATCH
INDEPENDENT_BOOTSTRAP_SEED_MISMATCH
NAN_OR_INFINITY
ANY_REQUIRED_DELTA_ZERO
LINEAGE_MISMATCH
```

## Stop line

```text
REAL_PROVIDER_CALL_EXECUTED_IN_POSTDEPLOY = false
PERSISTENT_SCHEDULER_STARTED = false
DEPLOYMENT_STATUS = PASS
AUTO_MERGE_EXECUTED = false
```
