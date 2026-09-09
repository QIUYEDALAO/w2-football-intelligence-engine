# 近 10 条中六场 LOSS 的逐场根因

证据分级：`CONFIRMED`（冻结证据直接支持）／`INFERENCE`（由代码机制推得）／
`NOT_RECONSTRUCTIBLE`（冻结记录不含，且拒绝倒灌）。

## 全局前提（对六场共同适用）

- `CONFIRMED`：六场全部 `calibration_status = APPROVED_VALIDATED`、`bookmaker_count = 3`、
  `original_state = ANALYSIS_PICK_ACTIVE`。
- `CONFIRMED`：六场全部 `evaluation_policy_version = candidate-eval.v1`，
  因此 `current_cashflow_price_edge` 未持久化（v2 才引入该字段）。
- `NOT_RECONSTRUCTIBLE`：六场的历史因子方向、participants、weights、absent reasons 均不可重建。
  生产 `dynamic_prematch_evaluations` 全表 payload 无任何 factor 字段，分析卡不落盘。
  **不得**用当前分析卡回算历史因子权重。

## C1：四场 Owner 标注的 AH 冲突 LOSS

| 场次 | 选择 | 线 | 赔率 | current_ev | 模型 P(LOSS+HALF_LOSS) | 比分 |
|---|---|---:|---:|---:|---:|---|
| 斯图加特 vs 科隆 | AWAY | 1.25 | 1.87 | +0.36836 | 0.224 | 4-1 |
| 热那亚 vs 科莫 | HOME | 0.75 | 1.92 | +0.170026 | 0.452 | 1-4 |
| 伊普斯维奇 vs 利物浦 | HOME | 1.00 | 2.00 | +0.412193 | 0.196 | 0-2 |
| 埃尔切 vs 皇家社会 | HOME | 0.25 | 1.99 | +0.284388 | 0.290 | 2-3 |

- **因子方向为何与 EV 相反**：`NOT_RECONSTRUCTIBLE`。Owner 标注了方向，但冻结记录没有因子裁决。
- **实际参与因子的方向/原值/标准化值/权重/缺失项**：`NOT_RECONSTRUCTIBLE`，不伪造。
- **current EV 为何仍在 +0.17 ~ +0.41**：`CONFIRMED` + `INFERENCE`。
  EV 由 `current_ev` 冻结值直接确认；其偏高的机制性解释是 `lifecycle.classify_evaluation`
  的状态判定**只看** EV / EV−SE / cashflow edge，链路上没有任何因子输入
  （已由「全表 payload 无 factor 字段」与代码路径共同证实）。
- **五态 LOSS/HALF_LOSS 概率为何偏低**：`CONFIRMED` 数值 + `INFERENCE` 归因。
  四场的输面 0.196–0.452 与全样本校准缺口一致：148 条整体预测 graded 赢面 64.19%、
  实测 42.96%，fixture 聚类 95% CI `[-0.301, -0.124]` 排除 0。属系统性过度自信，非单场偶发。
- **修复后是否会被明确阻断**：`INFERENCE`。若这四场确为 `FACTOR_EV_DIRECTION_CONFLICT`，
  在本次修复后会在经济准入**之前**落 `BLOCKED_BY_FACTOR → BLOCKED_BY_GATE`，不进入正式推荐。
  但因历史因子身份不可重建，**不能断言**它们当时确实带有该裁决码。
- **不允许的推论**：不得把「方向反过来可能盈利」当作证据。对侧赔率不同，且样本 n=5。

## C2：乌迪内斯 vs 拉齐奥（AH 同向 LOSS）

`CONFIRMED`：AH HOME、线 0.0、赔率 1.9、`current_ev = +0.146349`、`ev−se = +0.059996`、
五态 `WIN 0.4602 / PUSH 0.2720 / LOSS 0.2678`、`lineup_input_hash` 存在、
`bookmaker_count = 3`、确认于 T-15m、比分 1-2。

- **有限因子参与**：`NOT_RECONSTRUCTIBLE`（同全局前提）。
- **F5 缺失**：`NOT_RECONSTRUCTIBLE` 于本记录；F5 在生产上普遍为 `INSUFFICIENT_DATA`
  是独立已知事实，但**本场**的因子明细不在冻结记录内。
- **阵容数值贡献为零**：`NOT_RECONSTRUCTIBLE`。仅 `lineup_input_hash` 存活，
  starters/valued/numeric contribution 只存在于未落盘的分析卡。
- **模型/报价年龄**：`CONFIRMED`，`capture_at` 与 `evaluated_at` 已入 manifest（`model_age_seconds`）。
- **五态是否过度自信**：`INFERENCE`。单场无法定论；置于全样本校准缺口下才有意义。
- **结论**：多项共同作用，**不单因归责**。可确认的只有「EV 为正且经济门通过 → 成为候选」，
  以及该候选属于系统性高估赢面的那一批。

## C3：卡利亚里 vs 莱切（TOTALS LOSS）

`CONFIRMED`：TOTALS OVER 2.25、赔率 1.83、`current_ev = +0.275283`、
五态 `WIN 0.6422 / HALF_LOSS 0.2002 / LOSS 0.1576`、**`lineup_input_hash = null`**、
确认于 T-15m、比分 1-0。

- **四字段 xG 与最终 lambda**：`NOT_RECONSTRUCTIBLE`。evaluation payload 存的是
  `model_settlement_distribution` 与 `one_x_two_probabilities`，不含 lambda 或四字段。
- **模型 capture 距开赛**：`CONFIRMED`，`capture_at` 已入 manifest。
- **是否复用数日前的 `FIRST_ELIGIBLE_FREEZE_IMMUTABLE`**：`NOT_RECONSTRUCTIBLE`，
  冻结记录不含该标记。
- **T-15 报价是否搭配过旧模型**：`INFERENCE`，可由 manifest 的 `model_age_seconds` 判断，
  但无阈值合同可据以定性。
- **未确认阵容为何未阻断**：`CONFIRMED` 机制。`classify_evaluation` 的 blocker 链不含
  lineup 完整性；`lineup_input_hash` 为空**不构成**任何门。这与 AH 因子缺口同源：
  证据缺失未被翻译为阻断。
- **五态为何如此自信**：`CONFIRMED` 数值 + `INFERENCE` 归因，同 C2。

## 结论

四场冲突场的因子层面**不可重建**，只能记为 Owner 标注加当前代码机制解释。
六场唯一**可确认**的共同结构性因素是：状态判定链上没有任何因子或阵容完整性输入，
以及全样本层面已由聚类区间证实的赢面高估。
