# W2 当前 main 分支独立终审报告

**审计基线：** `main@dbc8e1e8aa74a7613fd7121bf6026890c3ee06c6`  
**审计日期：** 2026-07-31  
**最终裁决：** `EVAL-02B = BLOCKED`。当前不得开放真实 Provider、真实 canary、持续 scheduler、Candidate、Formal、Lock 或 Production。

## 一、审计方法与边界

本报告只把以下内容视为证据：

- 审计基线提交中的源代码；
- 数据库模型、唯一约束和 migration；
- staging Compose 等有效部署配置；
- 可以复核的 GitHub merge 事实；
- 测试只作为辅助证据，不把“测试通过”直接等同于运行能力通过。

PR 描述、`PROJECT_STATE.yaml`、`NEXT_ACTION.md`、Runbook 或既有测试中的自我声明，均不能单独证明任务完成。

尚未做到同等深度故障注入的领域包括：备份恢复、时钟漂移、资源耗尽、供应链依赖、凭据与日志暴露、操作系统和数据库账号最小权限。这些领域是“未证明”，不是“已通过”。

## 二、执行摘要

### 已完成

- P0/P1/P2 架构收敛；
- 阶段 A 已合并任务；
- EVAL-01A/B/C、EVAL-02A；
- OPS-01 Runbook 文档；
- EVAL-02B 预注册合同；
- Legacy 35 条永久排除决策；
- EVAL-02B 写侧 Implementation 01–04；
- exact pair 核心合同：以 `capture_at` 划分 Pre/Post，同 provider/bookmaker/market/selection/exact line，五态概率合法，歧义 fail-closed。

### 未完成

- EVAL-02B 真实端到端证据链；
- EVAL-03；
- 真实 Provider 链路验收；
- 持续 scheduler、多联赛并发配额、恢复和长期运行能力。

### A148 的唯一正确结论

```text
FAIL_CLOSED_BARRIER = PASS
PROVIDER_EXECUTION = NOT_EXECUTED
END_TO_END_CHAIN = NOT_VALIDATED
RUNTIME_COLLECTION_READINESS = NOT_PROVEN
EVAL_02B = BLOCKED
```

A148 证明挡板在前置条件冲突时能够阻止执行；它没有证明 Provider 到 exact pair 的链路可用。

## 三、统一工程原则

本轮缺陷反复呈现两个模式：

```text
缺失即放行
异常即静默
```

整改必须统一采用三条不变量：

1. **Default deny on missing or unknown**：安全输入缺失、非法、陈旧或不可验证时，结果必须是 `BLOCKED`。
2. **Explicit failure after external side effect**：Provider 请求可能到达外部系统后，任何后续失败必须持久化、显式冒泡并阻止后续调用。
3. **Idempotency must be proven**：只有命中预期约束、回读既存行并核对业务字段完全一致，冲突才可视为 no-op。

## 四、Critical

### C1. Provider 总熔断与 endpoint allowlist 缺失时 fail-open

**文件：** `src/w2/providers/control.py:47-61`  
**触发：** `W2_PROVIDER_CALLS_DISABLED` 缺失或非法，同时进程可见 API key 且调用方使用 `allow_live=True`。  
**后果：** 熔断被解释为未禁用；allowlist 缺失时默认开放 `status/fixtures/odds/lineups`。  
**复现：** 删除上述环境变量，在具备有效 key 的隔离测试中进入 live transport。  
**必须修复：** 缺失、空值、非法布尔值一律禁用；allowlist 缺失时为空集合；按一次性授权逐 endpoint 开放。  
**可接受风险：** 无。

### C2. 手工及其他 live 入口缺少统一运行时授权

**文件：** `scripts/run_prematch_refresh.py:124-152`、`src/w2/providers/api_football.py`。  
**触发：** 进程具备 shell、key 和数据库环境变量。  
**后果：** `--execute` 不校验 exact Git SHA、competition、policy season、endpoint、persistence、调用上限和授权有效期；状态文件只是文档，不是运行强制面。  
**复现：** 在 transport 条件允许的环境执行 `python scripts/run_prematch_refresh.py --execute`。  
**必须修复：** 在共享 Provider transport 前增加不可伪造、可过期、可撤销的运行授权，绑定上述全部范围和 run ID。  
**可接受风险：** 无。

### C3. CLI `--season` 只改变 task key，不约束真实 policy season

