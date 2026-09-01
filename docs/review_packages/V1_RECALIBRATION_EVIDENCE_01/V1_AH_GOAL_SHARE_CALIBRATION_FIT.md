# V1 AH conditional goal-share 开发验收

决策：`REJECTED`。

严格 PIT / rolling-origin OOF 开发证据；不构成 calibration grant、部署授权、盈利证明或生产有效性证明。

- full fit: `{'share_intercept': -0.004697, 'share_logit_scale': 1.139814}`
- OOF fixtures: `7159`
- improved folds/lines: `7/10`, `11/13`
- paired differences: `{'ah_brier_vs_totals_only': {'resamples': 2000, 'seed': 20260911, 'mean': -0.000179207, 'lower_95': -0.000441851, 'upper_95': 8.0926e-05}, 'scoreline_nll_vs_totals_only': {'resamples': 2000, 'seed': 20260912, 'mean': -0.000377156, 'lower_95': -0.001708239, 'upper_95': 0.000973714}, 'ah_brier_vs_production_current': {'resamples': 2000, 'seed': 20260913, 'mean': -0.000152018, 'lower_95': -0.00041613, 'upper_95': 0.000115516}, 'scoreline_nll_vs_production_current': {'resamples': 2000, 'seed': 20260914, 'mean': -0.005880919, 'lower_95': -0.008480058, 'upper_95': -0.003373375}}`
- margin regressions: `{'production_current': {'slope': 1.173055, 'intercept': -0.020455}, 'totals_only': {'slope': 1.173055, 'intercept': -0.020455}, 'candidate': {'slope': 0.99704, 'intercept': 0.007119}}`
- total invariance: lambda `1e-15`, NLL `2e-15`

## 冻结门

```json
{
  "absolute_margin_intercept_le_0_10": true,
  "ah_brier_vs_production_current_upper_95_le_zero": false,
  "ah_brier_vs_totals_only_upper_95_le_zero": false,
  "fitted_parameters_inside_bounds": true,
  "lambda_clamp_count_zero": true,
  "margin_slope_closer_to_one": true,
  "minimum_10_lines_improve": true,
  "minimum_7_folds_improve": true,
  "scoreline_nll_vs_production_current_upper_95_le_zero": true,
  "scoreline_nll_vs_totals_only_upper_95_le_zero": false,
  "total_lambda_max_difference_le_1e_12": true,
  "total_nll_max_difference_le_1e_12": true
}
```

121 注与 259 场市场 artifact 均未加载，不能选择参数、修改门槛或决定通过。
