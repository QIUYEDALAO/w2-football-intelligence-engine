# W2-LINEUP-FIRST-SEEN 验收记录

## 结论

`LINEUP_FIRST_SEEN_EVENT` 已实现为现有 `raw_payload` append-only 存储中的
`endpoint=lineup_first_seen_event` 事件，不新增表、不执行 migration。事件使用
`provider + provider_fixture_id` 的稳定哈希作为主键，重复观察保持 first-write-wins。

功能默认关闭：`W2_LINEUP_FIRST_SEEN_ENABLED=false`。本任务未部署，未运行采集器，
因此新增 Provider 调用为 `0`，生产写为 `0`。

## 已有本项目数据的实测分布

2026-09-02 对生产权威数据库执行只读查询。口径为：

- `matchday_endpoint_captures.endpoint = 'lineups'`
- `capture_status = 'CAPTURED'`
- `response_count = 2`
- capture 严格早于 kickoff
- 每个 fixture 取最早 capture

结果：

| sample_count | minimum | p50 | p90 | maximum |
|---:|---:|---:|---:|---:|
| 76 | 18.183 分钟 | 28.958 分钟 | 29.467 分钟 | 29.750 分钟 |

该 76 场样本受现有轮询网格删失：`T60_ODDS_LINEUPS → T45_LINEUPS_RETRY →
T30_LINEUPS_RETRY`。它证明这 76 场在 T-45 时首发尚未可得，真实可得时间落在
T-45 与 T-30 之间；精确值受轮询网格限制，无法从历史 capture 得出。`P50=28.958`
不是首发公布时间，不得作为首发发布时间引用。样本只有 76 场，不外推到其他联赛、
赛季或 Provider。

采集器自身的 `minutes_to_kickoff` 不受该删失影响：
`minutes_to_kickoff_observations()` 只读取采集器自己的
`endpoint=lineup_first_seen_event` 事件，且冷启动时立即观察。

## Provider 对账

- 本任务实际 Provider 调用：`0`
- 查询时当日既有 live lineup 调用：`0`
- 最新 quota observation：`2026-09-02T05:30:36.491864Z`
- 最后 `daily_remaining`：`7259`
- 查询生产数据库为只读；没有启动采集器，也没有人工 Provider probe。

## 轮询与保护

- 冷启动没有固定 T-minus 档位；样本不足时立即作探索性首次观察。
- 达到最小本地样本后，使用本项目事件分布的 P90 安排首次观察。
- 未出首发时，按距离 kickoff 的剩余时间与剩余次数均分退避。
- 每场最多 3 个计划且每个计划最多发 1 次 Provider 请求。
- 每 tick 最多新增 10 个计划，仅选择当前 UTC 比赛日内的未来 fixture。
- 新增 lineup live calls 每天最多 1500；remaining `<1500` fail closed，`1500` 可继续。
- quota authority 缺失时 fail closed。

### 冷启动预算风险

`next_lineup_poll_at()` 在 `completed_poll_count == 0` 且无本地样本时返回当前时间。
若创建计划时距离开赛仍有数小时，该次立即观察会先被消耗，之后只剩两次机会命中
T-45 至 T-30 的窗口。启用后必须持续监控：每场实际轮询次数、首发命中率、以及命中
时的 `minutes_to_kickoff`。本轮仅登记风险，不修改轮询逻辑。

## 重复分支处置

`codex/w2-lineup-first-seen-collection-01`（`4f9cc8c2`）与本分支功能重复，且包含
`0071_lineup_first_seen_event` migration。按本任务 migration=0 约束，本分支不合并、不引用、
不删除该分支；删除或保留其新表方案均待 Owner 明确确认。

## 未接入模型的证据

本分支相对生产基线没有改动：

- `calibrate_lambdas`
- `lineup_strength_adjustment`
- `lineup_ah_adjustment`
- `lineup_totals_adjustment`
- lineup adjustment enabled 标志
- `lineup_numeric_adjustment_*` capability 字段
- `CALIBRATION_VERSION`、模型参数及 calibration ledger

采集事件只由 lineup materialization 写入，scheduler 只生成带独立 policy version
`w2.lineup_first_seen.v1` 的 lineup endpoint 计划。

## Stop-line 对账

| 项目 | 结果 |
|---|---:|
| 生产写 | 0 |
| ledger 写 | 0 |
| migration | 0 |
| 部署 | 0 |
| GitHub 操作 | 0 |
| CALIBRATION_VERSION 改动 | 0 |
| 模型参数改动 | 0 |
| Provider 调用 | 0 |

生产 calibration identity 仍为
`21960a863fd93dcae01ff8804e73fd0ef9d8360e8f2b8073313f226322e5db71`，verdict 仍为
`APPROVED_VALIDATED`。