**文件：** `scripts/run_prematch_refresh.py:33,56-63,114-152`、`src/w2/ingestion/future_refresh.py`。  
**触发：** CLI season 与 registry policy season 不一致。  
**后果：** audit/task key 与真实 Provider 参数、数据库写入 season 分裂；改变 CLI season 可制造不同去重 key。  
**复现：** 对 policy season 2026 的 competition 使用 `--season 2099`。  
**必须修复：** 删除该参数，或仅把它作为 assertion；不一致时 Provider 调用和写入必须均为 0。  
**可接受风险：** 无。

### C4. `--execute` 默认使用 DB persistence

**文件：** `scripts/run_prematch_refresh.py:129-131`、`src/w2/ingestion/future_refresh.py:2005-2010`。  
**触发：** 执行命令但未显式指定 persistence。  
**后果：** 人工命令可直接写 raw payload、capture、observation、projection 和 task audit。  
**复现：** 不传 `--persistence` 且不设置覆盖变量。  
**必须修复：** 默认 plan/no-persistence 或隔离 file；DB 写入必须显式选择、核验目标库并携带有效授权。  
**可接受风险：** 无。

### C5. DB 模式在 Redis 缺失时可无锁执行

**文件：** `src/w2/ingestion/future_refresh.py:2000-2041`。  
**触发：** DB persistence、Redis 未配置、两个相同 key 的手工/worker run 并发。  
**后果：** 两个进程都可能通过 `task_key_exists()`，随后因无 Redis 直接 `lock_acquired=True`，造成双调用和并发写入。  
**复现：** 在无 Redis 的隔离环境并发启动两个相同 bucket 的 run。  
**必须修复：** 无锁后端即拒绝；优先采用 DB 原子 reservation 或 advisory lock，并使用 owner/fencing identity。  
**可接受风险：** 无。

### C6. Provider 调用、request ledger 与 quota ledger 不是可对账状态机

**文件：** `src/w2/providers/api_football.py`、`src/w2/providers/ledger.py:55-123`。  
**触发：** 外部请求已完成，但本地 request log 或 quota usage 写入失败。  
**后果：** 外部成本存在，本地 ledger 不完整；request log 与 quota usage 又是两个事务，调用数和 hard cap 可能被低估。  
**复现：** 在成功 HTTP 响应之后注入 ledger commit 失败。  
**纠偏：** HTTP attempts 默认是 1；默认情况下不会因此自动再次购买请求。只有显式设置 attempts≥2 时，广义重试才放大重复计费。结构问题仍然成立。  
**必须修复：** 建立稳定 logical request ID 和 `INTENT -> SENT/UNCERTAIN -> RESPONSE_RECEIVED -> LEDGER_COMPLETE` 状态机；收到响应后的 ledger 错误不得再次触发 HTTP。  
**可接受风险：** 真实 canary 前无。

### C7. uncertain-delivery timeout 在开启重试后不幂等

**文件：** `src/w2/providers/api_football.py`、`src/w2/ingestion/future_refresh.py`。  
**触发：** 请求已到 Provider，但客户端 read timeout，且 attempts≥2。  
**后果：** 同一逻辑请求可能再次购买。  
**复现：** 在服务端接收后注入客户端 timeout。  
**必须修复：** 区分连接建立前失败与 delivery uncertain；后者终止 run，禁止自动 Provider 重试。  
**可接受风险：** 默认 attempts=1 只能降低概率，不能证明正确。

### C8. schema drift 与异常空数据可能被视为正常完成

**文件：** `src/w2/ingestion/future_refresh.py`，尤其 `_future_fixtures()`、市场过滤和 `_diagnostic_code_for_response()`。  
**触发：** Provider schema 变化、权限变化、competition/season 错误、bookmaker 消失或 required lineup 为空。  
**后果：** fixture、market、event 或 pair 为 0，仍可能只有 diagnostic 或无 blocker。  
**复现：** 返回非预期 response 结构或 required endpoint 的空数组。  
**必须修复：** endpoint-specific schema；区分合法空窗口和异常空窗口；真实 canary 增加最低证据断言。  
**可接受风险：** 合法未出首发只能在调用前判定为不满足 canary 前置，不能算 canary PASS。

### C9. lineup materialization 失败及部分完整性冲突被吞掉

