# W2 Baseline Probability Quality Audit

文档状态：`PARTIALLY_COMPLETE`

审计基线：`origin/main@3b7f87db`

证据来源：`docs/review_packages/PHASE_2_5A_FINDINGS_HANDOFF.md`

执行边界：Gate 0A 与 Phase 2.5a 的既有只读证据摘要；本报告未重跑审计、未访问 VPS/Provider、未修改业务代码，也未执行 Phase 2.5b。

## 1. Conclusion Fields

```text
BASELINE_PROVENANCE_IDENTIFIED_NO_FITTING_EVIDENCE
BASELINE_CALIBRATION_DEFICIENCY_EVIDENCED_SINGLE_FOLD
```

这两个字段分别表示：当前 `BASELINE_PRIOR` 参数来源已经识别，但没有拟合代码或拟合证据；既有单折 1X2 对照为校准缺陷提供证据，但不足以确立 AH/OU 五态、跨联赛、跨时间或生产运行态结论。

## 2. Parameter Provenance and Fitting Identity

参数证据来自 `src/w2/strategy/calibration.py` 的历史与全仓符号搜索：

| parameter | current value | introduced | fitting code | direct test pin identified |
|---|---:|---|---|---|
| `home_advantage_goals` | 0.12 | `d4ca41b7`, 2026-06-29 | `false` | `tests/unit/test_simulation_engine.py:163` |
| `elo_gap_weight` | 0.28 | `d4ca41b7`, 2026-06-29 | `false` | none identified in handoff |
| `squad_value_log_weight` | 0.18 | `d4ca41b7`, 2026-06-29 | `false` | none identified in handoff |
| `lineup_adjustment_weight` | 0.08 | `d4ca41b7`, 2026-06-29 | `false` | none identified in handoff |
| `dixon_coles_rho` | 0.0 | `d4ca41b7`, 2026-06-29 | `false` | none identified in handoff |

引入 commit 为 `d4ca41b7`，主题为 `Add simulation-based formal recommendation engine (#96)`；diff 只有 `src/w2/strategy/calibration.py` 与一个测试，没有拟合脚本、标定 evidence、回归、网格搜索或优化器。上述参数此后未改动。`dixon_coles_rho = 0.0` 使默认 tau correction 成为空操作。

完整机器可读记录见 `docs/review_packages/W2_BASELINE_PARAMETER_PROVENANCE.json`。

## 3. Calibration Identity

```text
calibration_version = w2.formal.lambda_baseline_prior.v1
calibration_status  = BASELINE_PRIOR
```

`BASELINE_PRIOR` 的命名与“硬编码、无拟合证据”的实现事实一致。该身份不得与 fitted Understat candidate、Factor V2 candidate 或 EV-SE calibration 混同。

## 4. Model Structure

```text
base_home = (home_xg_for + away_xg_against) / 2
base_away = (away_xg_for + home_xg_against) / 2
total     = clamp(base_home + base_away, 1.35, 4.40)

adjusted_delta = (base_home - base_away)
               + 0.12
               + (elo_home - elo_away) / 400 * 0.28
               + log(value_home / value_away) * 0.18
               + lineup_strength * 0.08

lambda_home = clamp((total + adjusted_delta) / 2, 0.15, 4.25)
lambda_away = clamp((total - adjusted_delta) / 2, 0.15, 4.25)
```

### 待验证结构假设

以下均为可证伪假设，不是已确认缺陷：

1. `total` 默认只由 xG 决定；Elo、身价和首发只改变主客差值。`lineup_totals_adjustment` 在对应门开启时例外。
2. xG、Elo、身价均包含球队强弱信息，直接相加且未做正交化，可能在实力悬殊场次同向叠加并产生过冲。当前证据没有证明该现象实际发生，必须在合法数据与预注册诊断下验证。

## 5. Audit Coverage Matrix

