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
`W2_PROVIDER_DAILY_HARD_CAP=80` 覆盖了代码默认值。本次属于真正 HARD_CAP，
不是 `DAILY_QUOTA_UNKNOWN`，也不是 reserve 算术死锁；“继续等待 headroom”已撤回。

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
