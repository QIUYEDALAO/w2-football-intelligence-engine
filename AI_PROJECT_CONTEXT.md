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
- Production recovery 脱敏回执：`docs/operations/W2_PRODUCTION_RECOVERY_RECEIPT_20260803.md`
- 推荐权威与真实 fixture 重放回执：`docs/operations/W2_RECOMMENDATION_AUTHORITY_REAL_FIXTURE_REPLAY_RECEIPT_20260804.md`
- 真实 fixture 重放脱敏 manifest：`docs/operations/W2_REAL_FIXTURE_REPLAY_SANITIZED_MANIFEST_20260804.json`

## 可信基线

```text
repository = QIUYEDALAO/w2-football-intelligence-engine
audit_baseline_sha = dbc8e1e8aa74a7613fd7121bf6026890c3ee06c6
current_main_sha = 8c6086e37ba62c138bdf059997ca760accef7067
deployed_sha = 8c6086e37ba62c138bdf059997ca760accef7067
main contaminated by e875050f = false
main rollback required = false
PR #453 = QUARANTINED / DO NOT MERGE / DO NOT REPAIR IN PLACE
PR #450 = FINAL ACCEPTANCE REVIEW COMPLETED / ACCEPTED HEAD IN FINAL INTEGRATION
```

## 已完成

- P0/P1/P2 架构收敛按冻结范围完成，历史完成回执继续有效。
- 阶段 A、EVAL-01A/B/C、EVAL-02A 在冻结实现范围内完成。
- OPS-01 Runbook 文档完成；四个 collection-ready 联赛的受控 runtime collection 已启用。
- EVAL-02B 预注册合同、Legacy 35 永久排除决策、写侧 Implementation 01–04 完成。
- exact-pair 核心实现具备 `capture_at` 边界、同 provider/bookmaker/market/selection/exact line、五态合法性与歧义 fail-closed。
- `2/2.5 -> 2.25` 是明确测试合同，不是已证实缺陷。
- `readiness.py` 是状态计算器，不是 Provider live-call 入口。

“代码任务完成”不能扩大成“端到端运行能力完成”。

## 当前状态

```text
TOP_LEVEL_TASK = EVAL-02B
ACTIVE_NEXT_ACTION = POST_RECOVERY_OBSERVATION_AND_DYNAMIC_EVALUATION_READINESS
ACTIVE_CONTEXT_PR = NONE
CURRENT_WORKSTREAM = POST_RECOVERY_OBSERVATION_AND_DYNAMIC_EVALUATION_READINESS
CURRENT_PHASE = PRODUCTION_RECOVERY_CONTEXT_CLOSURE_COMPLETE
AUDIT_BASELINE_SHA = dbc8e1e8aa74a7613fd7121bf6026890c3ee06c6
CURRENT_MAIN_SHA = 8c6086e37ba62c138bdf059997ca760accef7067
DEPLOYED_SHA = 8c6086e37ba62c138bdf059997ca760accef7067
VPS_DEPLOYMENT = PASS
MIGRATION_HEAD = 0050_gate_a_runtime_selection
RELEASE_SYNC = PASS
REAL_PROVIDER_CALL_DELTA = 58
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
PROVIDER = ON_CONTROLLED
REAL_PROVIDER = ON_CONTROLLED
REAL_CANARY = PASS
PERSISTENT_SCHEDULER = ON_CONTROLLED
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
AUTO_MERGE = FORBIDDEN
```

## Production recovery 闭环

```text
DASHBOARD_REAL_DATA_RECOVERY = PASS
PUBLIC_DASHBOARD_CARDS = 51
PRODUCTION_FUTURE_FIXTURES = 51
PROVIDER_REQUEST_DELTA = 58
ENDPOINT_CAPTURE_DELTA = 58
PROVIDER_ERRORS = 0

COLLECTION_READY_COMPETITIONS = brasileirao_serie_a,chinese_super_league,allsvenskan,eliteserien
PERSISTENT_SCHEDULER = ON_CONTROLLED
SCHEDULER_CONCURRENCY = 1
PROVIDER_ATTEMPTS = 1
DAILY_HARD_CAP = 120
TICK_HARD_CAP = 30

DYNAMIC_EVALUATION_V2 = 0
EXPLICIT_NOT_READY_CARDS = 51
DYNAMIC_EVALUATION_PRODUCTION_RECOVERY = PENDING
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF

ACTIVE_NEXT_ACTION = POST_RECOVERY_OBSERVATION_AND_DYNAMIC_EVALUATION_READINESS
EVAL-03 = NOT STARTED
COLD_PULL_SLO = NOT_PROVEN
```

