# Candidate C · R0 T0 登记与前向排除清单

```text
register_id = W2-CANDIDATE-C-R0-T0-20260925-v1
preregistration_id = W2-CANDIDATE-C-R0-PREREG-20260925-v1
preregistration_sha256 = 13b897871a37011b3647f860b819a9299a76f81d5af00be5eb2acf2142671a0f
T0_utc = 2026-09-25T08:46:32Z
T0_asia_shanghai = 2026-09-25T16:46:32+08:00
T0_definition = R0_PREREGISTRATION_FROZEN_AT
forward_clock_status = NOT_STARTED
forward_clock_started_at = null
validation_sealed_count = 0
test_sealed_count = 0
production_capture_writer = NOT_AUTHORIZED
```

## 1. 登记的效力

T0 精确等于新 R0 预注册的冻结时点，用于锁定“参数和规则在任何拟议前向结果前已写定”的时间证据。**登记 T0 不等于启动前向时钟**：`NEXT_ACTION.md`、`QUANT_PROJECT_STATE.yaml` 的 `TRACK1_FORWARD_CLOCK=NOT_STARTED` 不变。当前没有可计入密封 validation/test 的新样本，也不允许因 T0 已登记而自动开始 fit、结果解盲、采集写入或生产切换。

历史架构清单要求正式前向预测在拟合值、新 calibration identity 与 writer revision 冻结后、赛果访问前由 append-only writer 固化；这些条件现在尚未满足。因此此处的 T0 只是**预注册时间锚**，不能作为已启动的业务开钟回执，也不能替代将来的 writer/identity 冻结证据。

正式开钟必须由 Owner 另行授权并留下不可变 `forward_clock_started_at` 及实现/输入版本身份。开钟时点记作 `T_start`，必须 `T_start≥T0`。从 T0 到 T_start 之间即使产生新的评估，也仅属诊断；**不追认、不回填**到密封 validation/test。若未来采集机制或预注册公式发生变更，则另建 T0 和新 cohort，不能沿用此登记掩盖变更。

## 2. 已知历史排除清单

| 集合 / 条件 | 处置 | 理由 |
|---|---|---|
| schema `w2.dynamic_quote_evaluation.v2`（业务旧模型 v1），或非当前冻结模型身份 | 排除 fit/validation/test；仅留历史对照 | 模型版本污染 |
| 诊断 1,394、历史 PIT 8,659、2026-09-23 两份导出、1,150 行回放及其派生 fixture | 仅准用于既有 TRAIN/诊断；一律排除新 validation/test | 已披露结果与参数来源；不能当独立前向 |
| `candidate-eval.v2` 的 2026-09-25 Gate 2 快照（原始 3,024 行、最新 664 fixture×market；严格技术 eligible 399 行/261 fixtures） | 全部排除新 validation/test | 均为 R0 冻结和正式开钟前的历史诊断，399 不是密封样本数 |
| 任一 `evaluated_at<T0`、`kickoff_utc≤T0` 或评估在 `T_start` 前 | 排除 validation/test；不追认 | 不满足前瞻时钟与无回填要求 |
| 缺 `evaluated_at`、quote/forecast 捕获时间、kickoff 或可验证绑定身份 | 标 `PIT_UNPROVABLE`，排除 fit/validation/test | 无法逐行证明 `captured_at≤evaluated_at<kickoff_utc` |
| forecast 或报价时间倒挂、比赛已开赛、报价跨 capture/fixture | 排除并记录时间/身份错误原因 | PIT 失败或未来信息泄漏 |
| 同 capture、bookmaker、exact line 的 Pinnacle 双侧缺失、AH 反向线/身份错配，或市场反解无解 | 排除 F1 正式计分；保留原因 `FUSION_MARKET_MISSING` / `QUOTE_PAIR_MISMATCH` / `MARKET_TOTAL_INFER_NO_SOLUTION` | 无可执行市场锚；不得假设缺侧赔率 |
| 缺同一评估可追溯的 `lambda_home/lambda_away/rho` 或输入身份 | 排除 Track B 正式计分；记录 `MODEL_PARAMETER_UNPROVABLE` | DC/Skellam 与五态重放不可独立证明；不得代入当前默认值 |
| `BLOCKED_BY_FACTOR` | 留在因子门/PIT 的审计分母；不进入 Track C 展示或候选推荐绩效 | 因子门原语义不变 |
| 无权威 FT 结果或结果来源未绑定 | 暂停结算与指标，记 `RESULT_CAPTURE_UNAVAILABLE`；不得当作输或静默删样本 | 后验结算事实尚不可证明 |

每条排除必须在访问赛果前按预先冻结的条件留原因；一个 fixture 不得因先后检查点或两个 market 进入不同 split。以上顺序用于审计解释，不得按已知结果挑选排除项。对未来时间倒挂、赔率缺侧、模型参数缺失的实际数量，本登记不作猜测。

## 3. 未来纳入条件与划分

只有正式开钟后**新产生并先于赛果固化**的评估才可进入候选资格检查：当前模型身份 `candidate-eval.v2`、schema v3、官方 enabled 联赛、明确 fixture/market/selection/exact line；`evaluated_at≥T_start` 且 `kickoff_utc>T_start`；绑定同评估模型快照与盘口双侧身份；forecast 和赔率各自 `captured_at≤evaluated_at<kickoff_utc`；模型 lambda/rho 可重放；无已披露历史 fixture 身份；五态和为 1 且价格/线合法。`ANALYSIS_PICK_ACTIVE` 和 `NO_EDGE_CURRENT` 是 Track C 展示及候选绩效全集；`BLOCKED_BY_FACTOR` 仅保留审计。完整 FT 到达后才结算，不能以 FT 是否有利决定是否入组。

先在每 fixture×market 内按 `evaluated_at DESC` 固定最新评估，再以 fixture 身份进行 split 归属；排序以 kickoff UTC 升序，同一 kickoff 用 canonical fixture identity 稳定破同序。沿用 v5 的两道密封门槛：首 2,500 eligible fixtures 为 validation，后续 2,500 为 test；不因观察计数、赛果或指标删联赛/方向/档位。正式资格、分母、排除原因和 fixture 清单需在 outcome 访问前生成不可变 manifest，随后独立复算。当前本地文档不生成 manifest，也不启动其采集。

## 4. 关系与待决阻塞

v5 原文（SHA-256 `3640b9a5d8d294161bbfe1273103e7bf4d297e3032162e5f3307c8c10ed9deb5`）保留历史，活动公式由 R0 新预注册覆盖；其前向密封、双市场/双价格、独立验收与失败停止规则继续适用。Gate 2 的 AH DC–Skellam 100 场误差仍 `NOT_ESTIMABLE`，缺 λ/rho 逐笔证据未补，因此 **AH 正式计分未就绪**。Gate 3 的 399 行是技术 PIT/双侧交集，不是 T0 后前向样本。`validation_samples` 历史兼容投影保持原样。

本登记为设计/时间证据；未修改 `NEXT_ACTION.md`、状态机、数据库、Provider、生产代码、迁移或部署。
