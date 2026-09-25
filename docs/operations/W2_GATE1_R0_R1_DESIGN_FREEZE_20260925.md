# Gate 1 设计冻结：R0 返水统一 + R1 追加式证据关联层

- 文档版本：`W2-GATE1-R0-R1-DESIGN-20260925-v1`
- 状态：`DESIGN_FROZEN_OFFLINE_ONLY`
- 适用分支：`codex/w2-authority-20260916`
- 范围：离线公式、单元测试、账本设计；不改生产、不改 migration、不接 Provider、不部署

## 1. R0 冻结语义

### 1.1 唯一版本

活动实现统一使用：

```text
rebate_formula_version = ABS_PROFIT_V2
rebate_rate = 0.025
```

单笔返水为：

```text
rebate_i = 0.025 × |profit_units_i|
```

精确五态下，若赔率为 `o`，期望返水为：

```text
E[rebate] = 0.025 × (
    (o - 1) × (p_win + 0.5 × p_half_win)
    + p_loss + 0.5 × p_half_loss
)
```

`PUSH` 的返水为零。五态现金流使用完整的 `WIN/HALF_WIN/PUSH/HALF_LOSS/LOSS`
分布；档位边界 `0.05 / 0.02 / 0.00` 保持冻结，只允许候选的档位归属因公式变化而迁移。

### 1.2 三处审计

| 表面 | 审计结果 | Gate 1 处理 |
|---|---|---|
| 冻结 v5 预注册 | 原文写的是 `p × odds - 1 + 0.025`，没有独立的 formula version；它是历史冻结文档，不能就地改写 | 标记为 `HISTORICAL_FORMULA_PENDING_NEW_PREREG`；新预注册必须引用本文和 `ABS_PROFIT_V2`，保留 v5 原文与摘要哈希。新预注册冻结前，不能声称三处均已生效统一 |
| `src/w2/domain/profit.py` | 已实现 `REBATE_RATE=0.025`、`REBATE_FORMULA_VERSION=ABS_PROFIT_V2`，按已实现的每笔 `abs(profit_units)` 求和 | 作为实现语义权威；本 Gate 不改生产结算逻辑 |
| `src/w2/quant_research/track_b_lambda_level_fusion.py` 与 `track_cd_offline_presentation.py` | 原先 Track B/Track D 固定加 `0.025`；现改为从同一版本常量计算期望 ABS_PROFIT_V2 返水 | 仅离线量化代码改动；Track D 使用独立的二元近似函数并明确不等价于五态 |

活动代码和测试都从 `w2.domain.profit` 读取版本与费率，禁止运行时传入另一套 rebate 公式。

### 1.2.1 历史 v5 账本的可复算边界

已只读核对桌面 v5 回放账本 SHA-256 为
`f91b3651a49297aa78a177465152d09ab1959c2b6266bfcd8059876e4ff257fc`。
该文件含 257 条 OOS 逐笔行（AH 76、TOTALS 181），但每行只存 `p_final_dir`
单一概率，不含完整五态分布；`pit_proof` 仍为
`UNPROVABLE_MISSING_EVALUATED_AT`。因此**无法从该账本精确重算 Track B 的
ABS_PROFIT_V2 五态 EV 和边界附近档位迁移**。本 Gate 不伪造迁移清单。后续须以
完整五态分布、对应两侧同快照赔率和可证明 PIT 的重新导出为输入；旧账本仅用于
冻结前诊断，不得充当新公式的 validation/test。

### 1.3 Track B 与 Track D

**Track B** 使用完整五态现金流：

```text
EV_B = (o - 1) × (p_win + 0.5 × p_half_win)
       - p_loss - 0.5 × p_half_loss
       + E[rebate]
```

**Track D** 只有 `p_fade` 单一概率，因此使用单独登记的二元近似：

```text
EV_D_APPROX = p_fade × o - 1
              + 0.025 × ((o - 1) × p_fade + (1 - p_fade))
```

近似公式版本为 `w2.track_d.binary_abs_profit_v2.v1`。该近似把非成功状态合并为全损，
不能宣称与 quarter-line 五态现金流一致。若 Track D
未来需要纳入正式五态验收，必须另行提供反转方向的完整五态分布和新预注册，不得在本设计中
隐式替换。

### 1.4 R0 测试证据

覆盖以下状态及独立算例：

- `WIN`：返水 `0.025 × (o-1)`；
- `HALF_WIN`：返水 `0.025 × 0.5 × (o-1)`；
- `PUSH`：返水 `0`；
- `HALF_LOSS`：返水 `0.025 × 0.5`；
- `LOSS`：返水 `0.025`；
- 混合五态分布：独立 oracle 与离线计算一致；
- Track D 二元近似与 Track B 五态结果明确不相等；
- 既有五态和为 1、quarter-line 结算、无 push 标量近似测试继续通过。

测试文件：

- `tests/unit/test_track_b_lambda_level_fusion.py`
- `tests/unit/test_track_cd_offline_presentation.py`
- `tests/unit/test_r0_rebate_formula_contract.py`

本次定向测试结果：`31 passed`。

## 2. R1 追加式证据关联层设计

### 2.1 三层架构

```text
dynamic_prematch_evaluations
        │ evaluation_id / model forecast / evaluated_at
        ▼
recommendation_review_ledger     (append-only evidence events)
        │ immutable review event + settlement observation
        ▼
Dashboard / validation / weekly diagnostics projections
```

