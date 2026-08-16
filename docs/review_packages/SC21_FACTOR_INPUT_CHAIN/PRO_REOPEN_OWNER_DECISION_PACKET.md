# PRO_REOPEN_OWNER_DECISION_PACKET

Status: OWNER_DECISION_PACKET_INCOMPLETE_GATE4

This packet does not authorize a Pro purchase or renewal. The current decision remains
`NOT_PURCHASED_NOT_RENEWED` until the Owner explicitly changes it.

> R20 容量复核：本包不以“Free 日限不足”作为购买 Pro 的论据。当前账号响应仍为 `Free`，
> `x-ratelimit-requests-limit=100`。Owner 已批准未来采用“Provider 总计费 cap 90 + 不可分配
> buffer 10”，POSTMATCH 20 保持为正交的 request-attempt cap；该调整必须等 R20-2 上线后
> 完整观察一个 UTC 日再实施。当前决定仍是不购买、不续开 Pro。

## 成立基础（首页口径）

| 门 | 状态 | 证据边界 |
|---|---|---|
| 门一：永久留存 | PASS | raw Statistics 可全量恢复派生层，restore hash match 为 true。 |
| 门二：Free 闭环 | PASS_PIPELINE_ONLY | 以 1 条真实已结算样本满足闭环；不是样本充分性或模型质量证明。 |
| 门三：候选链独立 | PASS | ModelForecast 不依赖 exact quote 或 Candidate；Candidate/Settlement 账本保持隔离。 |
| 门四：Pro 补仓 dry-run | NOT_COMPLETED | 仓库与 W2 Vault 均无 `PRO_BACKFILL_NET_REQUEST_BUDGET.json` 或等价已验收 dry-run 产物。 |

本包只有三门有证据，**不得呈现为四门全通**。当前 Owner 决定仍是不购买、不续开 Pro；
门四缺失不构成购买授权，也不得用估算或历史 Pro 证据冒充已完成 dry-run。

## Free-mode model validation proof

- Terminal: `FREE_MODE_MODEL_VALIDATION_CANARY_PASS`
- MODEL_ELIGIBLE_COUNT: `9`
- MODEL_FORECAST_CAPTURE_COUNT: `9`
- MODEL_FORECAST_SETTLED_COUNT: `1`
- PROBABILITY_METRICS_SAMPLE_COUNT: `1`
- SHADOW_CANDIDATE_COUNT: `40`
- RAW_STATISTICS_RESTORE_HASH_MATCH: `true`
- raw Statistics count/hash: `141 / 7f3fc61fe64ae8b98b71fa1e123847eff3ec712d7aa7f870c6fd7bab34718243`
- rebuilt team_xg_match count/hash: `140 / 325085b337f2977b118cf88b083b5044e3a36e17ffcad0a857909ae311d63e33`
- rebuilt rolling snapshot count/hash: `72 / 937b9a809ed43687e3e9dd12d23da483077c2e00a6c35686d0e1b3697c3dcde8`

## 模型表现口径

- 本次 PASS 证明管道闭环，不证明模型质量。
- 概率指标样本量 `n=1`，低于 `MIN_BUCKET_SAMPLES_FOR_RATE=30` 与 `SAMPLE_TARGET=200`。
- 唯一样本：HOME/DRAW/AWAY `0.331510 / 0.254890 / 0.413600`，真实结果主队 3-0；
  LogLoss `1.104112386514` 高于均匀先验 `ln(3)=1.098612288668`。
- 在达到预注册门槛前，任何模型表现判断统一标记 `INSUFFICIENT_SAMPLE`。

## 预测冻结提前量口径

- Capture 策略为 `FIRST_ELIGIBLE_FREEZE_IMMUTABLE`：首次满足条件即冻结，之后不更新。
- 每条 Capture 与 Outcome 均保留 `lead_time_seconds` 和 `lead_time_bucket`。
- 概率指标只按 `LT_6H / H6_TO_LT_24H / D1_TO_D3 / GT_3D` 分层输出，禁止跨档位
  合并为单一 Brier、LogLoss 或 RPS。
- 当前唯一已结算样本属于 `H6_TO_LT_24H`；其他档位无已结算样本，继续为
  `INSUFFICIENT_SAMPLE`。
- 当前已验证线上 release：`f39f2f2529be0be57371e8b0af6be7776d8961a1`，schema
  `0056_floor_model_forecast_lead_time`。

## Free 容量事实与增长感知测算

以下只描述容量，不构成购买、续费或提额建议。

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
- 样本节奏仍采用 R11 的不确定性口径：当前 xG-ready 自然速率约 `7.75 条/周`；
  `LT_6H` 没有有限周数保证，其他 bucket 的 30 条估算不是承诺。配额不参与该周数公式，
  但任何采集暂停都会使实际速度低于估算。

## Owner choices

1. Keep Free mode and continue natural ModelForecast accumulation.
2. Reopen a separately bounded Pro backfill decision using a fresh net-request budget.

Formal, Lock, Production, real money, Round 4, new Statistics calls, cadence changes,
model-threshold changes, and league deletion remain outside this packet.
