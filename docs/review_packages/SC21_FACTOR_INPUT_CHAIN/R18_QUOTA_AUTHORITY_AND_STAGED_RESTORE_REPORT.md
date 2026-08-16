# R18 配额权威归位与分步恢复报告

测量窗口：`2026-08-16T00:00:00Z` 至 `2026-08-16T05:34:37Z`
最终代码：`a4cea10aabe0e92dcc749d6f96d0161d7e06945b`
schema：`0057_provider_quota_observation`

## 结论

- R17 的“三源取最大值”规则已撤回。GENERAL 额度判定以新鲜的 Provider 响应头/
  `quota_usage` 为权威；本地 provider ledger 与 run audit 只用于偏差告警和权威降级时的
  保守回退。
- `2026-08-16T03:30:27.493845Z` 的 Provider 计费事实为 used `10`、limit `100`、
  remaining `90`。同窗 135 条本地日志是网络尝试数，不是 135 次 Provider 计费。
- 赛前采集已按 discovery、odds、lineups 三阶段恢复；POSTMATCH capture 优先级与预留未变，
  Statistics 始终未开放。
- 分钟级 limit/remaining 已持久化，分钟保护与 HTTP 429 使用独立状态，不再与日额度耗尽混写。

## R18-2：135 的零调用定性

原 135 行全部为当日新建的真实网络尝试，不是旧行 `requested_at` 被 upsert 刷新：

- `provider_request_hash()` 的输入包含本次 `requested_at`，同参数的不同尝试产生不同 hash。
- 135 行 requested_at、completed_at 均落在 2026-08-16 UTC，completed_at NULL 为 0。
- 原分布为 fixtures 65、status 65、odds 5；HTTP 均为 200。
- 多数 Free 访问错误响应没有日额度 header；因此 HTTP 200/本地日志行不能反推计费次数。

方案评估：

- A（增加 billable/cached 列）：Provider 未逐请求返回可靠 billable 标志，新增列仍需推断，
  schema 与历史回填风险高。
- B（唯一键加入时间维度）：现有 hash 已含 requested_at，实际上已经做到每次尝试独立成行，
  不能解决计费语义。
- C（Provider quota header 为计费权威，本地日志仅诊断）：本轮采用，改动最小且与实测一致。

POSTMATCH 的旧 `billable=19` 同样不是 Provider 响应头计费数，而是 task audit 中的
POSTMATCH 请求尝试数。20 次池保留为 W2 内部 attempt budget，用于保护 capture，不再称为
Provider billable pool。

## R18-1：计数合同

- 新鲜权威：`known_count = billable_from_provider`。
- `quota_usage` 缺失或超过 7200 秒未更新：
  `known_count = max(local_ledger_count, run_audit_count)`，并输出
  `QUOTA_AUTHORITY_DEGRADED`；降级态继续服从保守 W2 预算。
- `QUOTA_USAGE_LEDGER_DIVERGENCE` 只说明本地尝试口径与 Provider 计费口径偏离，不提高
  Provider 已用量。
- 每次预检审计同时输出 `billable_from_provider / local_ledger_count / run_audit_count`、
  authority 状态、观测时刻和 age。

## R18-4：分钟级保护

- migration 0057 为 `quota_usage` 增加 `observed_at / burst_limit / burst_remaining`。
- 新响应已真实持久化 `burst_limit=10 / burst_remaining=9`。
- 预检同时检查最近 60 秒本地请求尝试和 Provider burst remaining；不足时输出
  `PROVIDER_MINUTE_RATE_LIMIT_PROTECTED`。
- Provider 返回 429 时输出 `PROVIDER_MINUTE_RATE_LIMIT_EXCEEDED`，不复用日额度告警。

## R18-3：分步恢复证据

| 阶段 | 运行配置 | 自然 tick 结果 | Provider 日计费 | 分钟余额 |
|---|---|---|---:|---:|
| discovery | discovery on；POSTMATCH-only；status,fixtures | fixtures(T+1) 1 次 | 10→11 | 9/10 |
| odds | POSTMATCH-only off；增加 odds | 本 tick 无到期 odds；discovery 1 次 | 11→12 | 9/10 |
| lineups | 增加 lineups | 本 tick 无到期 lineups；无 Provider 调用 | 12→12 | 9/10 |

首次 discovery 曾轮转到 T+7 并得到 Free 日期访问错误；当即重新关闭 discovery。最小修复
将 `W2_FIXTURE_DISCOVERY_MAX_OFFSET_DAYS` 限制为 1 后才重新恢复，cadence 仍为 300 秒。
最终持久化配置为：

- `W2_FIXTURE_DISCOVERY_ENABLED=true`
- `W2_POSTMATCH_ONLY_ENABLED=false`
- `W2_PROVIDER_ENDPOINT_ALLOWLIST=status,fixtures,odds,lineups`
- Statistics、injuries、H2H 与 xG backfill 均未启用。

## 历史口径更正

- R8：used=81/limit=100 是 Provider 响应头计费事实；阻断来自 W2 自设 GENERAL cap=80，
  Provider 当时仍余 19。不是 Provider 耗尽。
- R13/R14：`19 + planned 2 > POSTMATCH cap 20` 是 W2 内部 attempt pool 耗尽/自我节流，
  不是 Provider 日额度耗尽。capture 优先与预留仍有必要，因为它保护的是内部有限尝试预算。
- R17：以本地 135 替代 Provider used=10 的 fail closed 属过度保守，造成赛前采集不必要停机；
  本报告完成恢复。

## 最终守卫

- `/ready=READY`；`/v1/version` exact release `a4cea10a...`；schema 0057 MATCH。
- workspace Web/API HTTP 均为 200。
- Provider logs `3265`；raw fixtures `183`；raw Statistics `141`。
- ModelForecast eligible/capture/settled/metrics `9/9/3/3`；ledger invalid `0/0`；
  `RAW_STATISTICS_RESTORE_HASH_MATCH=true`。
- 全套测试：`2658 passed / 14 skipped`；Ruff PASS。
- 本轮不授权 Pro、Statistics、模型阈值、联赛、cadence、冻结策略或阶段推进。
