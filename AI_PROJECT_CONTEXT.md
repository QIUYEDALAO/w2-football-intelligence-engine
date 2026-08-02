# W2 AI Project Context

> 任何 AI 或人接手 W2 时先读本文件。本文件是“已完成 + 核心规则 + 当前待办”的交接摘要；代码、数据库约束、migration、Git 历史、完整 Actions 日志和可复现实验仍是最终证据。

## 权威入口

- 当前机器状态：[`PROJECT_STATE.yaml`](PROJECT_STATE.yaml)
- 当前动作：[`NEXT_ACTION.md`](NEXT_ACTION.md)
- 当前执行总单：GitHub Issue **#454 v5 FINAL FROZEN BASELINE**
- 一次性 canary 冻结范围：Issue **#452**
- workflow 治理事件：Issue **#455**
- R5 计算权威：Issue **#456**
- 基础设施事件：Issue **#457**（保持 OPEN，状态不在本文件重定性）
- 原始 C9：Issue **#451**
- 历史任务规格与已合并回执：`docs/operations/architecture_convergence/W2_ARCHITECTURE_CONVERGENCE_MASTER_CHECKLIST.md`
- 独立终审：`docs/operations/W2_INDEPENDENT_FINAL_AUDIT_20260731.md`
- 资产唯一性审计：`docs/operations/W2_ASSET_UNIQUENESS_AUDIT_20260731.md`
- 审计视角登记：`docs/operations/W2_AUDIT_PERSPECTIVE_REGISTRY.md`
- Wave 4 脱敏永久回执：`docs/operations/W2_WAVE4_REAL_CANARY_RECEIPT_20260802.md`
- VPS postdeploy 脱敏回执：`docs/operations/W2_VPS_POSTDEPLOY_RECEIPT_20260802.md`

## 可信基线

```text
repository = QIUYEDALAO/w2-football-intelligence-engine
audit_baseline_sha = dbc8e1e8aa74a7613fd7121bf6026890c3ee06c6
current_main_sha = fe03a8267d7086c87557c267afb12d32433bd2cf
deployed_sha = fe03a8267d7086c87557c267afb12d32433bd2cf
main contaminated by e875050f = false
main rollback required = false
PR #453 = QUARANTINED / DO NOT MERGE / DO NOT REPAIR IN PLACE
PR #450 = FINAL ACCEPTANCE REVIEW COMPLETED / ACCEPTED HEAD IN FINAL INTEGRATION
```

## 已完成

- P0/P1/P2 架构收敛按冻结范围完成，历史完成回执继续有效。
- 阶段 A、EVAL-01A/B/C、EVAL-02A 在冻结实现范围内完成。
- OPS-01 Runbook 文档完成，runtime enablement 未完成。
- EVAL-02B 预注册合同、Legacy 35 永久排除决策、写侧 Implementation 01–04 完成。
- exact-pair 核心实现具备 `capture_at` 边界、同 provider/bookmaker/market/selection/exact line、五态合法性与歧义 fail-closed。
- `2/2.5 -> 2.25` 是明确测试合同，不是已证实缺陷。
- `readiness.py` 是状态计算器，不是 Provider live-call 入口。

“代码任务完成”不能扩大成“端到端运行能力完成”。

## 当前状态

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
EVAL-02B END-TO-END = PROVEN
EVAL-03 = NOT STARTED
WAVE_1 = PASS_AND_FROZEN
T00_RERUN = FORBIDDEN_UNLESS_NEW_APPROVED_EVIDENCE
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

Wave 1 的绑定终态已经由 PR #458 exact-head 独立验收确认：

```text
WAVE_1_FINAL = PASS_WITH_BOUNDED_CARRY_FORWARD
FINAL_GATE_A_GROUPS = 28
FINAL_EXACT_C1_C11_MAPPINGS = 35
FINAL_TEST_CONTRACT_SKELETONS = 30
ROLE_FIELDS_CARRIED_TO_PR450 = 145
ROLE_FIELD_DISPOSITION = CARRY_TO_PR450_DOCUMENTATION_REPAIR
WAVE_2 = PASS
SER_05_INDEPENDENT_ORACLE = PASS
PR_461 = INTEGRATED_INTO_PR_460
```

