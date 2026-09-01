# V1 AH component-share 最终开发验收

决策：`REJECTED`。

同一开发集上的第 4 个且最终 AH 家族；使用 Bonferroni 修正后的 99.375% 上界。
不构成 calibration grant、部署授权、盈利证明或生产有效性证明。

- full fit: `{'home_adjustment': 0.208545, 'attack_adjustment': 0.663475, 'defence_adjustment': -0.112027}`
- OOF fixtures: `7159`
- improved folds/lines: `7/10`, `12/13`
- paired differences: `{'ah_brier_vs_totals_only': {'resamples': 8000, 'seed': 20260921, 'mean': -0.000307681, 'lower_99_375': -0.000690815, 'upper_99_375': 8.0417e-05}, 'scoreline_nll_vs_totals_only': {'resamples': 8000, 'seed': 20260922, 'mean': -0.001017306, 'lower_99_375': -0.002829504, 'upper_99_375': 0.00087991}, 'ah_brier_vs_production_current': {'resamples': 8000, 'seed': 20260923, 'mean': -0.000280491, 'lower_99_375': -0.000666586, 'upper_99_375': 9.4281e-05}, 'scoreline_nll_vs_production_current': {'resamples': 8000, 'seed': 20260924, 'mean': -0.006521069, 'lower_99_375': -0.010021858, 'upper_99_375': -0.003071417}}`
- margin regressions: `{'production_current': {'slope': 1.173055, 'intercept': -0.020455}, 'totals_only': {'slope': 1.173055, 'intercept': -0.020455}, 'candidate': {'slope': 0.995275, 'intercept': 0.009648}}`
- total invariance: lambda `1e-15`, NLL `2e-15`

## 冻结门

```json
{
  "absolute_margin_intercept_le_0_10": true,
  "ah_brier_vs_production_current_upper_99_375_le_zero": false,
  "ah_brier_vs_totals_only_upper_99_375_le_zero": false,
  "component_monotonicity_proven_by_bounds": true,
  "current_share_clamp_count_zero": true,
  "fitted_parameters_inside_bounds": true,
  "lambda_clamp_count_zero": true,
  "margin_slope_closer_to_one": true,
  "minimum_10_lines_improve": true,
  "minimum_7_folds_improve": true,
  "scoreline_nll_vs_production_current_upper_99_375_le_zero": true,
  "scoreline_nll_vs_totals_only_upper_99_375_le_zero": false,
  "total_lambda_max_difference_le_1e_12": true,
  "total_nll_max_difference_le_1e_12": true
}
```

121 注与 259 场市场 artifact 均未加载。失败时停止在该开发集上继续搜索 AH 家族。
