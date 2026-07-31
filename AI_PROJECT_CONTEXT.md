# W2 AI Project Context

> **用途：** 任何 AI 或人接手 W2 时先读本文件。它是“已完成 + 核心规则 + 当前待办”的 AI 汇总，不替代代码、数据库约束、Git history、Actions logs 和独立审查。
>
> 机器状态：[`PROJECT_STATE.yaml`](PROJECT_STATE.yaml)  
> 当前动作：[`NEXT_ACTION.md`](NEXT_ACTION.md)  
> 独立终审：[`docs/operations/W2_INDEPENDENT_FINAL_AUDIT_20260731.md`](docs/operations/W2_INDEPENDENT_FINAL_AUDIT_20260731.md)  
> 审计视角登记：[`docs/operations/W2_AUDIT_PERSPECTIVE_REGISTRY.md`](docs/operations/W2_AUDIT_PERSPECTIVE_REGISTRY.md)  
> 冻结执行总单：GitHub Issue **#454 v3**  
> 自修改 workflow 治理事件：GitHub Issue **#455**

## 1. 当前可信基线

```text
repository = QIUYEDALAO/w2-football-intelligence-engine
trusted_main = dbc8e1e8aa74a7613fd7121bf6026890c3ee06c6
compare(trusted_main, main) = identical
```

- PR #449 已包含在该 main 基线中。
- `e875050f6bc0286aed389aadfce1e17b2063635a` 不是 main 的祖先。
- 当前已知污染被限制在 Draft agent 分支，main 不需要回滚或历史重写。
- PR #453 已隔离为证据：`QUARANTINED / DO NOT MERGE / DO NOT REPAIR IN PLACE`。

## 2. 已完成

- P0/P1/P2 架构收敛完成，其冻结范围继续保持有效，不因当前 C1–C11 重开。
- 阶段 A 已合并任务完成；`ARCH-GOVERNANCE-01` 曾完成，但 post-merge consistency gate 后来退役。
- EVAL-01A、EVAL-01B、EVAL-01C、EVAL-02A 在冻结实现范围内完成。
- OPS-01 Runbook 文档完成；真实运行 enablement 未完成。
- EVAL-02B 预注册合同、Legacy 35 永久排除决策、写侧 Implementation 01–04 完成。
- exact-pair 核心合同已实现：以 `capture_at` 划分 Pre/Post，同 provider/bookmaker/market/selection/exact line，五态概率合法，歧义 fail-closed。
- `2/2.5 -> 2.25` 等合法 split-line 语义是明确实现和测试合同，不是已证实缺陷。
- `src/w2/monitoring/readiness.py` 是状态计算器，不是 Provider live-call 入口。

### 架构清单与当前整改的关系

当前 GitHub 证据已确认：

- C7 的 broad-exception retry 最迟由 2026-06-23 的 `8e467e65...` 引入；
- C5 最迟在 2026-06-25 的 `5e46a8b...` 中存在；
- C1、C6、C11-A 明确由 2026-07-03 的 `97978194...` 引入；
- C11-B 的当前具体形态来自 2026-07-05 的 `ac17e875...`；
- C9 的根问题最迟在 2026-07-19 的 `d460055b...` 中存在；
- C2/C3/C4、C8、C10 均已确认在 2026-07-22 架构总清单建立时存在。

准确裁决：

```text
ARCHITECTURE_CONVERGENCE_SCOPE_REMAINS_VALID
NO_EVIDENCE_C1_TO_C11_WERE_CREATED_BY_ARCHITECTURE_CONVERGENCE
```

这说明当前工作是补做动态失败、并发、计费一致性和治理视角，不是推翻已经完成的静态架构/权威收敛。T00 完成前，不把“收敛绝对没有引入任何其他缺陷”写成未经全量来源矩阵证明的绝对命题。

## 3. 当前状态

```text
EVAL-02B_END_TO_END = BLOCKED / NOT_VALIDATED
EVAL-03 = NOT_STARTED
PROVIDER = OFF
REAL_CANARY = NOT_AUTHORIZED
PERSISTENT_SCHEDULER = OFF
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
AUTO_MERGE = FORBIDDEN
```

A148 的唯一正确结论：

```text
FAIL_CLOSED_BARRIER = PASS
PROVIDER_EXECUTION = NOT_EXECUTED
END_TO_END_CHAIN = NOT_VALIDATED
RUNTIME_COLLECTION_READINESS = NOT_PROVEN
```

