# Candidate C · R0 返水与市场身份预注册（活动口径）

```text
preregistration_id = W2-CANDIDATE-C-R0-PREREG-20260925-v1
status = FROZEN_OFFLINE_ONLY
frozen_at_utc = 2026-09-25T08:46:32Z
frozen_at_asia_shanghai = 2026-09-25T16:46:32+08:00
rebate_formula_version = ABS_PROFIT_V2
track_d_approx_formula_version = w2.track_d.binary_abs_profit_v2.v1
market_total_infer_version = w2.market_total_infer.v1
forward_clock = NOT_STARTED
production_writes = 0
deployment = 0
```

## 1. 权威关系与变更边界

本文件是 v5 的**新活动 R0 预注册补充版本**，不是对历史原文的改写。原 `W2_CANDIDATE_C_RECALIBRATION_PREREGISTRATION_20260923.json`（SHA-256 `3640b9a5d8d294161bbfe1273103e7bf4d297e3032162e5f3307c8c10ed9deb5`）及其 ERRATA、`TOTAL_INFER_V1` 均逐字节保留；其历史回放、参数来源和缺陷披露仍可审计。在返水公式、市场 total 反解、AH 配对身份、整数线及缺市场数据规则上，以**本文件**为新活动口径；其他未冲突的 v5+ERRATA 条款继续有效。旧 `EV = p×o−1+0.025` 只可用于解释历史结果，不能用于新档位、fit、validation 或 test。

本文件不授权任何生产推荐、采集、结算、迁移、推送、Provider 或部署变更，也不授予校准版本/identity 的生产使用权。任何权重、档位边界、返水公式、市场反解或 cohort 规则后续变化，必须新预注册、新 identity 和全新前向 cohort，不能在观察结果后改本文件。

## 2. 冻结参数与五态返水

| 参数 | 冻结值 |
|---|---|
| `total_scale` | `1.0`（Track A 已关闭） |
| `w_AH` / `w_TOTALS` | `0.9` / `0.0` |
| `fade_delta` | `+0.05`（仅原始 UNDER → OVER） |
| Track C 档位边界 | 重点 `EV≥0.05`；一般 `[0.02,0.05)`；观察 `[0,0.02)`；负 EV 不推 |
| `rebate_rate` | `0.025`，唯一公式版本 `ABS_PROFIT_V2` |

每注已结算返水为 `rebate_i = 0.025 × |profit_units_i|`。WIN 返净赢、LOSS 返本金、PUSH 返 0、HALF_WIN/HALF_LOSS 返相应半注盈亏绝对值。对同一赔率 `o>1` 的完整五态概率（五项和为 1，容差 `1e-9`）：

```text
E[rebate_B] = 0.025 × [
    (o−1) × (p_WIN + 0.5 p_HALF_WIN)
    + p_LOSS + 0.5 p_HALF_LOSS
]
EV_B = (o−1) × (p_WIN + 0.5 p_HALF_WIN)
       − p_LOSS − 0.5 p_HALF_LOSS + E[rebate_B]
```

Track B 必须用五态完整分布和执行方向的渠道赔率算档位；不得把 `+0.025` 作为固定加数。Track D 保留独立二元近似，不能宣称五态等价：

```text
p_fade = clamp(p_Pinnacle_devig(OVER) + 0.05, 0.01, 0.99)
EV_D_APPROX = p_fade × o − 1
              + 0.025 × [(o−1) × p_fade + (1−p_fade)]
```

`p_Pinnacle_devig` 使用同快照双侧赔率比例法去水；反转方向的渠道 OVER 赔率必须同 fixture、capture、bookmaker、line，fixture join 使用 `provider_fixture_id`。无反向渠道价则 `EV=None`，不得列入重点。Track D 若要改成五态，需重新预注册并提供完整反转方向五态证据。`validation_samples` 的旧兼容口径不因展示档位或反转候选而改变。

## 3. `MARKET_TOTAL_INFER_V1` 冻结规格

该市场赔率反解与已冻结的 **`TOTAL_INFER_V1` 模型五态反推**是不同计算域，必须分别标识。输入为同一 Pinnacle capture、bookmaker、exact line 的 OVER/UNDER 两侧有效 decimal odds；各侧倒数后比例法去水，得到 `target_under`。以纯 Poisson total `λ` 二分反解，区间 `[0.5,6.0]`，`hi−lo≤1e−6` 停止；目标落在端点可达范围外为 `MARKET_TOTAL_INFER_NO_SOLUTION`，保留模型 total 作为显式 fallback，同时 `fusion_ev=None`、不得参与 Track C 档位或推荐。