完整 all-call ledger 与 grouped effect inventory 保持冻结，不在 PR #450 重新分组。
PR #450 只恢复可信 main 保留的 145 条历史守卫、承接 145 个 `role` 字段并硬守卫
当前 authority matrix 的 9 个表头名称、顺序和列数。上述 28/35/30 是 Wave 1
独立验收后的冻结集合；Wave 3 已按该冻结集合完成，分母继续保持冻结。

A148 只能定义为：

```text
FAIL_CLOSED_BARRIER = PASS
PROVIDER_EXECUTION = NOT EXECUTED
END_TO_END_CHAIN = NOT VALIDATED
RUNTIME_COLLECTION_READINESS = NOT PROVEN
```

## 风险家族

```text
R1 Default allow / missing authority
R2 Silent failure / failure downgrade
R3 External side effect / local-state non-atomicity
R4 Authority split / concurrency / identity drift
R5 Computation authority split
```

Wave 1 的 T00 已用 exact-SHA-bound、优先 AST、可复跑扫描器完成并冻结；除非出现新的、
明确批准的证据，不得重新执行或调整其分母。

## workflow 治理

已核实 automation commit `e875050f...` 修改 C9 代码并删除触发 workflow。PR #453 的历史不再是实现权威。

强制规则：

- 从可信 `origin/main` 创建本地 clean worktree；
- 禁止 merge/rebase/cherry-pick PR #453、`agent/eval-02b-c9-*`、`e875050f...` 或其他 automation-authored remediation；
- 保留污染 refs 供 #455 调查；
- 业务实现只允许正常本地 edit/commit/push/Draft PR；
- 禁止 workflow 使用写权限改写受审业务分支。

## 资产与计算权威

### 存储层

Wave 1 的存储 inventory 已完成并冻结；本阶段不重新执行 T00。

```text
DUPLICATE_TABLE_CREATION_IN_LINEAR_UPGRADE_PATH_WITHOUT_INTERVENING_DROP_OR_RENAME = 0
```

此结论不关闭 `0002–0016` 动态引用当前 ORM metadata 的 Gate D 风险。

### R5 canonical serialization

运行相关 serializer/hash writer inventory 已由 Wave 1 T00-R5 冻结；本阶段不重新计数。
Wave 2 / SER-01 至 SER-07、独立 Oracle 与 Gate A 已完成验收。下列合同继续永久有效：

1. 全量 hash/serializer inventory；
2. SER-02 ADR 与版本化合同；
3. compatibility/migration/rollback；
4. `src/w2/domain/` 唯一版本化权威；
5. SER-05 golden vectors 和独立 oracle；
6. 静态防重复守卫；
7. 独立复算验收。

禁止在 SER-02 前选择 `ensure_ascii=True` 或 `False`；禁止原地覆盖历史 hash。

独立 oracle 的最低条件：

```text
PRODUCTION_SERIALIZER_IMPLEMENTER != ORACLE_GOLDEN_VECTOR_AUTHOR
ORACLE_IMPORTS_PRODUCTION_SERIALIZER = false
INDEPENDENT_REVIEWER_RECORDED = true
```

不满足时只能标记 `SELF_REVIEWED_ONLY`。

## 核心工程规则

1. 缺失、非法、陈旧、未知或不可验证的安全输入必须 `BLOCKED`。
2. Provider 请求可能送达后，后续失败必须持久化、显式冒泡、停止后续调用并禁止自动 Provider retry。
3. 幂等只在命中预期约束、回读既存行且全部业务字段一致时成立。
4. Required empty、吞异常、无锁执行、陈旧 quota 和未执行都不是成功。
5. 同一事实只有一个可版本化、可独立复算的计算权威；不同定义必须显式命名和版本化。
6. 历史 identity/hash 未经版本化 migration/compatibility 方案不得覆盖。
7. 完成声明必须列出覆盖和未覆盖审计视角。
8. 同源测试不等于独立 oracle。
9. 真实事故无法映射现有视角时，必须在同一整改中扩展视角登记表。
10. 不得为绿 CI 删除、skip、xfail 或放宽 required event、五态 `1e-9`、package matrix、delta、lineage、migration、故障注入和历史守卫。

## PR #450 守卫要求

