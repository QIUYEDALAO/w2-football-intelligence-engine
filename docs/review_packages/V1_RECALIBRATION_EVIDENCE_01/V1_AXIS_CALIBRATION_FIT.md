# V1 AH/TOTALS 轴校准开发验收

决策：`{'AH': 'REJECTED', 'TOTALS': 'REJECTED', 'combined': 'REJECTED'}`。

本结果只使用严格 PIT 开发/rolling-origin OOF；不构成生产授权或盈利证明。

## 全开发集拟合值

- AH: `{'attack_delta_weight': 0.636364, 'defence_delta_weight': 0.450569}`
- TOTALS: `{'attack_total_weight': 0.580538, 'defence_total_weight': 0.438513}`

## OOF

- fixtures: `7159`
- folds improved: `{'AH': 9, 'TOTALS': 10}`
- generic lines improved: `{'AH': 7, 'TOTALS': 3}`
- paired differences: `{'AH_scoreline': {'resamples': 2000, 'seed': 20260901, 'mean': -0.001154622, 'lower_95': -0.002337132, 'upper_95': 4.7387e-05}, 'TOTALS_total': {'resamples': 2000, 'seed': 20260902, 'mean': -0.001898088, 'lower_95': -0.003372656, 'upper_95': -0.000478009}, 'combined_scoreline': {'resamples': 2000, 'seed': 20260903, 'mean': -0.002527423, 'lower_95': -0.004201046, 'upper_95': -0.000799234}}`
- interaction loss fraction: `-0.165062726`

## 冻结门

```json
{
  "AH": {
    "absolute_margin_intercept_le_0_10": true,
    "margin_slope_closer_to_one": true,
    "mean_generic_ah_brier_lower": true,
    "minimum_5_generic_lines_improve": true,
    "minimum_7_folds_improve": true,
    "paired_scoreline_nll_mean_lt_zero": true,
    "paired_scoreline_nll_upper_95_le_zero": false
  },
  "TOTALS": {
    "absolute_mean_total_bias_le_0_10": true,
    "mean_generic_totals_brier_lower": true,
    "minimum_2_generic_lines_improve": true,
    "minimum_7_folds_improve": true,
    "paired_total_nll_mean_lt_zero": true,
    "paired_total_nll_upper_95_le_zero": true,
    "total_slope_closer_to_one": false
  },
  "combined": {
    "ah_axis_passes": false,
    "interaction_loss_fraction_le_0_10": true,
    "paired_scoreline_nll_upper_95_le_zero": true,
    "totals_axis_passes": false
  }
}
```

## 边界

121 注与 259 场市场证据均未由本脚本加载；它们不能选择参数或决定本次通过。