**文件：** `src/w2/ingestion/future_refresh.py:1105-1158`、`src/w2/ingestion/future_refresh_repository.py`。  
**触发：** XI 不完整、球员重复、两队不完整、身份冲突或数据库完整性错误。  
**后果：** raw payload 已保存，但 lineup snapshot/event/evaluation/pair 未生成；调用方对 `FutureRefreshPersistenceError` 执行 `pass`，repository 也可能以 0 代替明确冲突。  
**复现：** raw 保存后注入 lineup persistence 失败。  
**必须修复：** 保留 raw evidence，同时设置明确阶段失败和整体 `BLOCKED/PARTIAL_FAILED`；只有证明为同一业务事实的重复才允许 no-op。  
**可接受风险：** 保留 raw payload 可接受，隐藏后续失败不可接受。

### C10. A148 冻结 restart policy 与 staging Compose 仍冲突

**文件：** `infra/compose/compose.staging.yml:229`。  
**触发：** 使用当前 effective Compose 重跑 A148。  
**后果：** scheduler 的 `restart: unless-stopped` 再次与冻结要求 `restart: no` 冲突，演练仍会在 Provider 前停止。  
**复现：** 比对 effective Compose 与演练合同。  
**必须修复：** 提供专用 rehearsal profile/override，并验证最终 effective config 为 `restart: no`。  
**可接受风险：** 无。

### C11. ledger 完整性错误与不完整 quota evidence 可静默失败

#### C11-A. request ledger 无条件吞没 `IntegrityError`

**文件：** `src/w2/providers/ledger.py:72-94`、`src/w2/infrastructure/persistence/ingestion_models.py`。  
**触发：** Provider 外部副作用发生后，request log commit 抛任意 `IntegrityError`。  
**后果：** rollback 后继续，不识别约束、不回读、不核对业务字段、不产生明确失败；真实调用可能没有 ledger。  
**复现：** 注入非幂等的 request-log 完整性失败。  
**必须修复：** 只允许预期唯一冲突进入 duplicate 分支；回读并核对全部字段；其他错误抛专用异常并停止后续调用。

#### C11-B. 有 remaining 但无 limit 时 quota usage 静默不更新

**文件：** `src/w2/providers/ledger.py:95-123`、`src/w2/providers/quota.py`。  
**触发：** 响应提供 `daily_remaining`，但没有 `daily_limit`。  
**后果：** 当前 run 可继续，而 `QuotaUsageModel` 不更新，也没有 diagnostic/metric，request ledger 与 quota ledger 分叉。  
**复现：** 只返回 remaining header。  
**必须修复：** 返回并持久化结构化 ledger 状态和缺失字段；产生 `PROVIDER_QUOTA_EVIDENCE_INCOMPLETE`；当 quota evidence 是安全边界时阻止后续调用。  
**纠偏：** `daily_remaining` 本身缺失时，future refresh 会显式 `DAILY_QUOTA_UNKNOWN`，该情况不是静默成功。  
**可接受风险：** 只有版本化 Provider 合同允许使用配置 limit，且必须记录来源。

## 五、Important

### I1. PR #449 合并后当前状态曾失真

`PROJECT_STATE.yaml` 与 `NEXT_ACTION.md` 仍等待独立回执审查。state v4 将其翻页为 `RUNTIME_SAFETY_AND_CONCURRENCY_REMEDIATION`。

### I2. 合并后状态一致性门禁已退役

`ARCH-GOVERNANCE-01` 历史完成，但专用 post-merge consistency gate 后来被移除。至少应恢复可见告警。

### I3. 单个 frozen artifact 原子，但完整 Provider-to-pair 链不是同一事务

`write_frozen_analysis_artifacts()` 内部共享一个 Session；Provider ledger、raw、capture、lineup、observation、projection 分属多个事务，多 event 又逐个 commit。必须用显式 saga 状态表达和重放规则。

### I4. evaluation、lineup、supersession 存在首写并发竞态

`SELECT previous -> INSERT -> supersession` 没有 fixture/market 锁；lineup 唯一约束也不是 fixture 单一 authoritative event。持续运行前需数据库级串行化和并发测试。

### I5. 跨 run 日配额预检存在竞态

不同 key 可同时读取相同旧 usage 并各自通过。需要原子 quota reservation 或 advisory lock，并用 Provider evidence 与本地 ledger 做保守对账。

