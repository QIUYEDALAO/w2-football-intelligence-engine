# R8 P0 配额死锁与赛果抢救验收

测量截止：`2026-08-15T06:03:04.598938Z`

## 结论

- 精确终态：`FREE_MODE_MODEL_VALIDATION_CANARY_PASS`。
- 最终线上 release：`a0f16d2e06857a39b28e085846fe1db7d5c0a854`。
- 当前决定不变：不开通、不续开 Pro；Formal、Lock、Production、Round 4 均保持关闭。
- 9 条 capture 中只有 fixture `1494244` 已完场；其余 8 条开球时间在 `2026-08-15T11:35:00Z` 至 `2026-08-17T17:00:00Z`，不是 2026-08-14 赛果抢救对象。
- 中超 `1523240` 的 POSTMATCH_RESULT 为 `PLANNED`，不是失败的 `1523235/1523236/1523237` 之一，不标记 `STRUCTURALLY_UNSETTLEABLE_ON_FREE`。

## R8-2 配额定性

02:20 与 03:21 UTC 的四组拒绝审计字段一致：

- `error_code=DAILY_PROVIDER_HARD_CAP_EXCEEDED`
- `quota_guard_mode=HARD_CAP`
- `actual_calls_today=81`
- `planned_calls=2`
- `daily_cap=80`
- `reserve_bucket=0`
- `remaining_quota=19`

因此 `81/100` 表示 Provider 已用 81、剩余 19；不是剩余 81。实际生效的
`W2_PROVIDER_DAILY_HARD_CAP=80` 是 W2 自设保护性上限；阻断发生时 Provider 侧仍有
19 次可用额度，所以不是 Provider 配额耗尽。代码命中的是 W2 的
`DAILY_PROVIDER_HARD_CAP_EXCEEDED / HARD_CAP` 分支，不是 `DAILY_QUOTA_UNKNOWN`，
也不是 reserve 算术死锁；“继续等待 headroom”已撤回。该上限是批次前置检查，
`actual_calls_today=81` 也证明单批次可把实际计数推过 80，不能表述为单次调用级硬保证。

## R8-4 有界抢救

严格使用 Owner 一次性授权，只对已完场 capture fixture `1494244` 发出 1 次 fixtures-by-id 调用：

- Provider ledger：`3107 -> 3108`
- raw fixtures：`161 -> 162`
- raw Statistics：`141 -> 141`
- HTTP/result：`200 / FT / 3-0`
- raw SHA-256：`73675d2a6c9c6fc406e35e788e76f9e0c4c95eb440d53543ae4f6bf0fa686bcd`
- endpoint capture：`e9982f989c5b464616f9aa93cb3f59b5cc22ac1cd625ffecb4adc9f53b3cb8b8`
- ModelForecastOutcome：1 条
- Brier：`0.682903900178`
- LogLoss：`1.104112386514`
- RPS：`0.308951688937`

Result 写入后，原组合结算进程因内存被系统终止；已停止重跑组合路径，改用最小零 Provider
`settle_model_forecasts` 完成 Outcome。1494244 的 POSTMATCH plan 已绑定上述真实 capture 并转为 `CAPTURED`。

## R8-3 结构性修复

- POSTMATCH_RESULT 不再受通用 80-call 门槛和响应头 reserve 门槛阻断。
- 独立硬上限 `W2_POSTMATCH_RESULT_DAILY_HARD_CAP=20` 已在 worker/scheduler 显式生效；超过时输出 `RESULT_QUOTA_EXHAUSTED` 并保留 DUE/RETRY_PENDING。
- POSTMATCH_RESULT 在同批计划认领中优先于 odds/lineups。
- 结果窗口过期输出 `RESULT_WINDOW_MISSED`，不再归入等待完场。
- 每批只认领一个 POSTMATCH_RESULT，并以 fixture id 请求 fixtures；不再使用 Free 模式实测失败的 league/season/date 请求。
- 本次事故不是 `DAILY_QUOTA_UNKNOWN`，条件式快照初始化修复不适用；POSTMATCH 专属路径也不依赖 Provider remaining 快照才能首次放行。

第一次结构 release 放行后，自然 Scheduler 在 `05:56:12.561089Z` 至
`05:56:21.677404Z` 运行四个旧 DUE 批次，共新增 status 4、fixtures 4；raw Statistics 不变。
真实响应证明 league/season/date fixtures 参数返回 `PROVIDER_FIXTURES_ERRORS`，由此触发最终 fixture-id 修复。
最终 release 从 `2026-08-15T06:01:00Z` 至 `06:03:04.598938Z` 的 Provider 时间窗计数为 0。

## 最终守卫

- Provider logs：`3116`
- raw fixtures：`166`
- raw Statistics：`141`
- ModelForecastCapture：`9`
- ModelForecastOutcome：`1`
- 账本 invalid capture/outcome：`0 / 0`
- `RAW_STATISTICS_RESTORE_HASH_MATCH=true`
- API/Web exact SHA：`a0f16d2e06857a39b28e085846fe1db7d5c0a854`
- schema：`0054_model_forecast_validation_ledger` MATCH
- API/worker/scheduler/web：healthy

本报告不授权任何新的 Provider 调用或阶段推进。

## R17 口径复核（2026-08-16）

- R8 当时的阻断仍应表述为 W2 自设 cap 命中，而非 Provider 侧真实耗尽；原文已按此口径记录。
- `provider_request_logs` 是单调网络请求账本，Provider header `limit-used` 是账号计费视图；两者
  不可互相覆盖。R18 最终合同以新鲜 Provider header/quota_usage 为计费权威；仅在权威缺失或
  过期时回退本地两源最大值并标记 DEGRADED。
- POSTMATCH 的 `actual_calls_today` 是任务审计请求尝试数；R13/R14 的 19 次说明 W2 内部
  attempt pool 被占用，不是 Provider 计费 19 或 Provider 日额度耗尽。

## R9 口径补充

- 本次 PASS 只证明真实预测冻结、权威赛果、结算和概率指标的管道闭环，不证明模型有效。
- 当前概率指标样本量为 `n=1`，低于 `MIN_BUCKET_SAMPLES_FOR_RATE=30` 与
  `SAMPLE_TARGET=200`；所有模型表现结论均为 `INSUFFICIENT_SAMPLE`。
- 唯一样本 LogLoss `1.104112386514` 高于均匀先验 `ln(3)=1.098612288668`；差值约
  `0.005500`。这一条样本既不能证明模型有效，也不能证明模型无效。
- 9 条 capture 的逐场终态与 9 次 Provider 调用明细见
  `R9_CANARY_PASS_INDEPENDENT_REVIEW.md`。
