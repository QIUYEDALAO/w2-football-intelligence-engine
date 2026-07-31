# W2 AI Project Context

> **用途：** 任何 AI 或人接手 W2 时先读本文件。它是“已完成 + 核心规则 + 当前待办”的 AI 汇总，不替代代码、数据库约束、Git history、Actions logs 和独立审查。
>
> 机器状态：[`PROJECT_STATE.yaml`](PROJECT_STATE.yaml)  
> 当前动作：[`NEXT_ACTION.md`](NEXT_ACTION.md)  
> 独立终审：[`docs/operations/W2_INDEPENDENT_FINAL_AUDIT_20260731.md`](docs/operations/W2_INDEPENDENT_FINAL_AUDIT_20260731.md)  
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

- P0/P1/P2 架构收敛完成。
- 阶段 A 已合并任务完成；`ARCH-GOVERNANCE-01` 曾完成，但 post-merge consistency gate 后来退役。
- EVAL-01A、EVAL-01B、EVAL-01C、EVAL-02A 在冻结实现范围内完成。
- OPS-01 Runbook 文档完成；真实运行 enablement 未完成。
- EVAL-02B 预注册合同、Legacy 35 永久排除决策、写侧 Implementation 01–04 完成。
- exact-pair 核心合同已实现：以 `capture_at` 划分 Pre/Post，同 provider/bookmaker/market/selection/exact line，五态概率合法，歧义 fail-closed。
- `2/2.5 -> 2.25` 等合法 split-line 语义是明确实现和测试合同，不是已证实缺陷。
- `src/w2/monitoring/readiness.py` 是状态计算器，不是 Provider live-call 入口。

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

## 6. 核心工程规则

1. **Default deny on missing or unknown.** 缺失、非法、陈旧或不可验证意味着 `BLOCKED`。
2. **Explicit failure after external side effect.** Provider 请求可能到达外部后，任何后续失败都必须持久化、显式冒泡并停止后续调用。
3. **Idempotency must be proven.** 只有命中预期约束、回读现有行并证明全部业务字段一致，冲突才是 no-op。
4. **No silent success.** Required empty、吞异常、无锁、陈旧 quota、未执行任务都不是成功采集。
5. **Canary is evidence-chain acceptance.** 不是进程存活、HTTP 200 或“没有报错”。
6. **No self-modifying workflow.** 业务代码只能通过本地正常编辑、commit、push 和 Draft PR 修改。
7. **Context follows evidence.** `PROJECT_STATE`、本文件和 PR 描述不能领先于代码与 GitHub 事实。

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

验收要求未分类项为 0，且 canary 路径 MUST_FIX 在准入前为 0。

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
- fake Provider 离线 rehearsal。

### Step 6 — 强制停机与二次验收

Codex 只能提交离线证据，不得创建真实授权或调用 Provider。最终必须输出：

```text
REAL_PROVIDER_CALL_EXECUTED = false
REAL_CANARY_AUTHORIZATION_CREATED = false
AUTO_MERGE_EXECUTED = false
READY_FOR_INDEPENDENT_SECOND_REVIEW = true|false
```

## 9. 持续运行前置（Gate B，后置但不取消）

- 完整自动 saga、补偿和本地重放；
- 通用多 writer evaluation/lineup/supersession 串行化；
- 完整 service/collection/evaluation readiness 与 progress health；
- 自动 migration startup fencing；
- Celery ack/requeue/worker-lost/retry 合同；
- 长任务 lease renewal 与 stale owner；
- 多 competition quota 并发；
- worker/scheduler/broker/Redis 全量故障矩阵；
- cold-pull、备份恢复、灾备、时钟、资源、供应链、权限和凭据审计；
- Candidate/Formal/Lock/Production 独立产品审批；
- EVAL-03 独立启动决定。

## 10. 95% 的可验收含义

不承诺“未来永远没有问题”。可验收的 95% 是：

```text
R1-R4 已被可重复 T00 全量扫描
未分类项为 0
canary 路径 MUST_FIX 为 0
同类风险有 CI 防回归
Gate A 故障注入通过
trusted-base 离线 rehearsal 通过
独立二次验收通过
```

只有达到这些条件，才能给出 `PASS_FOR_HUMAN_CANARY_AUTHORIZATION`；它仍不等于 scheduler、Candidate、Formal、Lock 或 Production 获准。

## 11. 接手检查清单

1. 读本文件、`PROJECT_STATE.yaml`、`NEXT_ACTION.md`、#454、#455。
2. 从 GitHub 同步并验证 main SHA，不依赖聊天记忆。
3. 保留污染 refs 作为证据，不在 PR #453 原地修复。
4. 先 T00-GOV，再 T00-SAFE，再重建 C9。
5. 不创建可向业务分支 push 的 workflow。
6. 不调用真实 Provider，不启动 scheduler，不合并 PR。
7. 所有结论必须带 exact SHA、CI run、故障注入和可复现输出。