### I6. collection readiness 可失败，而顶层 `/ready` 仍为绿色

`readiness.py` 不是 live 入口；问题是 `matchday_intake.ready` 没有参与顶层 status。应拆分 `/live`、service readiness、collection readiness 和 evaluation readiness。

### I7. migration 成功未约束 worker/scheduler 启动

worker 和 scheduler 没有依赖 migration 完成。需建立 schema-head fencing。

### I8. Celery 交付语义依赖框架默认值

acks、worker lost、failure/timeout、autoretry 和 publish retry 没有显式冻结。需写入代码并做 kill test。

### I9. 测试存在 over-mock 与源码字符串断言

需要 PostgreSQL、Redis、worker kill、timeout、schema drift、多 event 部分失败等真实故障注入。

### I10. Cold pull、恢复、时钟、资源、供应链、权限和凭据暴露仍未证明

cold-pull SLO 阻止持续 scheduler；恢复和安全领域未通过前阻止 Production。

## 六、Minor

### M1. `ALREADY_RUNNING` 返回退出码 0

`run_prematch_refresh.py:166` 会让调用方误认为本轮已采集。应输出 `executed=false` 并使用独立退出码。

### M2. pair `exact_line` 使用 float 序列化

目前不是已证实错误，但 Decimal 字符串或 quarter-unit integer 更利于跨实现重现。

### M3. 状态文件曾重新膨胀为任务台账副本

state v4 只保留当前状态和 blockers；历史回执继续由总清单负责。

## 七、已纠正的非问题

### Valid split-line averaging is intentional

`2/2.5 -> 2.25`、`-0/0.5 -> -0.25` 是明确实现并由测试冻结。没有真实 Provider payload 证明输入域包含非法 split line，因此不得把它列为整改阻断项。

### `readiness.py` is not a live-call path

该文件只计算状态，不执行 Provider HTTP。需要修复的是 readiness 聚合语义，而不是隐藏网络入口。

## 八、真实 canary 不可豁免合同

真实 canary 是证据链验收，不是进程存活验收。以下增量必须全部为正：

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

并且必须在同一 lineage 中对账至少以下字段：

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

任何必需增量为 0 或 lineage 断裂：

```text
CANARY = FAILED
EVAL_02B = BLOCKED
AUTO_RETRY = FORBIDDEN
```

如果运行前无法合理预期产生完整证据链，必须在 Provider 调用前终止且成本为 0。“这次没数据”不能成为 canary PASS。

## 九、可接受或有界保留项

- **Legacy 35：** 作为不可变历史事实永久排除；只有找回 exact original raw blob 且 SHA-256 一致，才可重开身份修复子任务。
- **22 包 SCC 与 `schemas`：** 允许作为有 owner 和退出条件的技术债，不允许据此猜测删除。
- **OPS-01 通用 readiness producer：** 可等到新 competition enablement，但届时未补齐就不能称 ready。
- **cold-pull SLO：** 在 C1–C11 全部关闭后，可不阻止一次严格前台 canary；仍阻止持续 scheduler 和 Production。
- **备份恢复与安全审查空缺：** 阻止 Production。

## 十、整改顺序

1. 统一 default-deny runtime authorization 与空 allowlist；
2. competition/season/task identity 强绑定并显式选择 persistence；
3. 原子 task reservation、quota reservation 与 fencing；
4. Provider/ledger 外部副作用状态机；
5. 区分可安全重试和 uncertain delivery；
6. schema、required-empty、lineup、ledger 错误全部显式失败；
7. 提供 `restart: no` 的 rehearsal effective config；
8. 拆分 service/collection/evaluation readiness；
9. migration fencing、Celery 合同和故障注入；
10. 独立复审后才可申请一次真实 canary。

## 十一、最终回答

### 已完成任务是否真的完成？

在冻结实现范围内完成。EVAL-02B 写侧 01–04 为 code-complete，但运行安全仍需整改，端到端未验证。

### EVAL-02B 当前能否开始真实采集？

不能。C1–C11 必须全部关闭并通过独立复审。

### 系统是否具备持续运行条件？

不具备。锁、跨 run quota、readiness、migration fencing、Celery 语义、SLO 与恢复均未闭环。

### 当前必须保持关闭的能力

```text
PROVIDER = OFF
REAL_CANARY = NOT_AUTHORIZED
PERSISTENT_SCHEDULER = OFF
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
```
