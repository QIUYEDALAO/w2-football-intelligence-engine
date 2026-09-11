# V1 严格 PIT 赛果纠偏复核

状态：`FAIL_STOP`。

本报告只支持本地候选实现，不构成生产认证、ledger 授权或部署许可。

## OOF 主结果

- OOF fixtures: `7159`
- 现役净胜球 slope/intercept: `{'slope': 1.173055, 'intercept': -0.020455}`
- 候选净胜球 slope/intercept: `{'slope': 1.028712, 'intercept': 0.022801}`
- paired NLL candidate-current: `{'resamples': 2000, 'seed': 20260901, 'mean': -0.000415741, 'lower_95': -0.001435234, 'upper_95': 0.000619995}`
- 改善 folds: `7/10`
- individual clamp 改变总进球的 OOF fixtures: `0`

## 冻结检查

```json
{
  "at_least_7_of_10_folds_improve": true,
  "candidate_abs_intercept_le_0_10": true,
  "candidate_slope_closer_to_one": true,
  "oof_fixture_count_7159": true,
  "paired_oof_nll_mean_lower": true,
  "paired_oof_nll_upper_95_le_zero": false
}
```

## 市场条件选择偏差

- delta 均值: `{'raw_delta': -0.022628, 'current_model_delta': 0.277372, 'candidate_model_delta': 0.275063, 'market_implied_delta': 0.265444}`
- market delta ~ raw delta: `{'slope': 0.958535, 'intercept': 0.287134}`
- market delta ~ candidate delta: `{'slope': 0.869784, 'intercept': 0.026199}`
- signed HOME fair-minus-market: `{'X': 0.176641, 'Y': 0.005792, 'Z': 0.014479}`
- favorite-conditioned: `{'X': 0.431641, 'Y': 0.37207, 'Z': 0.349609}`

favorite-conditioned 数字使用市场自身决定选边，只作诊断；不得作为迫使模型复制盘口的上线门。

## 1.848 更正

`1.848 [1.758, 1.939]` 没有可执行脚本或不可变逐行 artifact，无法从仓库证据复现。
严格 PIT 现役 scale=1.0 的开发集 slope 以本 artifact 为准；不得继续引用 1.848 为已证事实。

121 注已结算候选仅用于解释冻结概率、赔率、EV 选择与输赢，不进入这里的拟合或验收。
