# R23 Pro 补仓 dry-run

- 状态：`AWAITING_OWNER_CONFIRMATION`
- 测量时刻：`2026-08-16T17:23:27Z`
- Statistics 调用：`0`
- Statistics 配置：仍冻结
- Provider 套餐权威：`Pro / 7500 day / 300 minute`

本计划是门四的 dry-run 交付物，不授权执行 Statistics。Owner 确认前，不把
`statistics` 加入采集端点，也不启动任何补仓任务。

## 精确净请求预算

| 范围 | 完场 fixture | 当前缓存命中 | 净 Statistics 请求 |
|---|---:|---:|---:|
| 最近一个完整赛季（2025） | 4,525 | 0 | 4,525 |
| 两个完整赛季（2024+2025） | 8,914 | 0 | 8,914 |
| 2024+2025+2026 已完赛 | 10,218 | 134 | 10,084 |

当前 141 条 raw Statistics 中，134 个 fixture 命中上述 13 联赛范围；其中 70 个
fixture 的两队 Expected Goals 都非空。其余 7 条不是该补仓目标中的有效缓存命中，
因此不得从净预算中扣减。逐联赛、逐赛季 fixture 数、缓存数和 source sha256 见
`PRO_BACKFILL_NET_REQUEST_BUDGET.json`。

## 执行顺序

### 第一个配额日：六个已验证联赛

巴甲、阿甲、MLS、中超、瑞超、挪超已有 2026-07-07 Pro Statistics/xG 实证。

- 全量净请求：`5,292`
- 独立 Statistics 日硬上限建议：`5,500`
- 先执行 fast lane：当前 T+7 球队最近 3 场的去重集合，净 `165` 请求
- fast lane 历史覆盖充分时可支持的 T+7 fixture：`73`
- fast lane 完成并通过 lineage guard 后，继续补齐该批 2024-2026 历史

`5,500` 低于 Pro 日限；结合既有 `1,500` reserve，仍为自然 fixtures、odds、lineups
和结果链保留约 `500` 个非补仓可用计费位。POSTMATCH 的 `20` 是正交 request-attempt
上限，保持不变。

### 第二个配额日：条件性联赛

五大联赛先各取 3 场真实 Statistics，共 `15` 个 pilot；荷甲、葡超同样各取 3 场，
共 `6` 个 pilot。每个联赛只有在真实响应中两队 Expected Goals 非空且 raw/lineage
断言通过后，才进入全量。

- 五大条件性全量：`3,514` 请求；当前 T+7 理论 31 场，其中 24 场已有至少 3 场同联赛历史
- 荷甲/葡超条件性全量：`1,278` 请求；当前 T+7 理论 14 场，其中 12 场已有至少 3 场同联赛历史
- 第二日条件性最大总量：`4,792`
- pilot 已包含在对应全量预算内，不重复计数

升班马历史不足使五大 7 场、葡超 2 场即使完成本计划仍不会立刻 READY；它们应继续
标记 `UNDER_SAMPLED`，不得把跨联赛或猜测历史拼入四字段 xG。

## 速率与 Pro 保留时长

- Statistics 独立日硬上限：建议 `5,500/day`
- Statistics 发送速率：建议不高于 `60/min`，远低于实测 Pro `300/min`
- 条件性最大净量 `10,084`：两个 UTC 配额日可完成
- 建议保留时长：从 Owner 确认执行起 `2 个配额日 + 1 个只读验收日`
- 退回 Free 的最早条件：全部计划 scope 有明确终态、raw/retention/派生层 count/hash
  一致、备份恢复抽检通过、无在途补仓任务

这只是时长测算，不构成续费建议。

## 写入、备份与恢复

每批开始前：

1. 在 VPS `/opt/w2/backups` 生成 PostgreSQL 有界备份，至少覆盖 `raw_payload`、
   `raw_statistics_retention`、`team_xg_match`、`team_xg_rolling_snapshot`、
   `model_forecast_capture`、`model_forecast_outcome`。
2. 生成文件 sha256、表 count/hash manifest，并验证备份可读。
3. 固定本批 fixture id manifest；Provider 请求只能命中该清单。

每个 Statistics 响应必须先永久写入 `raw_payload(endpoint='statistics')`，再写 retention
manifest，之后才允许派生 `team_xg_match` 与 rolling snapshot。每批结束必须证明：

- raw 新增数与成功响应数一致，sha256 可按 fixture 查询；
- 可仅从 raw 重建派生层；
- 重建前后 team_xg_match 与 rolling snapshot count/hash 一致；
- 新增 xG READY fixture 与新增 ModelForecastCapture 分开报告；
- Capture 仍遵守 `FIRST_ELIGIBLE_FREEZE_IMMUTABLE`，不得覆盖既有 9 条。

任一 raw 写入、retention、解析、身份或 hash 断言失败即停止当前批。恢复只从已验证备份或
永久 raw 重建，不删除 raw，不合成 Expected Goals。额度拒绝使用独立
`XG_BACKFILL_QUOTA_EXHAUSTED`，响应存在但 Expected Goals 为空使用
`RESPONSE_WITHOUT_XG`；只有连续真实响应支持时才可判定 Provider 不支持。

## Owner 待决策

确认后才执行以下授权：启用 Statistics、采用 `5,500/day` 与 `60/min` 上限、按上述三批
顺序运行。未确认则 Statistics 保持冻结，账本不会因本 dry-run 自动新增 Capture。
