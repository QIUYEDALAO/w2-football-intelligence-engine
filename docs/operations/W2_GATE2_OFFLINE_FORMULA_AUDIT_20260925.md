# Gate 2 离线公式审计

- 审计分支：`codex/w2-authority-20260916`
- 基线：`ebe027234eff7dabae805ec8c79b1d7d783ed1a0`
- 审计对象：`src/w2/quant_research/track_b_lambda_level_fusion.py`、`track_cd_offline_presentation.py`
- 结论类型：离线审计；未修改生产、迁移、Provider 或线上写路径。

## 逐条对照

| 项目 | 冻结口径 | 当前实现 | 结论 |
|---|---|---|---|
| Track A | ERRATA ④ 关闭，`total_scale=1.0` | `FROZEN_TOTAL_SCALE=1.0`，传入模型 lambda 时乘 1 | 一致 |
| AH 权重 | `w_AH=0.9`，其余市场权重 0.1 | `FROZEN_W_AH=0.9`，无运行时权重参数 | 一致 |
| TOTALS 权重 | `w_TOTALS=0.0`，市场去水为唯一融合概率输入 | `FROZEN_W_TOTALS=0.0`，几何混合保留该值 | 一致 |
| Track C | 展示 `ANALYSIS_PICK_ACTIVE`、`NO_EDGE_CURRENT`；排除 `BLOCKED_BY_FACTOR`；四档边界 0.05/0.02/0 | 常量与 `DISPLAY_STATES`、`_tier` 相同 | 一致 |
| Track D 信号 | 只允许原始 `TOTALS/UNDER` 反转到 OVER；OVER 不反转 | `e.market == TOTALS and e.selection == UNDER` 才追加 `TRACK_D` | 一致 |
| Track D 价格 join | 同 `provider_fixture_id`、capture、bookmaker、exact line 的 OVER | `_reverse_quote` 使用四个键并要求 `TOTALS/OVER` | 一致 |
| Track D 概率 | `clamp(Pinnacle OVER devig + 0.05, .01, .99)` | `_fair_probability` 后加 `FROZEN_FADE_DELTA` 并 clamp | 一致 |
| R0 版本 | `ABS_PROFIT_V2`、2.5%，五态绝对盈亏返水 | Track B `expected_rebate_units` 按五态；Track D 明确 `w2.track_d.binary_abs_profit_v2.v1` | 一致；Track D 是注册的二元近似，不是五态等价 |
| 五态结算 | 完整 `WIN/HALF_WIN/PUSH/HALF_LOSS/LOSS` | `_distribution` 调 canonical settlement，归一化五态 | 一致 |
| TOTAL_INFER_V1 适用边界 | 对**模型已给出的五态分布**反推模型 total：纯 Poisson、`lambda∈[0.5,6.0]`、步长 .005 | `_solve_total_lambda` 是**市场双侧赔率反推市场 total**：`[0.1,10.0]` 连续二分、DC score matrix、模型 delta、`max_goals=12` 截断归一化 | **不同用途，不能直接判违背 TOTAL_INFER_V1**；市场反解的独立版本/误差容限未冻结，需补规格 |
| AH 反解 | v5 描述为 Skellam delta 反解 | `_solve_handicap_delta` 对 DC score matrix 的有效胜率二分 | `rho=0` 且无截断时可视作 Skellam 差分反解；当前 12 球截断与非零 rho 时并非逐字同式，需量化误差 |
| AH 双侧赔率身份 | 同一盘口须 HOME `L` 对 AWAY `-L` | `fuse_lambda_level` 只收 `{HOME: price, AWAY: price}`，不携带两侧 quote line/identity，无法在函数内证实配对 | **证据缺口**；调用前必须校验反向符号和同 capture/bookmaker，不能把同号 HOME/AWAY 错配 |
| 缺市场数据 | 预注册写明缺任一 Pinnacle 侧时可退纯模型并标 `FUSION_MARKET_MISSING` | `present_offline` 缺 Pinnacle 或渠道价时 EV 置 `None`，只展示“不推”，没有纯模型 EV | **行为差异**；当前是更保守的展示降级，需 Owner 明确是否允许 |

## 边界审计结果

- `.25/.75` 的逐点 HALF 状态映射已用独立算例覆盖：总进球 2 对 2.25、总进球 3 对 2.75；AH `-0.25/-0.75` 也覆盖。
- 五态概率可以含零状态；PUSH 返水为 0，半赢/半输按 0.5 暴露计算。
- 非法赔率（`<=1`、NaN、Inf）fail-closed 抛 `ValueError`，不会进入展示。
- 合法但极端赔率会触及当前 `[0.1,10.0]` 反解边界，当前实现不返回残差或“不可达”标记；这与 TOTAL_INFER_V1 的有限 grid 语义不能混同。

## 证据来源与版本

1. 冻结口径：`docs/operations/W2_CANDIDATE_C_RECALIBRATION_PREREGISTRATION_20260923.json`（v5）、`W2_CANDIDATE_C_RECALIBRATION_ERRATA_20260924.md`（④ 关闭 Track A）、`W2_TOTAL_INFER_V1.md`（FROZEN）。
2. R0 设计：`docs/operations/W2_GATE1_R0_R1_DESIGN_FREEZE_20260925.md`，`rebate_formula_version=ABS_PROFIT_V2`。
3. 生产实现未被修改；本次只新增 `tests/unit/test_gate2_fusion_audit.py` 和审计文档。
4. 独立复算与审计边界见 [W2_GATE2_INDEPENDENT_RECALC_20260925.md](W2_GATE2_INDEPENDENT_RECALC_20260925.md)。

## 测试

定向量化、合约与既有 Track 测试：`38 passed`（`.venv/bin/python -m pytest ...`）。