`tests/contract/test_delivery_status_documentation.py` 的删除必须建立完整等价性矩阵：

```text
ORIGINAL_GUARD
CURRENT_EQUIVALENT
CLASSIFICATION = RETAINED_EQUIVALENT | LOST_AND_RESTORED | INTENTIONALLY_RETIRED_WITH_EVIDENCE
RATIONALE
EVIDENCE
UNCLASSIFIED_REMOVED_GUARDS = 0
```

至少恢复：

- historical PR range explicit non-authority guard；
- retired staging address absence guard。

顶层任务保持 `EVAL-02B`，T00 是 workstream；`task_authority` 继续指向主清单，`active_execution_authority` 指向 #454。

## 真实 canary 硬合同

全部增量必须为正：

```text
actual_provider_calls_delta      > 0
provider_request_ledger_delta    > 0
raw_payload_delta                > 0
endpoint_capture_delta           > 0
lineup_event_delta               > 0
dynamic_evaluation_v2_delta      > 0
five_state_snapshot_delta        > 0
exact_pair_delta                 > 0
```

同一 lineage 至少包含：

```text
run_id
authorization_id
competition_id
season
fixture_id
provider
bookmaker
market
selection
exact_line
capture_at
raw_payload_sha256
endpoint_capture_id
lineup_input_hash
evaluation_id
pair_hash
exact_git_sha
serializer_version
```

以下均为独立硬失败，不得降级 warning：

```text
SERIALIZER_VERSION_MISSING
INDEPENDENT_PAIR_HASH_MISMATCH
INDEPENDENT_BOOTSTRAP_SEED_MISMATCH
NAN_OR_INFINITY
ANY_REQUIRED_DELTA_ZERO
LINEAGE_MISMATCH
```

## #454 v5 历史执行顺序与当前边界

Wave 1 / T00 已完成并冻结；Wave 2 independent serializer oracle、Wave 3 C9 与 Gate A、
Wave 4 单次真实 Canary 均已验收通过，`EVAL_02B_REAL_CHAIN = PROVEN`。正式 main
`fe03a8267d7086c87557c267afb12d32433bd2cf` 已使用其 post-merge CI immutable digests 部署，
migration、health、ready、release sync 均通过，部署期间 Provider 增量为 0，scheduler 保持关闭。
当前唯一下一动作是 `POSTDEPLOY_OBSERVATION_AND_COLLECTION_POLICY_ROLLOUT`。Issue #457 项目
gate 已按 owner risk acceptance 关闭，PR #450 accepted head 已纳入 main。

## Gate 分层

- **Gate A：** 一次人工前台 canary。
- **Gate B：** 持续 scheduler、多联赛、自动恢复、Celery、长期 lease、完整 readiness/progress、容量与背压。
- **Gate C：** fair odds、market taxonomy、Brier/ECE、EV/五态/结算/CLV 独立数学 oracle，以及 Candidate/Formal/Lock。
- **Gate D：** migration replay、备份恢复、灾备、安全权限、凭据与日志、长期 soak 和 Production。

## 接手动作

1. 先读本文件、`PROJECT_STATE.yaml`、`NEXT_ACTION.md` 和 #454/#457 最新 binding decision。
2. 核对 `CURRENT_MAIN_SHA = DEPLOYED_SHA = fe03a826...` 与
   `ACTIVE_NEXT_ACTION = POSTDEPLOY_OBSERVATION_AND_COLLECTION_POLICY_ROLLOUT`。
3. 不重跑或扩大 T00；不要重新执行已通过的 C9、Gate A 或真实 Canary。
4. 不得使用、复制、merge 或 cherry-pick PR #453 / `e875050f...`。
5. 保留 PR #450 恢复的历史守卫与 145 个 role 字段账目；不得放宽 C9 required event 断言。
6. postdeploy context PR 不调用 Provider、不创建新授权、不启动持续 scheduler、不再次部署、不自动合并。
7. 最终输出：

```text
REAL_PROVIDER_CALL_EXECUTED_IN_POSTDEPLOY = false
PERSISTENT_SCHEDULER_STARTED = false
DEPLOYMENT_STATUS = PASS
AUTO_MERGE_EXECUTED = false
READY_FOR_FINAL_DEPLOYMENT_ACCEPTANCE = true|false
```
