# R17 P0 配额低估与真实额度审计

> **R18 更正：** 本报告第 1、4 项与“三源取最大值”修复已撤回。135 是本地网络尝试数，
> Provider 响应头/quota_usage 的 used=10 才是计费权威。最终合同与恢复证据见
> `R18_QUOTA_AUTHORITY_AND_STAGED_RESTORE_REPORT.md`。

测量窗口：`2026-08-16T00:00:00Z` 至 `2026-08-16T03:46:45.895794Z`  
Provider calls：`0`（本审计）

## 结论

1. `request_count_since()` 原先优先使用新鲜 `quota_usage` 的方向正确；真正缺口是没有 freshness、
   降级状态和三源并列审计。
2. 当前账号仍为 `Free`；最近持久化响应头明确给出日限 `100`，不是高于 100 的套餐。
3. 同窗 135 条 `provider_request_logs` 全部 live/HTTP 200，但 Provider header 只报告 used=10。
   因此第 101 条 HTTP 200 不能单独证明第 101 次是 Provider 计费调用；日志行数与 Provider
   header 用量是两个不同证据面。
4. GENERAL 以新鲜 Provider header/quota_usage 为计费权威；只有权威缺失或过期时才回退到
   `max(run audit, provider ledger)` 并标记 `QUOTA_AUTHORITY_DEGRADED`。预算维持
   `70 / 20 / 10`，未获 Owner 授权不放宽。

## 临时分级停机（已解除）

- `2026-08-16T03:45:33.700638Z` 停止唯一 scheduler；随后 Provider ledger 稳定在 135 条。
- 新运行模式只生成/认领 `POSTMATCH_RESULT` 计划，禁止 initial seed、fixture discovery、odds、
  lineups 与其他赛前 checkpoint。
- 当日剩余 5 条 capture 每场固定 `status + fixtures(id)` 两次；恢复后的新增 POSTMATCH 支取
  上限为 10 次。普通 POSTMATCH 不参与该窗口。
- R18 归位计数口径并完成 discovery→odds→lineups 分步观察后，赛前采集已恢复；POSTMATCH
  capture 优先与预留全程未变。

## Provider 额度原始证据

最近成功 status 响应审计：

| UTC | header | value |
|---|---|---:|
| `2026-08-16T03:30:27.493845Z` | `x-ratelimit-requests-limit` | 100 |
| 同上 | `x-ratelimit-requests-remaining` | 90 |
| 同上 | `x-ratelimit-remaining` | 6 |

现有审计未持久化 `x-ratelimit-limit`，只能恢复分钟 remaining=6；不得推造分钟 limit。
后续响应合同应补存该字段，但本轮不为补证而调用 Provider。

最近可读 status payload 在 `2026-08-15T14:35:26.617819Z` 明确记录
`subscription.plan=Free`、`requests.limit_day=100`。2026-07-07 的 Pro day-1 历史不能覆盖
当前账号事实。

## 同一 UTC 日的请求账本

| UTC 小时 | logs | HTTP 2xx |
|---|---:|---:|
| 00:00 | 45 | 45 |
| 01:00 | 32 | 32 |
| 02:00 | 34 | 34 |
| 03:00 | 24 | 24 |
| 合计 | 135 | 135 |

- 第 100 条：`2026-08-16T02:31:09.175578Z / status / 200`。
- 第 101 条：`2026-08-16T02:31:09.789916Z / fixtures / 200`。
- 两条均为真实网络请求；是否计入 Provider 日费额只能服从 Provider quota header/status，不能
  由 HTTP 200 或本地日志序号反推。

## quota_usage 解释

| endpoint | used | limit | window |
|---|---:|---:|---|
| fixtures | 6 | 100 | `2026-08-16T00:00Z/2026-08-17T00:00Z` |
| odds | 10 | 100 | 同上 |
| status | 10 | 100 | 同上 |

`quota_usage` 按 endpoint 保存响应头推导的 `limit - remaining`，并对各 endpoint 只保留最大值；
大量 fixtures 错误响应没有 quota header，status 头又持续为 100/90，因此该表停在 10。表中
没有 inserted_at/updated_at，不能伪造精确写入时刻；最近可关联观测是
`2026-08-16T03:30:27.493845Z`。

## R18 最终修复

- 新鲜 `quota_usage` 为唯一 Provider 计费权威；缺失/过期时才回退本地两源最大值并显式降级。
- `QUOTA_USAGE_LEDGER_DIVERGENCE` 仅表示本地尝试与计费口径偏差；审计并列保留三源数字。
- migration 0057 持久化分钟 limit/remaining；分钟保护与 429 使用独立告警。
- `API_FOOTBALL_FREE_DAILY_LIMIT=100` 的引入提交为 `674bd806`；提交文档声称来源为响应头，
  但没有记录实测时刻或原始值。本轮补齐 source/observed_at 三元组。

## 历史结论连带复核

- R8 已明确是 W2 自设 cap 阻断、Provider 尚余 19，不改写为 Provider 耗尽。
- R13/R14 的 POSTMATCH 19 次来自 task audit，是 W2 内部请求尝试池，不是 Provider 计费 19；
  capture 优先与预留结论保留，但“Provider 配额耗尽”表述撤回为“内部 attempt pool 自我节流”。
- R11-2 周数只由赛程/xG-ready/lead-time 分布计算，不受本缺陷算术影响。
- Pro 决策包没有以 Free 额度不足作为购买依据；首页补充本事件不构成购买或提额授权。