A148 证明挡板有效，不证明链路可用。

## 4. 新增治理事实：自修改 workflow 事件

### 已核实

- Bot commit：

```text
e875050f6bc0286aed389aadfce1e17b2063635a
Author: OpenAI Agent
```

- 它修改了 C9 生产代码和集成测试，并删除触发它的 `agent-c9-patch.yml`。
- 三个已知 agent 分支都从同一个 `e875050f` 派生：

```text
agent/eval-02b-c9-lineup-event-ordering
agent/eval-02b-c9-ci-fix-runner
agent/eval-02b-c9-remediation-runner-2
```

- `agent-dynamic-distribution-diagnostic.yml` 的删除提交已定位：

```text
d041ae2a95a5dbb012c5109846270d2691a3f373
```

- 多个相关 workflow 具备 `contents: write`，会配置 `OpenAI Agent` 并向业务 PR 分支执行 `git push`。

### 治理裁决

- PR #453 不再是实现权威，只保留历史证据。
- C9 必须从可信 main 的本地 clean worktree 正常重写。
- 禁止 cherry-pick bot/workflow 整改提交。
- 禁止再使用 workflow 改写业务分支。
- 完整历史 workflow/run/push/commit 仍必须由 T00-GOV 复现并归零所有未解释项。

## 5. 四个风险家族

### R1 — Default allow / missing authority

安全输入缺失、非法、陈旧或未知时却继续执行。

### R2 — Silent failure / failure downgrade

异常被 `pass`、broad catch、rollback-and-continue、diagnostic-only 或成功退出码隐藏。

### R3 — External side effect / local-state non-atomicity

Provider 可能已计费，但 request ledger、quota、raw、capture 或业务阶段未形成可对账状态。

### R4 — Authority split / concurrency / identity drift

CLI/policy、task key/业务 scope、check/lock、SELECT/INSERT、多个 current authority 之间缺少原子约束。

## 5A. 审计视角登记与门禁映射

完整登记见 [`W2_AUDIT_PERSPECTIVE_REGISTRY.md`](docs/operations/W2_AUDIT_PERSPECTIVE_REGISTRY.md)。

当前视角状态：

| 视角 | 状态 | 关闭门禁 |
|---|---|---|
| 架构、权威、重复路径 | COMPLETE（冻结范围） | 已完成，不重开 |
| 动态失败、缺失、并发、计费一致性 | IN_PROGRESS | Gate A 的 canary 路径必须关闭 |
| workflow/供应链治理 | IN_PROGRESS | 可信 C9 重建前关闭 |
| 数据与数学正确性 | PARTIAL / SELF_REVIEWED_ONLY | canary 验证直接冻结合同；Candidate/Formal 前完成与实现同源测试分离的独立 oracle |
| 时间与时序语义 | PARTIAL | canary 做目标链最小证明；scheduler 前全路径审计 |
| 安全、权限、密钥、日志 | PARTIAL / NOT FULLY AUDITED | Production 前关闭 |
| 恢复与灾备 | NOT_AUDITED / UNVERIFIED | Production 前真实演练 |
| 可观测性 | PARTIAL | 持续 scheduler 前关闭 |
| 性能与资源 | PARTIAL | 持续 scheduler/Production 前关闭 |

一个视角完成不能写成整体完成。已有数学测试多数与实现同源，测试覆盖率不能被扩大解释成独立数学正确性签字。

所有新任务/PR 必须回答：

1. 权威/fallback 是否改变；
2. 外部调用或业务写入失败前后会怎样；
3. 缺失、空、非法、陈旧数据返回什么；
4. 重放、冲突和并发行为；
5. 数学不变量与独立 oracle/golden vector；
6. `capture_at`、as-of、kickoff、timezone、freshness；
7. 权限、凭据和日志脱敏；
8. 机器如何发现失败、如何恢复；
9. 哪个登记视角本应抓到本任务/事故，登记表是否需增长；
10. 实现者和独立 reviewer 分别是谁，是否完成 reviewer 轮换；
11. 若是事故型紧急修复，R1–R4 事后复查是否完成。

`不适用` 必须写理由。该规则用于避免验收继承规格盲区，但不会把完整 Production 审计提前塞进第一次人工前台 canary。