| Phase 2.5 required item | status | evidence boundary |
|---|---|---|
| parameter provenance / fitting identity | `IDENTIFIED` | commit `d4ca41b7`; no fitting code or evidence identified |
| calibration version and status | `IDENTIFIED` | `w2.formal.lambda_baseline_prior.v1` / `BASELINE_PRIOR` |
| lambda and total-goals clipping frequency | `NOT_EXECUTABLE_LOCALLY_REQUIRES_GATE_0B_OR_EXPORT` | local PostgreSQL is empty; no historical prediction/outcome dataset |
| input availability and fail-closed coverage | `NOT_EXECUTABLE_LOCALLY_REQUIRES_GATE_0B_OR_EXPORT` | local fixtures corpus is insufficient for production-like coverage |
| 1X2 LogLoss / Brier / RPS / ECE | `SINGLE_FOLD_ARCHIVED_EVIDENCE_ONLY` | 2026-07-07 Understat validation, N=453 |
| AH/OU five-state NLL / Brier / RPS | `NOT_EXECUTABLE_LOCALLY_REQUIRES_GATE_0B_OR_EXPORT` | archived evidence is 1X2, not AH/OU five-state |
| league and chronological-block stability | `ARCHIVED_ROBUSTNESS_EVIDENCE_EXISTS` | `ROBUST_IMPROVEMENT`, 2026-07-07 archived report; cross-season + four-fold rolling-origin |
| fixture-set digest and row-conservation ledger | `NOT_EXECUTABLE_LOCALLY_REQUIRES_GATE_0B_OR_EXPORT` | archived document reports counts but no Phase 2.5 local export/digest |
| production runtime identity | `NOT_EXECUTABLE_LOCALLY_REQUIRES_GATE_0B_OR_EXPORT` | release, OCI revisions, applied migration and capability runtime are unknown locally |

Gate 0A separately established that the static migration chain has one head, `0051_apply_seven_day_collection_policy`, while the production-applied head remains unknown. The capability manifest statically reports `production_enabled = 0/13`, `isolated_runtime_verified = 0/13`, `staging_canary_passed = 0/13`, and `POLICY_THRESHOLD_UNVALIDATED` for recommendation-related capabilities; these are static facts, not production-runtime verification.

## 6. Existing Single-Fold 1X2 Evidence

Evidence source: `docs/archive/league_whitelist/W2_UNDERSTAT_MODEL_ITERATION_1_20260707.md` from 2026-07-07 / PR #193.

Method boundary:

- five major leagues using free Understat xG;
- fixtures 1,755; xG matched 1,750; eligible walk-forward 1,510;
- chronological split train/validation = 1,057/453;
- lambda and temperature fitted only on train;
- target fixture's own xG excluded.

Validation metrics, N=453:

| model | log_loss | Brier | RPS | ECE |
|---|---:|---:|---:|---:|
| uniform | 1.098612 | 0.666667 | 0.240250 | 0.086093 |
| Elo-only | 1.028208 | 0.617209 | 0.220493 | 0.080288 |
| **baseline prior（生产）** | **1.005268** | 0.600625 | 0.213034 | **0.114102** |
| fitted raw | 0.970488 | 0.577814 | 0.202277 | 0.048973 |
| fitted + temperature | 0.969900 | 0.577688 | 0.202153 | 0.041136 |

生产 `BASELINE_PRIOR` 具备判别力——其 log_loss `1.005268` 优于 uniform 的 `1.098612`；但其校准度 ECE `0.114102` 劣于 uniform 的 `0.086093` 与 Elo-only 的 `0.080288`，是该对照表中最差。这是典型的“有判别力但过度自信”特征。

单折 fitted + temperature 相对 baseline prior 的 log_loss 为 `-0.035368`、ECE 为 `-0.072966`。`-0.035368` 保留为历史记录；稳健性报告明确将该单折结果自述为乐观值，不应用作主效应量。

主效应量采用滚动 origin 四折稳健值：mean delta log_loss `-0.026376` nats，sd `0.009400`，4/4 折均优于 baseline prior 与 Elo-only。跨季双向 delta log_loss 为 `-0.024113` 与 `-0.032057`。研究中拟合出的 temperature `0.88` 从未进入 `src/w2/strategy/calibration.py`，本报告不授权将其写入生产路径。

稳健性报告还给出：train 2,236 / validation 959 的 fitted + temperature train/validation gap 为 log_loss `+0.008477`、Brier `+0.007031`、RPS `+0.008246`、ECE `+0.022574`；报告判定无明显过拟合。

滚动 origin 四折如下：

| fold | train | validation | fitted LL | prior LL | delta log_loss |
|---:|---:|---:|---:|---:|---:|
| 1 | 1,437 | 479 | 0.976957 | 1.017201 | -0.040244 |
| 2 | 1,757 | 479 | 0.985057 | 1.012744 | -0.027687 |
| 3 | 2,076 | 479 | 0.996999 | 1.018464 | -0.021465 |
| 4 | 2,396 | 479 | 1.000485 | 1.016593 | -0.016108 |

### 待验证时间趋势假设

