# PRO_REOPEN_OWNER_DECISION_PACKET

Status: PRO_ACTIVE_BACKFILL_DRY_RUN_AWAITING_OWNER_CONFIRMATION

Owner 已于 2026-08-16 开通 Pro。本包不授权续费，也不自动授权 Statistics 补仓；
补仓仍等待 Owner 对 R23 dry-run 的明确确认。

> R24 套餐实测：`subscription.plan=Pro`、`active=true`、到期
> `2026-09-16T16:10:05Z`，日/分钟额度头为 `7500/300`。R20 的 Free
> `90/10/20` 方案已经作废；POSTMATCH `20` 继续作为正交 request-attempt cap。

## 成立基础（首页口径）

| 门 | 状态 | 证据边界 |
|---|---|---|
| 门一：永久留存 | PASS | raw Statistics 可全量恢复派生层，restore hash match 为 true。 |
| 门二：Free 闭环 | PASS_PIPELINE_ONLY | 首次以 1 条真实已结算样本满足闭环；当前 6 条。两者都不是样本充分性或模型质量证明。 |
| 门三：候选链独立 | PASS | ModelForecast 不依赖 exact quote 或 Candidate；Candidate/Settlement 账本保持隔离。 |
| 门四：Pro 补仓 dry-run | DRY_RUN_COMPLETE_EXECUTION_NOT_AUTHORIZED | `PRO_BACKFILL_NET_REQUEST_BUDGET.json` 已给出 13 联赛 2024-2026 精确净预算；Statistics 仍冻结，等待 Owner 确认执行。 |

四门当前均有对应证据，但门四只代表 dry-run 交付，不代表补仓已执行、lineage 已验收或
模型质量已验证。不得把 `DRY_RUN_COMPLETE` 呈现为 `BACKFILL_COMPLETE`。

## Free-mode model validation proof

- Terminal: `FREE_MODE_MODEL_VALIDATION_CANARY_PASS`
- MODEL_ELIGIBLE_COUNT: `9`
- MODEL_FORECAST_CAPTURE_COUNT: `9`
- MODEL_FORECAST_SETTLED_COUNT: `6`
- PROBABILITY_METRICS_SAMPLE_COUNT: `6`
- SHADOW_CANDIDATE_COUNT: `40`
- RAW_STATISTICS_RESTORE_HASH_MATCH: `true`
- raw Statistics count/hash: `141 / 7f3fc61fe64ae8b98b71fa1e123847eff3ec712d7aa7f870c6fd7bab34718243`
- rebuilt team_xg_match count/hash: `140 / 325085b337f2977b118cf88b083b5044e3a36e17ffcad0a857909ae311d63e33`
- rebuilt rolling snapshot count/hash: `72 / 937b9a809ed43687e3e9dd12d23da483077c2e00a6c35686d0e1b3697c3dcde8`

## 模型表现口径

- 本次 PASS 证明管道闭环，不证明模型质量。
- 当前概率指标样本量 `n=6`，仍低于 `MIN_BUCKET_SAMPLES_FOR_RATE=30` 与 `SAMPLE_TARGET=200`。
- 首个闭环样本：HOME/DRAW/AWAY `0.331510 / 0.254890 / 0.413600`，真实结果主队 3-0；
  LogLoss `1.104112386514` 高于均匀先验 `ln(3)=1.098612288668`。
- 在达到预注册门槛前，任何模型表现判断统一标记 `INSUFFICIENT_SAMPLE`。

## 预测冻结提前量口径

- Capture 策略为 `FIRST_ELIGIBLE_FREEZE_IMMUTABLE`：首次满足条件即冻结，之后不更新。
- 每条 Capture 与 Outcome 均保留 `lead_time_seconds` 和 `lead_time_bucket`。
- 概率指标只按 `LT_6H / H6_TO_LT_24H / D1_TO_D3 / GT_3D` 分层输出，禁止跨档位
  合并为单一 Brier、LogLoss 或 RPS。
- 当前分层为 `H6_TO_LT_24H=1`、`D1_TO_D3=5`、`LT_6H=0`、`GT_3D=0`；
  所有档位都继续为 `INSUFFICIENT_SAMPLE`。
- 当前已验证线上 release：`268b18c7816c049e756d66ceb20d60e4f5914d73`，schema
  `0058_quota_observation_history`。

## Free 历史容量事实与 Pro 当前预算

以下只描述容量，不构成续费或提额建议。Free 数字是切换前历史，不再是当前运行额度。

- 最近三个完整 UTC 日的 Provider 计费峰值为 `53 / 80 / 81`，实测 Free 日限为 `100`；
  已观测峰值使用率为 `81%`。
- 这些峰值发生在仅瑞超与部分中超具备 xG、仅 9 条 ModelForecastCapture、Statistics
  关闭且未扩大联赛范围的条件下。
- xG 从 `UNDER_SAMPLED` 自然转为 READY 不会新增赛前 Provider 调用；Capture 是本地冻结。
  边际 Provider 成本发生在赛后：现有链路每场 `status + fixtures = 2` 次网络 attempt，
  R19 实测只有 fixtures 推动日计费，因此当前可审计边际为约 `1 billable/场 + 2 attempts/场`。
- 过去四个完整 ISO 周，瑞超与中超总赛程为 `29 + 27 = 56` 场，即 `14.00 场/周`；
  当前 xG-ready 为 `29 + 2 = 31` 场，即 `7.75 场/周`。若中超现有赛程在不新增
  Statistics 的前提下全部自然转为 READY，平均结果需求由约 `1.11 billable/日`、
  `2.21 attempts/日` 增至约 `2.00 billable/日`、`4.00 attempts/日`，增量约
  `0.89 billable/日、1.79 attempts/日`。
- 同一观察窗单日两联赛总赛程峰值为 `8` 场；若当日全部 xG-ready，结果链需
  `16 attempts + 8 billable`，仍低于 POSTMATCH attempt cap `20`。把历史计费峰值 `81`
  与这 8 次全部保守叠加得到 `89`，未触及已批准但尚未生效的 W2 cap `90`；该叠加会
  重复计算峰值日中已有的赛果请求，因此是保守上界，不是预测值。
- 以同样保守叠加法，历史峰值之上新增第 `10` 次 billable 会得到 `91`，首次超过 W2
  cap `90`；新增第 `20` 次会超过 Provider 硬顶 `100`。当前观察到的单日赛程峰值为 8，
  尚未达到这两个触发点。赛程密度或 xG-ready 率变化后必须滚动重算。
- R11 的样本节奏估算已标记 `INVALID_UNDER_CURRENT_CONFIG`；Statistics 冻结期间新增
  Capture 到达率为 0。Pro 已生效，但只有 Owner 确认 R23 补仓且 Statistics 实际解冻后，
  才能重新估算四个 lead-time 档位的 30/200 样本时间。
- R23 dry-run 精确预算：2025 单季净 `4,525`，2024+2025 净 `8,914`，再含 2026
  已完赛为 `10,084`；建议的有界执行为 `5,500 Statistics/day`，预计两个配额日，另留
  一个只读 lineage 验收日。

## Owner 当前待决策

1. 确认按 R23 dry-run 启用 Statistics：`5,500/day`、`60/min`、三批 fail-closed 补仓。
2. 暂不确认：Statistics 保持冻结，Pro 只维持当前 fixtures/odds/lineups/result 链。

Formal、Lock、Production、real money、Round 4、cadence、模型阈值和冻结策略变更仍在本包
范围之外。Statistics 只有在 Owner 对上述第 1 项明确确认后才可执行。