`validation_samples` 保留为现有兼容投影，不改其历史行，不取代 R1，也不作为 R1 的追加
事实源。R1 的事件不得通过窗口重算、upsert 或删除来覆盖历史事件。

### 2.2 逻辑表：`recommendation_review_ledger`

本 Gate 只冻结设计，不创建 migration 或表。建议逻辑字段如下：

| 字段组 | 字段 |
|---|---|
| 事件身份 | `review_event_id`、`evaluation_id`、`derived_from_evaluation_id`、`event_type`、`event_version` |
| 决策身份 | `decision_version`、`calibration_identity`、`code_revision`、`params_snapshot_sha256` |
| 市场身份 | `fixture_id`、`market`、`original_selection`、`selection`、`exact_line`、`market_quote_identity`、`channel_quote_identity`、`pinnacle_quote_identity` |
| 候选类型 | `candidate_kind`：`TRACK_B` / `TRACK_D_REVERSE` / `OFFICIAL_RECOMMENDATION` / `NO_EDGE_DISPLAY` / `FACTOR_GATE_BLOCKED` |
| 状态 | `display_state`、`factor_gate_state`、`review_state`、`exclusion_reason` |
| 时间链 | `quote_captured_at`、`evaluated_at`、`kickoff_utc`、`settlement_observed_at` |
| 概率与价格 | 完整五态分布、`predicted_success`、`decimal_odds_channel`、`decimal_odds_pinnacle`、`fair_line`、`ev_raw`、`ev_with_rebate` |
| 结算 | `settlement`、`home_goals`、`away_goals`、`profit_units_channel`、`profit_units_pinnacle`、`rebate_units_channel`、`rebate_units_pinnacle` |
| 版本与哈希 | `rebate_formula_version`、`track_d_approx_formula_version`（仅 Track D）、`serialization_version`、`payload_sha256`、`source_payload_sha256` |
| 审计 | `created_at`、`supersedes_review_event_id`、`write_reason` |

`review_event_id` 由现有 canonical serializer `w2.canonical-json.v2` 对完整身份和证据
摘要计算。不能创建第二套 serializer，也不能用展示字段重新生成历史身份。
`event_type` 取 `EVALUATION_SNAPSHOT` / `DECISION_SNAPSHOT` /
`SETTLEMENT_OBSERVED` / `CORRECTION`。`candidate_kind` 区分信号或官方身份：
同一原评估若先产生 Track B 候选、后进入官方推荐，须写两个相互关联的事件，而不是
覆盖原事件的 `candidate_kind`。Track D 反转候选必须保留原始 UNDER 评估的
`derived_from_evaluation_id`。

### 2.3 不可变规则

1. `review_event_id` 唯一；重复写入必须是完整业务字段相同的幂等 no-op。
2. 赛果补充是新的 `SETTLEMENT_OBSERVED` 事件，不更新原始评估事件。
3. 纠错是新的 superseding event，旧事件保留，不允许 UPDATE/DELETE 覆盖历史。
4. `PIT_UNPROVABLE`、缺反向渠道价和非官方候选必须保留原因，不能静默丢弃。
5. 一个 fixture×market 可以有多个评估事件，但每个官方推荐必须通过明确的
   `derived_from_evaluation_id` 追溯到原评估。

### 2.4 对账口径

先按以下键匹配交集：

```text
fixture_id + market + evaluation_id + candidate_kind + market_quote_identity
```

对交集逐字段比较：

- 五态分布；
- `settlement`；
- channel/Pinnacle 两套盈亏；
- rebate formula version；
- `evaluated_at`、`quote_captured_at`、`kickoff_utc`；
- calibration identity 和参数快照哈希。

交集要求 100% 一致。非交集按原因计数，不判为故障：

- `PIT_UNPROVABLE`；
- `NON_OFFICIAL_CANDIDATE`；
- `REVERSE_CHANNEL_QUOTE_MISSING`；
- `LEGACY_IDENTITY_UNAVAILABLE`；
- `RESULT_CAPTURE_UNAVAILABLE`。

对账报告必须同时给出：总事件数、唯一 fixture 数、交集数、每类差异数、缺失率和未决数。

### 2.5 Gate 3 迁移路径（仅设计）

1. 冻结字段与 canonical identity contract，完成独立 schema review；
2. 使用离线 fixture 构造器写入测试 ledger，验证幂等、追加、supersession 和部分失败；
3. 只读重放现有 `dynamic_prematch_evaluations` 与 `validation_samples`，无法证明 PIT 的历史
   行标记 `LEGACY_IDENTITY_UNAVAILABLE`，不得补造时间；
4. Gate 3 另行授权后才创建 migration、writer 和受控投影任务；上线前先保持 writer 不使能；
5. 使能 shadow writer 后双读对账：R1 ledger 与现有兼容投影并行读取，交集 100% 后才申请读路径切换；
6. 任何 writer 异常都停止后续写入并保留原始证据，不自动重试可能产生重复业务事件。

## 3. Gate 1 结果与边界

- R0：离线 Track B/Track D 公式和单测已统一到 `ABS_PROFIT_V2`；冻结 v5 原文未改，新的
  R0 预注册仍是 F1 前置条件。
- R1：三层架构、身份字段、追加规则、对账口径和迁移路径已设计冻结；未建表、未迁移、未写生产。
- Provider calls：`0`。
- Production DB writes：`0`。
- Migration：`0`。
- Deployment：`0`。
- 生产 V4、推荐、结算、Dashboard：未修改。