整数线 `L` 的反解目标为 `P(total<L | total≠L)`，即 `P(UNDER win | not push)`；不可把 push 当作失败或胜利。半球线取 `P(total≤floor(line))`。`.25` 线沿用市场反解的 UNDER 有效胜率 `P(total<floor(line)) + 0.5P(total=floor(line))`，`.75` 线为 `P(total≤floor(line))`；quarter-line 五态结算仍依逐半盘口分别结算。禁止把市场反解结果冒称 `TOTAL_INFER_V1` 的 grid/SSE 结果。

规格冲突须显式保留：冻结的 `W2_TOTAL_INFER_V1.md` 表格把 `.25` 线 UNDER 在整数进球处列为 `HALF_LOSS`，而现有 `src/w2/domain/odds.py` 按拆线结算为 `HALF_WIN`（例如 UNDER 2.25、总进球 2）。本 R0 的市场反解采用实际拆线结算，不修改那份历史冻结文件；`TOTAL_INFER_V1` 自身的更正必须单独立勘误并复核受影响回放，不能由本文件默默代替。

**已知未闭环差异**：v5 的 AH 描述为 Skellam 反解，当前离线实现为 DC 截断矩阵二分。Gate 2 未能从现有落盘证据中恢复同一评估的完整 `lambda_home/lambda_away/rho`，因此 100 场 DC–Skellam 最大/中位误差仍 `NOT_ESTIMABLE`。该差异在获得配对误差与独立复核前是 AH 正式前向验收的阻塞项；不得默认为误差为零或放宽线。

## 4. AH 双侧身份、缺数据与 PIT

AH HOME/AWAY 线须互为相反数（容差 `±0.01`），与评估选边线方向相符。两侧 `provider_fixture_id`、`bookmaker_id`、`capture_id` 必须一致；每侧 market、selection、line、price、observation_id 须与报价行一致。任一项失败为 `QUOTE_PAIR_MISMATCH`，拒绝融合，不从单侧估算另一侧。

缺任一侧市场报价，或市场反解无解：`fusion_ev=None`，只可展示纯模型概率并标注“无市场锚·不参与档位”；不得把纯模型结果悄然计入重点档。Track C 仅展示 `ANALYSIS_PICK_ACTIVE` 与 `NO_EDGE_CURRENT`；`BLOCKED_BY_FACTOR` 保留审计但不展示。

R1 后续补采集必须落盘并绑定 `evaluation_id`、`evaluated_at`、forecast `captured_at`、双侧 quote `captured_at`、`kickoff_utc`、模型 `lambda_home/lambda_away/rho` 及其输入身份。逐行证明：`forecast_captured_at ≤ evaluated_at < kickoff_utc` 且 `quote_captured_at ≤ evaluated_at < kickoff_utc`；任一时间或身份缺失标 `PIT_UNPROVABLE` 并排除出 fit/validation/test，不得以赛果时点、当前快照或事后回填替代。补采集是后续单独授权事项，本文件不改写入路径。

## 5. 样本、检验与停止规则

承接 v5 的 schema `w2.dynamic_quote_evaluation.v3` 与当前模型版本 `candidate-eval.v2`，按 fixture×market 最新评估去重并在 split 层以 fixture 为唯一归属。训练/诊断可保留已披露历史；validation 与 test 仅接收 T0 后、正式启动后新产生且在赛果访问前固化的 eligible fixture，分别密封 `2,500 + 2,500`。市场双侧、PIT、模型参数、FT 赛果和冻结排除原因逐行可审；先报告计数与排除，不提前揭示 validation/test 指标。v5 的 AH/TOTALS 分轨 logloss/Brier/RPS/bias、市场基准、两种价格、分联赛报告和失败即停止规则继续适用；不得根据收益、档位数量或单场赛果事后改样本或边界。

冻结公式的本地验证见 `tests/unit/test_r0_rebate_formula_contract.py`、`tests/unit/test_track_b_lambda_level_fusion.py`、`tests/unit/test_track_cd_offline_presentation.py`、`tests/unit/test_gate2_fusion_audit.py`；这些是实现正确性证据，不是独立前向验收。实际开钟、生产写证据、fit、grant、部署均需各自授权。
