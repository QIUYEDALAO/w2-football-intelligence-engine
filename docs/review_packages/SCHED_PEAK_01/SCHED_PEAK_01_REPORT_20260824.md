# SCHED-PEAK-01 — 18:30Z 高峰槽根因报告

## 结论

`CHECKPOINT_MISSING` 的具体成因是 **单 worker 串行化，加上任务的 Provider 后处理超过剩余窗口/租约**。生产 worker 明确为 `--concurrency=1`，且该观测发生在截至 2026-08-28T04:37:34Z 的临时 coverage 插桩窗口内。18:30:49Z 调度器一次性成功 claim `14/14` 个 prematch 计划，说明不是没取走，也不是初始 claim 争用；11 个已发出的峰值请求全部 HTTP 200，最大 `355ms`，说明不是 Provider 超时。

巴甲 8-plan 批次排队 `467.645s` 后于 18:38:37Z 开始，8 次 Provider 请求在 18:38:40.507Z 前全部返回，但任务直到 18:47:45.513Z 才结束。最后响应后的本地处理仍占 `545.005s`，最终超过 18:45:00Z 短窗口 `165.513s`，也超过 18:45:49.502Z claim lease `116.011s`。18:45:55Z scheduler 因窗口和 lease 均已过期，把 6 个短窗口计划推进为 MISSED 并清除 token；worker 随后写回才看到 `CHECKPOINT_CLAIM_TOKEN_MISMATCH`。该 mismatch 是过期后的结果，不是最初争用原因。

## 峰值瞬时容量

- 同一 tick prematch due/selected：`14/14`，预计 Provider calls `16`。
- 同 due_at 的全部计划另有 1 个 `POSTMATCH_RESULT`，因此数据库最终状态为 `{"CAPTURED": 4, "FAILED": 1, "MISSED": 9, "PROVIDER_EMPTY": 1}`。
- worker 可用并发：`1`；claim lease：`900s`；从 claim 到 18:45 短窗口结束实际仅 `850.498s`。
- 巴甲任务从 claim 到结束 `1016.011s`；启动时 lease 只剩 `432.355s`，而自身运行 `548.366s`。

| 顺序 | 联赛 | 计划数 | queue s | run s | task 状态 | blocker |
|---:|---|---:|---:|---:|---|---|
| 1 | serie_a | 2 | 35.421 | 218.392 | COMPLETED | - |
| 2 | ligue_1 | 1 | 324.817 | 107.963 | COMPLETED | - |
| 3 | brasileirao_serie_a | 8 | 467.645 | 548.366 | BLOCKED | CHECKPOINT_CLAIM_TOKEN_MISMATCH |
| 4 | la_liga | 1 | 1016.032 | 0.058 | BLOCKED | CHECKPOINT_CLAIM_TOKEN_MISMATCH |
| 5 | primeira_liga | 1 | 1016.110 | 0.066 | BLOCKED | CHECKPOINT_CLAIM_TOKEN_MISMATCH |
| 6 | argentina_primera | 1 | 1016.196 | 0.069 | BLOCKED | CHECKPOINT_CLAIM_TOKEN_MISMATCH |

## 为什么 4 个 CAPTURED 能成功、9 个不能

同 due_at 的 4 个 CAPTURED 不是同质样本：

- 3 个 prematch CAPTURED 全是 `T15_ODDS`，属于最先执行的 Serie A 两场和 Ligue 1 一场；分组顺序在巴甲之前，均在 18:45 前完成。
- 第 4 个是 `POSTMATCH_RESULT`，窗口一直到 `2026-08-25T03:30:00+00:00`，经历 `3` 次 claim 后仍可恢复；它不能证明 15 分钟 prematch 容量充足。
- 9 个 MISSED 按联赛为 `{"argentina_primera": 1, "brasileirao_serie_a": 8}`，按档位为 `{"T-30m_VALIDATION_LOCK": 3, "T30_LINEUPS_RETRY": 3, "T3_ODDS": 2, "T6_ODDS": 1}`。其中巴甲 8 个在同一批次：请求虽已快速返回，但整批在持久化/投影阶段越过窗口；Argentina T6 排在最后，首次启动时 lease 已失效，重领后又因同一 worker 队列延迟越过 19:00。

所以表面上与联赛相关，真正的区分维度是 **claim 后的 competition 分组顺序、单 worker FIFO 占用和窗口长度**，不是巴甲 Provider 慢。

## 四类假设判定

| 假设 | 判定 | 可复现证据 |
|---|---|---|
| claim 争用 | 否 | 单 tick `14/14` 全 claim；9 个 MISSED 的 `attempt_count>=1`；token mismatch 发生在窗口推进清 token 之后 |
| worker 并发不足 | 是 | runtime `--concurrency=1`；前序任务串行占用，巴甲 claim→finish `1016.011s` 超 900s lease |
| Provider 响应超时 | 否 | 峰值绑定请求 `11/11` HTTP 200、error 0、max `355ms`；18:30–18:48 Provider ledger timeout 0 |
| 到期前未被取走 | 否 | scheduler dispatch 中 14 个 plan ID 全部有 claim token/expiry；MISSED 全部至少 attempt 1 |

## 修复选项与代价

1. **临时止血候选：worker concurrency `1 → 2`。** 冻结时间线按 FIFO、并保留观测到的 task/child 切换占用重放，巴甲批次预计在 claim 后 `726.615s` 完成，距短窗口结束尚有 `123.883s`；因此 `2` 只是在 coverage 插桩负载下通过这一次冻结重放的临时值，不是长期容量基线。coverage 于 2026-08-28T04:37:34Z 结束后必须按 SCHED-PEAK-02 重测。代价是多一个 Celery 子进程、额外 DB 连接和近似增加一份 worker 工作集；并行请求还会提高瞬时 Provider burst，必须保留现有 tick hard cap 与 quota guard，并在部署 Gate 复测内存、DB 连接和峰值 Provider burst。
2. **结构性修复：把临场短窗口放到独立 Celery queue/concurrency pool，并按 window_end/fixture 分小批。** 保留 scheduler 的 EDF claim，不改业务档位时间；让 discovery、postmatch、outcome 与长窗口任务不能占掉 T-30/T15 执行槽。代价是多一个 worker 服务/路由规则、更多 task 开销和更复杂的 quota 并发控制。
3. **不建议加长 lease 或改 checkpoint 时间。** lease 变长只会允许窗口外写回，不能恢复正式 T-30 有效性；把业务档位错开会改变推荐语义。若只做“错峰”，应错开非临场后台任务或隔离队列，不动 T-30/T15 的窗口。

本轮只交付诊断和方案：Provider 调用 `0`、生产写入 `0`、部署 `0`。
