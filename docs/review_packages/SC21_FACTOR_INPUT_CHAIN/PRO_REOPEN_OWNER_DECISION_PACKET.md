# PRO_REOPEN_OWNER_DECISION_PACKET

Status: OWNER_DECISION_PACKET_INCOMPLETE_GATE4

This packet does not authorize a Pro purchase or renewal. The current decision remains
`NOT_PURCHASED_NOT_RENEWED` until the Owner explicitly changes it.

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

## Owner choices

1. Keep Free mode and continue natural ModelForecast accumulation.
2. Reopen a separately bounded Pro backfill decision using a fresh net-request budget.

Formal, Lock, Production, real money, Round 4, new Statistics calls, cadence changes,
model-threshold changes, and league deletion remain outside this packet.
