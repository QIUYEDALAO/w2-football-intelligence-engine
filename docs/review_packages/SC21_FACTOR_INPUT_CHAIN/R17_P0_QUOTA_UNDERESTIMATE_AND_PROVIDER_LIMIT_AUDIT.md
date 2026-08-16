# R17 P0 配额低估与真实额度审计

测量窗口：`2026-08-16T00:00:00Z` 至 `2026-08-16T03:46:45.895794Z`  
Provider calls：`0`（本审计）

## 结论

1. `request_count_since()` 在 `quota_usage` 非空时覆盖其余两源，是已确认代码缺陷。
2. 当前账号仍为 `Free`；最近持久化响应头明确给出日限 `100`，不是高于 100 的套餐。
3. 同窗 135 条 `provider_request_logs` 全部 live/HTTP 200，但 Provider header 只报告 used=10。
   因此第 101 条 HTTP 200 不能单独证明第 101 次是 Provider 计费调用；日志行数与 Provider
   header 用量是两个不同证据面。
4. W2 仍按最保守口径 fail closed：`quota_usage / run audit / provider ledger` 取最大值。
   这会有意高估，不允许低估；预算维持 `70 / 20 / 10`，未获 Owner 授权不放宽。

## 分级停机

- `2026-08-16T03:45:33.700638Z` 停止唯一 scheduler；随后 Provider ledger 稳定在 135 条。
- 新运行模式只生成/认领 `POSTMATCH_RESULT` 计划，禁止 initial seed、fixture discovery、odds、
  lineups 与其他赛前 checkpoint。
- 当日剩余 5 条 capture 每场固定 `status + fixtures(id)` 两次；恢复后的新增 POSTMATCH 支取
  上限为 10 次。普通 POSTMATCH 不参与该窗口。

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

## 修复与同型检查

- `request_count_since()` 改为三源最大值，任何来源不得降低已知值。
- 最大值与 quota_usage 差值大于 5 时输出 `QUOTA_USAGE_LEDGER_DIVERGENCE`，审计同时保留三源
  数字与 delta。
- 全仓同型搜索只命中本函数；未发现第二处“单一 quota source 覆盖多源最大值”的实现。
- `API_FOOTBALL_FREE_DAILY_LIMIT=100` 的引入提交为 `674bd806`；提交文档声称来源为响应头，
  但没有记录实测时刻或原始值。本轮补齐 source/observed_at 三元组。

## 历史结论连带复核

- R8 已明确是 W2 自设 cap 阻断、Provider 尚余 19，不改写为 Provider 耗尽。
- R13/R14 的 POSTMATCH 19 次子池归属来自 task audit，不依赖通用 quota_usage，结论保留。
- R11-2 周数只由赛程/xG-ready/lead-time 分布计算，不受本缺陷算术影响。
- Pro 决策包没有以 Free 额度不足作为购买依据；首页补充本事件不构成购买或提额授权。
