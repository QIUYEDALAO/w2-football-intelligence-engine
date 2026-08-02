# W2 GitHub Copilot Instructions

先读 `AI_PROJECT_CONTEXT.md`、`PROJECT_STATE.yaml`、`NEXT_ACTION.md`、两份审计、视角登记表，以及 GitHub Issue #454 v5、#455、#456。

## 权威与任务

```text
TOP_LEVEL_TASK = EVAL-02B
ACTIVE_NEXT_ACTION = EXECUTE_WAVE_3_C9_THEN_GATE_A_OFFLINE
ACTIVE_CONTEXT_PR = 450
CURRENT_WORKSTREAM = EVAL-02B-C9-AND-GATE-A
CURRENT_PHASE = WAVE_3_C9_THEN_GATE_A_OFFLINE
TASK_AUTHORITY = docs/operations/architecture_convergence/W2_ARCHITECTURE_CONVERGENCE_MASTER_CHECKLIST.md
ACTIVE_EXECUTION_AUTHORITY = Issue #454 v5
TRUSTED_MAIN = dbc8e1e8aa74a7613fd7121bf6026890c3ee06c6
```

#457 可保持 OPEN 作为运维风险记录；项目 gate 已由 binding decision 以 owner risk acceptance 关闭。
Wave 1 / T00 已完成并冻结；除非出现新的、明确批准的证据，不得重跑 T00。
Wave 2 已在 combined exact head 完成；Wave 3 已获授权，且必须先 C9、后 Gate A 离线整改。

## Source rules

- 先 `git fetch --all --prune --tags` 并核对可信 main。
- 从可信 main 的本地 clean worktree 工作。
- 不使用 PR #453、`agent/eval-02b-c9-*`、`e875050f...` 或其他 automation-authored remediation。
- 不创建会使用写权限改写业务 PR 分支的 workflow。
- 仅通过正常 local edit/commit/push/Draft PR 提交实现。

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
WAVE_1 = CLOSED_AND_FROZEN
T00_RERUN = FORBIDDEN_UNLESS_NEW_APPROVED_EVIDENCE
FINAL_GATE_A_GROUPS = 28
FINAL_EXACT_C1_C11_MAPPINGS = 35
FINAL_TEST_CONTRACT_SKELETONS = 30
ROLE_FIELDS_CARRIED_TO_PR450 = 145
ROLE_FIELD_DISPOSITION = CARRY_TO_PR450_DOCUMENTATION_REPAIR
ISSUE_457_PROJECT_GATE = CLOSED_WITH_OWNER_RISK_ACCEPTANCE
WAVE_2 = CLOSED_WITH_EXISTING_C9_BLOCKER
SER_05_INDEPENDENT_ORACLE = PASS
PR_461 = INTEGRATED_INTO_PR_460
WAVE_3_AUTHORIZED = true
NEXT_CODE_ACTION = C9_TRUSTED_REBUILD_THEN_GATE_A_OFFLINE
PR_450 = DRAFT
PR_450_FINAL_ACCEPTANCE_REVIEW = COMPLETED
PREDEPLOY_C9 = EXISTING_BLOCKER
PROVIDER = OFF
REAL_PROVIDER = OFF
REAL_CANARY = NOT_AUTHORIZED
PERSISTENT_SCHEDULER = OFF
CANDIDATE / FORMAL / LOCK / PRODUCTION = OFF
AUTO_MERGE = FORBIDDEN
```

PR #450 只允许上下文和守卫收口：保留全部历史守卫，硬校验 authority matrix
表头名称、顺序与列数，并显式承接 145 个 `role` 字段。不得重新计算或重新分组
Wave 1 分母。当前从 PR #460 combined head 先可信重建 C9；只有 exact predeploy 通过后
才执行冻结的 Gate A 离线整改。PR #450 final acceptance review 已发生并继续保持 Draft。

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
REAL_PROVIDER_CALL_EXECUTED = false
REAL_CANARY_AUTHORIZATION_CREATED = false
AUTO_MERGE_EXECUTED = false
```