## Recommendation authority 与真实 fixture 重放闭环

```text
PUBLIC_RECOMMENDATION_AUTHORITY = SINGLE
REAL_FIXTURE_OFFLINE_REPLAY = PASS
LINEUP_NUMERIC_VALUE_MODEL = NOT_IMPLEMENTED
LINEUP_NUMERIC_ADJUSTMENT = OFF
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
```

当前公共推荐只认 `w2.recommendation_decision.v4`；历史 V3 仅供展示、历史读取与结算。
真实 fixture 已从保存的四端点 raw evidence 开始，在网络禁用条件下两次独立复算并得到相同
canonical bytes。首发只参与 readiness、证据和首发后赔率刷新，尚未进入模型概率数值调整。

## Delivery pipeline

```text
DELIVERY_MODEL = RELEASE_CANDIDATE_PROMOTION_V1
MERGE_QUEUE = NOT_AVAILABLE_CURRENT_PERSONAL_REPOSITORY
PR_FAST_REQUIRED = ENABLED
RELEASE_REQUIRED = ENABLED
MAIN_DUPLICATE_FULL_CI = DISABLED
MAIN_DUPLICATE_IMAGE_BUILD = DISABLED
IMAGE_TRANSPORT = LOCAL_OCI_RELAY_PRIMARY / GHCR_ARCHIVE_AND_FALLBACK
ACTIVE_NEXT_ACTION = POST_RECOVERY_OBSERVATION_AND_DYNAMIC_EVALUATION_READINESS
```

其余已注册但尚未同时接入 future-refresh 与 matchday policy 的联赛保持注册，不得从
白名单删除：

- `argentina_primera`
- `bundesliga`
- `eredivisie`
- `la_liga`
- `ligue_1`
- `mls`
- `premier_league`
- `primeira_liga`
- `serie_a`

上述 58 次 Provider request 与 58 条 endpoint capture 一一对账，Provider error 为 0。
当前公网 51 张卡片都是显式 `NOT_READY`；`DYNAMIC_EVALUATION_V2 = 0`，因此不得宣称
production dynamic evaluation 已恢复。cold-pull 两次超过部署 SLO 并回滚，warm switch
成功不能替代 cold-pull SLO 证明。

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
`8c6086e37ba62c138bdf059997ca760accef7067` 已使用其 post-merge CI immutable digests 部署，
Dashboard 真实数据恢复通过，四联赛 scheduler 以受控模式运行。
当前唯一下一动作是 `POST_RECOVERY_OBSERVATION_AND_DYNAMIC_EVALUATION_READINESS`。Issue #457 项目
gate 已按 owner risk acceptance 关闭，PR #450 accepted head 已纳入 main。

## Gate 分层

- **Gate A：** 一次人工前台 canary。
- **Gate B：** 四联赛受控 scheduler 与 Celery 已运行；自动恢复、长期 soak、完整 readiness/progress、容量与背压仍待证明。
- **Gate C：** fair odds、market taxonomy、Brier/ECE、EV/五态/结算/CLV 独立数学 oracle，以及 Candidate/Formal/Lock。
- **Gate D：** migration replay、备份恢复、灾备、安全权限、凭据与日志、长期 soak 和 Production。

## 接手动作

1. 先读本文件、`PROJECT_STATE.yaml`、`NEXT_ACTION.md` 和 #454/#457 最新 binding decision。
2. 核对 `CURRENT_MAIN_SHA = DEPLOYED_SHA = 8c6086e3...` 与
   `ACTIVE_NEXT_ACTION = POST_RECOVERY_OBSERVATION_AND_DYNAMIC_EVALUATION_READINESS`。
3. 不重跑或扩大 T00；不要重新执行已通过的 C9、Gate A 或真实 Canary。
4. 不得使用、复制、merge 或 cherry-pick PR #453 / `e875050f...`。
5. 保留 PR #450 恢复的历史守卫与 145 个 role 字段账目；不得放宽 C9 required event 断言。
6. context-only PR 不调用 Provider、不创建新授权、不重启或扩大现有 scheduler、不再次部署、不自动合并。
7. 最终输出：

```text
CONTEXT_CLOSURE_PROVIDER_CALL_DELTA = 0
SCHEDULER_RESTARTED_IN_CONTEXT_CLOSURE = false
DEPLOYMENT_EXECUTED_IN_CONTEXT_CLOSURE = false
AUTO_MERGE_EXECUTED = false
```