### 视角登记表自扩展

每次事故、异常、canary 失败、staging/production 偏差或新 audit finding，都必须回答：

```text
哪个登记视角本应抓到它？
```

- 已有视角可覆盖：更新该行证据、覆盖边界和遗漏原因；
- 无视角可覆盖：在同一整改中新增视角；
- 未完成映射，不得关闭任务或事故；
- 无独立 reviewer 时只能标记 `SELF_REVIEWED_ONLY` 或 `PARTIAL`。

最低关闭输出：

```text
INCIDENT_PERSPECTIVE_MAPPED = true
NEW_PERSPECTIVE_REQUIRED = true|false
REGISTRY_UPDATED = true
UNMAPPED_PERSPECTIVE = 0
REVIEWER_INDEPENDENT_OF_IMPLEMENTATION = true
```

### 事故型紧急修复的事后复查

事故、hotfix、quota hard-stop 或 security containment 可以先止血，但在 R1–R4 和受影响额外视角完成独立事后复查前，只能标记：

```text
CONTAINED_PENDING_POST_INCIDENT_REVIEW
```

不能标记最终 `CLOSED`。`97978194...` 同时引入 C1、C6、C11-A，是该规则的仓库内证据。

## 6. 核心工程规则

1. **Default deny on missing or unknown.** 缺失、非法、陈旧或不可验证意味着 `BLOCKED`。
2. **Explicit failure after external side effect.** Provider 请求可能到达外部后，任何后续失败都必须持久化、显式冒泡并停止后续调用。
3. **Idempotency must be proven.** 只有命中预期约束、回读现有行并证明全部业务字段一致，冲突才是 no-op。
4. **No silent success.** Required empty、吞异常、无锁、陈旧 quota、未执行任务都不是成功采集。
5. **Canary is evidence-chain acceptance.** 不是进程存活、HTTP 200 或“没有报错”。
6. **No self-modifying workflow.** 业务代码只能通过本地正常编辑、commit、push 和 Draft PR 修改。
7. **Context follows evidence.** `PROJECT_STATE`、本文件和 PR 描述不能领先于代码与 GitHub 事实。
8. **Perspective coverage is explicit.** 任务完成只能声明其已验收视角，不能把局部完整扩大为系统整体完整。
9. **Perspective registry self-expands.** 现实发现无法映射时必须新增视角，不能用静态表制造假完整。
10. **Emergency containment requires post-incident review.** 恢复正常路径不等于事故最终关闭。

## 7. 真实 canary 硬合同

所有增量必须为正：

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

