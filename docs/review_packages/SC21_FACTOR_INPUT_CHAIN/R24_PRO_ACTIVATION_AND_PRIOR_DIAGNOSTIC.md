# R24 Pro 激活与预测先验诊断

- 状态：`R23_0_PASS / R23_1_PASS / R23_2_PASS / R23_4_DELIVERED`
- Statistics：`FROZEN_AWAITING_OWNER_CONFIRMATION`
- 模型质量：`INSUFFICIENT_SAMPLE`

## R24-1：套餐实测

唯一授权的 `/status` 于 `2026-08-16T16:47:41.418098Z` 成功：

| 字段 | 原始值 |
|---|---|
| subscription.plan | Pro |
| subscription.active | true |
| subscription.end | 2026-09-16T16:10:05Z |
| requests.current | 56 |
| requests.limit_day | 7500 |
| x-ratelimit-requests-limit / remaining | 7500 / 7444 |
| x-ratelimit-limit / remaining | 300 / 299 |

观测已写入 `provider_quota_observations`。调用窗口 provider log `3384 -> 3385`，raw
Statistics 保持 `141`。

## R23-1：五大联赛重新探测

| 联赛 | provider id | 2026 fixture 数 | payload_sha256 | Provider errors |
|---|---:|---:|---|---|
| 英超 | 39 | 380 | `2a47fdccad510b6f73f819d4becd6e126f8276ede9cc2a00830b16a224f14ef2` | [] |
| 法甲 | 61 | 306 | `3a4f8d5785806afddc4d07e135b27149b48c9a2f51b75deed46f5c581274ad52` | [] |
| 德甲 | 78 | 306 | `5b000c1b1b7989117b3b84d25b89220cd5227692d76ca7d26b2273b36c2ac252` | [] |
| 意甲 | 135 | 380 | `db18f71653936e929cd2cfda2cf1c4804dc4661b2a563a501399fcf5fae93f56` | [] |
| 西甲 | 140 | 380 | `da39ae9c3fb6cd611f229082e383d132ad07e0b68d5ebb3f37e846b379921e2e` | [] |

五项响应均为 HTTP 200、Pro 额度头 `7500/300`，均未再出现 Free season access error。
西甲此前确实被 Free 限制，只是没有进入最初四条静态种子；R21 已用三条独立保存响应补证。
Pro 运行态现在同时绕过静态种子与运行时 Free 限制记录，五大行为一致。

Dashboard 只读验收：`2026-08-22` workspace 返回 17 场，其中 5 场英超，包括
Hull City vs Manchester United、Everton vs Crystal Palace。验收时 API 为 READY，
read-model/matchday-card 为 `197/197`。

## R23-2：额度护栏

运行态 GENERAL 按 Provider header 计费，cap `7500`、reserve `1500`；POSTMATCH `20`
保持正交 request-attempt 池。所有 Free 静态限制只在最新权威日限 `<=100` 时生效；非 Free
额度必须同时有观测时刻，否则 fail closed。生效 cap 高于最新 Provider 实测日限时仍拒绝启动。

## R24-4：9 条 Capture 的先验分布

| scope | n | mean HOME | mean DRAW | mean AWAY | 本地历史 HOME / DRAW / AWAY |
|---|---:|---:|---:|---:|---|
| 全部 Capture | 9 | 0.393014 | 0.221611 | 0.385375 | 构成加权约 0.425270 / 0.251416 / 0.323311 |
| 瑞超 | 8 | 0.411840 | 0.218248 | 0.369912 | 0.411765 / 0.274510 / 0.313725（n=51） |
| 中超 | 1 | 0.242403 | 0.248519 | 0.509078 | 0.533333 / 0.066667 / 0.400000（n=15） |

结论：瑞超的平均主胜概率与本地历史主胜率几乎相同，不支持“模型整体系统性压低主胜”的
判断。整体 HOME 比构成加权基准低约 `0.0323`，主要由唯一一场中超 Capture 拉低；中超
基准也只有 15 场，不能据此判定模型偏差。

可能来源仅作为待验证假设：

- 单场中超四字段 xG 使客队 lambda 明显更高；
- 当前 `home_advantage_goals=0.12` 是全局固定项，不是联赛级标定；
- `w2.formal.lambda_baseline_prior.v1` 为全局 calibration，并未证明对中超先验分布充分。

本项不修改模型、lambda、校准版本或阈值。账本仍为 `9/9/6/6`，integrity `0/0`，模型
质量继续标记 `INSUFFICIENT_SAMPLE`。

## 审计边界

R23 dry-run 的 fixtures 清单请求结束后 raw fixtures 为 `225`，raw Statistics 仍为 `141`；
最终只读验收时 Provider log 为 `3462`，最新额度观测为
`2026-08-16T17:23:48.166359Z / 7500 / remaining 7367 / minute 300/286`。
期间自然 Scheduler 继续运行，因此 Provider 全表增量不能全部归因于本任务；人工 dry-run
调用以 5 个 2026 五大 scope、26 个 2024/2025 scope、8 个其余 2026 scope 的固定 manifest
逐项核对。Statistics 调用为 0。