拟合模型的四折优势从 `-0.0402` 单调收缩至 `-0.0161`，幅度约衰减 60%；同期 baseline prior 四折约为 `1.0172 / 1.0127 / 1.0185 / 1.0166`，没有相同的单调恶化。因此，“后期验证窗口对所有模型都更难”不足以单独解释该趋势，一个待验证解释是拟合模型在后期窗口特异地丢失优势。

这只是警告信号，不是结论：只有 4 个点，训练集彼此嵌套，验证窗口相邻，折间观测不独立。必须在新的预注册 robustness 设计中验证，不得据此修改模型或生产路径。

## 7. Identifiability Limits

本节的 `BASELINE_CALIBRATION_DEFICIENCY_EVIDENCED_SINGLE_FOLD` 结论字段严格限于：

```text
single fold
N = 453
1X2 only
five major leagues using Understat xG only
```

它不是 AH/OU 五态指标。后续 robustness workorder 位于 `docs/league_whitelist/W2_UNDERSTAT_MODEL_ITERATION_1_ROBUSTNESS_WORKORDER.md`，验证结论已归档于 `docs/archive/league_whitelist/W2_UNDERSTAT_MODEL_ITERATION_1_ROBUSTNESS_20260707.md`，状态为 `ROBUST_IMPROVEMENT`。该报告通过 train/validation gap、跨季双向和四折 rolling-origin 证明离线 fitted challenger 的改善具有稳健性；这不等于当前生产 baseline 已被确证有缺陷，也不能外推为 AH/OU 五态或 production runtime 结论。

EV 对概率水平是线性的，良好判别力不能替代概率校准；不过单折校准缺陷证据仍不能单独裁定生产参数、阈值或模型身份。

## 8. Relationship to Other Evidence

- Understat fitted candidate 与 temperature `0.88` 是研究身份，不是当前生产 baseline 身份，也没有进入生产路径。其稳健效应量以 rolling-origin 四折均值约 `-0.026376` nats 为准；单折 `-0.035368` 仅作报告自述的乐观历史值。
- Factor V2 的 TRAIN-only temperature `0.928709586` 是另一个 prospective candidate identity；其 Gate 1 因 ECE 恶化保持 FAIL，不能用于证明当前 baseline 有效，也不能覆盖本报告的单折边界。
- Factor V2 的 frozen `N=5500` 和 one-look 只服务其原始 successor 问题，不得借给 Penaltyblog 研究。

### PR #193、接续 commit 与代码可用性

PR #193 创建于 `2026-07-06T19:47Z`，关闭于 `2026-07-07T01:22Z`，未合并且零评论。它因依赖的基分支被删除而关闭；接续 commit `8e82c4b6` 的提交信息明确写明：

```text
replacement for closed #193 after dependent base branch deletion
BASELINE_PRIOR remains online champion
```

`8e82c4b6` 已验证为 `origin/main` 的祖先，稳健性报告于 2026-07-29 经 `daf935fb` 归档进 main。因此这不是工程失败或工作丢失：模型已建立、已验证 `ROBUST_IMPROVEMENT`、代码已落地 main、报告已归档；未发生的是晋级裁决。

复现与实现入口仍在：

```text
scripts/run_w2_free_tier_2024_backtest.py
src/w2/backtest/free_tier_2024.py::_fit_offline_lambda_model
src/w2/backtest/free_tier_2024.py::_fit_temperature
src/w2/backtest/free_tier_2024.py::_cross_season_robustness
src/w2/backtest/free_tier_2024.py::_rolling_origin_robustness
src/w2/backtest/free_tier_2024.py::build_understat_model_robustness_report
```

`runtime/` 下没有缓存数据，重跑需重新获取 Understat 公开数据；本轮没有重跑。`src/w2/strategy/`、`src/w2/prematch/`、`src/w2/domain/` 均无对 `free_tier_2024` 或 `_fit_offline_lambda_model` 的引用。稳健性报告也明确声明 `not production enablement`。

## 9. Phase 2.5b Disposition

本轮不重复执行 Phase 2.5b：本地没有可执行数据，且 2026-07-07 已存在单折 + 稳健性（跨季双向 + 四折 rolling-origin）定量证据。只有当 Owner 要求验证新的时间趋势假设并批准合法新窗口/导出时，才需要继续定量工作。

本报告不申请 Gate 0B，不继续 Phase 1/2，不改变阶段顺序，不修改 `calibration.py` 或任何生产参数。
