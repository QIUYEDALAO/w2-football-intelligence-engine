# V1 市场轴校准开发验收

决策：`{'AH': 'REJECTED', 'TOTALS': 'PASS_DEVELOPMENT', 'combined': 'REJECTED'}`。

严格 PIT/rolling-origin OOF 开发证据；不构成生产授权、盈利证明或 ledger grant。

## 拟合值

- AH: `{'home_intercept': 0.343251, 'attack_weight': 0.691718, 'defence_weight': 0.476429}`
- TOTALS: `{'total_intercept': 0.885958, 'total_scale': 0.701191}`

## OOF

- fixtures: `7159`
- folds improved: `{'AH': 7, 'TOTALS': 8}`
- lines improved: `{'AH': 12, 'TOTALS': 7}`
- paired differences: `{'AH_brier': {'resamples': 2000, 'seed': 20260901, 'mean': -0.000327871, 'lower_95': -0.000688026, 'upper_95': 4.4216e-05}, 'AH_scoreline_nll': {'resamples': 2000, 'seed': 20260902, 'mean': 0.00021821, 'lower_95': -0.001718258, 'upper_95': 0.002243618}, 'TOTALS_brier': {'resamples': 2000, 'seed': 20260903, 'mean': -0.001005456, 'lower_95': -0.001476438, 'upper_95': -0.000518059}, 'TOTALS_nll': {'resamples': 2000, 'seed': 20260904, 'mean': -0.004414417, 'lower_95': -0.006527817, 'upper_95': -0.002243568}, 'combined_scoreline_nll': {'resamples': 2000, 'seed': 20260905, 'mean': -0.005388671, 'lower_95': -0.00824612, 'upper_95': -0.002493556}}`

## 冻结门

```json
{
  "AH": {
    "absolute_margin_intercept_le_0_10": true,
    "brier_upper_95_le_zero": false,
    "margin_slope_closer_to_one": true,
    "minimum_10_lines_improve": true,
    "minimum_7_folds_improve": true,
    "scoreline_nll_noninferiority_upper_95_le_0_001": false
  },
  "TOTALS": {
    "absolute_mean_total_bias_le_0_10": true,
    "brier_upper_95_le_zero": true,
    "minimum_5_lines_improve": true,
    "minimum_7_folds_improve": true,
    "total_nll_upper_95_le_zero": true,
    "total_slope_closer_to_one": true
  },
  "combined": {
    "ah_passes": false,
    "scoreline_nll_upper_95_le_zero": true,
    "totals_passes": true
  }
}
```

121 注与 259 场市场 artifact 均未加载，不能选择参数或决定通过。