同一 lineage 至少对账：

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
```

任一 required delta 为 0 或 lineage 断裂：

```text
CANARY_FAILED
EVAL_02B_BLOCKED
AUTO_RETRY_FORBIDDEN
```

如果调用前无法合理预期生成完整链路，必须以 Provider calls=0、business writes=0 停止；“这次没数据”不能成为 PASS。

## 8. 当前唯一执行顺序

### Step 1 — GitHub → 本地可信同步

Codex 必须先：

```bash
git remote -v
git fetch --all --prune --tags
git status --porcelain=v1
git rev-parse origin/main
git show -s --format='%H %P %an <%ae> %cn <%ce> %s' origin/main
```

然后从可信 `origin/main` 新建 clean worktree。不得从 PR #453 或任何 `agent/eval-02b-c9-*` 分支开始，不得 merge/rebase/cherry-pick `e875050f`。

### Step 2 — T00-GOV

完整枚举 agent workflow、历史创建/删除 commit、Actions runs、job logs、push 结果和 automation commits。验收：

```text
UNCLASSIFIED_AGENT_WORKFLOWS = 0
UNCLASSIFIED_AGENT_RUNS = 0
UNCLASSIFIED_AUTOMATION_COMMITS = 0
UNEXPLAINED_BRANCH_MUTATIONS = 0
MAIN_CONTAMINATION = false
```

### Step 3 — T00-SAFE

以可重复 AST/机械扫描封闭 R1–R4。每项分类为：

```text
SAFE_DEGRADATION
MUST_FIX_FOR_CANARY
MUST_FIX_FOR_CONTINUOUS
ACCEPTED_WITH_REASON
```

验收要求未分类项为 0，且 canary 路径 MUST_FIX 在准入前为 0。T00 完成时同步更新审计视角登记，不得把未审计视角写成 PASS。

### Step 4 — 从可信 main 重建 C9

逐 hunk 审查 `e875050f` 的行为意图，正常重写，不复制来源不可信代码。打开新的 clean Draft PR；PR #453 最终只能被标为 superseded，不能合并。

### Step 5 — Gate A：一次性前台 canary 阻断项

包括：

- C1 默认拒绝的 Provider ingress；
- C2 短期单次 runtime authorization；
- C3 canonical season/scope；
- C4 显式 persistence 与 DB identity；
- C5 PostgreSQL run reservation/fencing；
- call/quota reservation；
- C6 logical request 状态机；
- C7 uncertain-delivery 禁止自动重试；
- C11 ledger 完整性与 quota evidence；
- C8 endpoint schema/异常空数据；
- canary preflight；
- foreground isolation 与 scheduler `restart: no`；
- 最小 stage/failure 记录；
- migration-head 人工前置；
- canary-path 故障注入；
- hard canary validator；
- 目标链最小时序证明和本次五态/pair 冻结数学合同；
- fake Provider 离线 rehearsal。

### Step 6 — 强制停机与二次验收

Codex 只能提交离线证据，不得创建真实授权或调用 Provider。最终必须输出：

```text
REAL_PROVIDER_CALL_EXECUTED = false
REAL_CANARY_AUTHORIZATION_CREATED = false
AUTO_MERGE_EXECUTED = false
READY_FOR_INDEPENDENT_SECOND_REVIEW = true|false
```

## 9. 持续运行及后续产品门禁（后置但不取消）

### Gate B：持续 scheduler / 多联赛

- 完整自动 saga、补偿和本地重放；
- 通用多 writer evaluation/lineup/supersession 串行化；
- 完整 service/collection/evaluation readiness 与 progress health；
- 自动 migration startup fencing；
- Celery ack/requeue/worker-lost/retry 合同；
- 长任务 lease renewal 与 stale owner；
- 多 competition quota 并发；
- worker/scheduler/broker/Redis 全量故障矩阵；
- 全路径时序语义、cold-pull、资源和背压。

### Gate C：Candidate / Formal / Lock

- EV、五态、结算、CLV、校准的独立 oracle/recalculation；
- 独立 oracle 必须与实现代码、同源测试和原规格分离；
- 数据集、样本选择和时间切分正确性；
- 产品阈值、guardrail 和回滚；
- 每项能力独立授权。

### Gate D：Production

- 备份恢复和灾备；
- 时钟、容量和长期 soak；
- 供应链、权限、密钥与日志暴露；
- 独立安全和运营签字。

EVAL-03 仍需独立启动决定。

## 10. 95% 的可验收含义

不承诺“未来永远没有问题”。可验收的 95% 是：

```text
R1-R4 已被可重复 T00 全量扫描
未分类项为 0
canary 路径 MUST_FIX 为 0
同类风险有 CI 防回归
Gate A 故障注入通过
trusted-base 离线 rehearsal 通过
审计视角登记真实且可由现实事件扩展
UNMAPPED_PERSPECTIVE = 0
独立 reviewer 覆盖和轮换证据完整
所有事故型修复的事后跨视角复查已完成
未审项目没有被误报为 PASS
独立二次验收通过
```

只有达到这些条件，才能给出 `PASS_FOR_HUMAN_CANARY_AUTHORIZATION`；它仍不等于 scheduler、Candidate、Formal、Lock 或 Production 获准。

## 11. 接手检查清单

1. 读本文件、`PROJECT_STATE.yaml`、`NEXT_ACTION.md`、审计视角登记、#454、#455。
2. 从 GitHub 同步并验证 main SHA，不依赖聊天记忆。
3. 保留污染 refs 作为证据，不在 PR #453 原地修复。
4. 先 T00-GOV，再 T00-SAFE，再重建 C9。
5. 不创建可向业务分支 push 的 workflow。
6. 不调用真实 Provider，不启动 scheduler，不合并 PR。
7. 所有结论必须带 exact SHA、CI run、故障注入和可复现输出。
8. 每项完成声明必须写清已覆盖视角和明确未覆盖视角。
9. 每次事故/异常必须完成视角映射；无匹配视角时立即扩展登记表。
10. 事故型紧急修复在 R1–R4 事后独立复查前不得最终关闭。
