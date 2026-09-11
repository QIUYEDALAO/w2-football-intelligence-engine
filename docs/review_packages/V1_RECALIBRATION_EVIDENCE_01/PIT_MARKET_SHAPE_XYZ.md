# V1 严格 PIT 斜率候选市场复核

> **后续解释已取代本报告的上线门含义：** favorite-conditioned 指标先用市场
> 自身决定强弱侧，再衡量模型与市场差异，会条件选择市场噪声。以下数字保留为
> 开发诊断，不再作为 outcome-validity 或部署门；最终裁决见
> `STRICT_PIT_OUTCOME_CORRECTION.md`。

> 结论边界：259 场均为开发数据；本报告不能证明生产有效性或 EV 已完全修复。

- A2 strict-PIT SHA-256: `d7c6eaf9ab39a62265438d661cc2f606cf0c7d4dfd4b5ac5fb8a41999c95266f`
- frozen market audit SHA-256: `47ede4e8c1e40fbf4217d2adcd713141f0cb410de0f62430ffefdb68b25b2698`
- 只复用旧审计冻结的盘口、赔率、机构和 captured_at；旧模型输出全部丢弃。
- 去水实际实现：`PROPORTIONAL`。
- X=`0.12/1.0`，Y=`0.30/1.0`，Z=`0.30/1.102038`。

## 强制计数

```json
{
  "fixture_count": 259,
  "snapshot_count": 178,
  "rebuild_count": 81,
  "track_count": 777,
  "clamp_affected_count": 0,
  "all_model_market_gaps_nonempty": true,
  "at_least_one_model_market_gap_nonzero": true
}
```

## 分组结果

| cohort | track | AH强队缺口mean | 弱队edge mean | 弱队edge>5% | 强队edge mean | TOTALS差mean |
|---|---|---:|---:|---:|---:|---:|
| all_259 (259) | X | 0.431641 | 0.130240 | 159/256 (0.621094) | -0.278125 | -0.068359 |
| all_259 (259) | Y | 0.372070 | 0.105046 | 146/256 (0.570312) | -0.253294 | -0.068359 |
| all_259 (259) | Z | 0.349609 | 0.095440 | 142/256 (0.554688) | -0.243710 | -0.068359 |
| snapshot_178 (178) | X | 0.431818 | 0.129975 | 111/176 (0.630682) | -0.278943 | -0.059659 |
| snapshot_178 (178) | Y | 0.377841 | 0.107325 | 100/176 (0.568182) | -0.256743 | -0.059659 |
| snapshot_178 (178) | Z | 0.352273 | 0.096784 | 98/176 (0.556818) | -0.246220 | -0.059659 |
| rebuild_81 (81) | X | 0.431250 | 0.130821 | 48/80 (0.600000) | -0.276327 | -0.087500 |
| rebuild_81 (81) | Y | 0.359375 | 0.100032 | 46/80 (0.575000) | -0.245706 | -0.087500 |
| rebuild_81 (81) | Z | 0.343750 | 0.092482 | 44/80 (0.550000) | -0.238187 | -0.087500 |
| clamp_affected_0 (0) | X | - | - | 0/0 (-) | - | - |
| clamp_affected_0 (0) | Y | - | - | 0/0 (-) | - | - |
| clamp_affected_0 (0) | Z | - | - | 0/0 (-) | - | - |
| excluding_clamp_259 (259) | X | 0.431641 | 0.130240 | 159/256 (0.621094) | -0.278125 | -0.068359 |
| excluding_clamp_259 (259) | Y | 0.372070 | 0.105046 | 146/256 (0.570312) | -0.253294 | -0.068359 |
| excluding_clamp_259 (259) | Z | 0.349609 | 0.095440 | 142/256 (0.554688) | -0.243710 | -0.068359 |

## 六项开发上线门

```json
{
  "values": {
    "a_underdog_edge_mean": 0.09544,
    "b_underdog_edge_gt_0_05_fraction": 0.554688,
    "c_abs_favorite_shortfall_mean": 0.349609,
    "d_favorite_shortfall_mean": 0.349609,
    "d_favorite_edge_mean": -0.24371,
    "e_home_favorite_abs_worsening": -0.010607000000000033,
    "e_away_favorite_abs_worsening": -0.04395600000000005,
    "f_totals_mean_change": 0.0
  },
  "checks": {
    "a_underdog_edge_mean_le_0_05": false,
    "b_underdog_fraction_le_0_35": false,
    "c_abs_favorite_shortfall_mean_le_0_25": false,
    "d_no_shortfall_overshoot_le_minus_0_25": true,
    "d_favorite_edge_mean_le_0_05": true,
    "e_home_favorite_worsening_le_0_10": true,
    "e_away_favorite_worsening_le_0_10": true,
    "f_totals_mean_change_le_0_02": true
  },
  "all_pass": false
}
```

结论：`FAIL`，不得实现、授权或部署该候选。

## 独立复核

```bash
check_dir=$(mktemp -d /private/tmp/v1-pit-market-shape.XXXXXX)
PYTHONPATH=src:. .venv/bin/python scripts/audit_v1_pit_market_shape.py \
  --a2-pit docs/review_packages/V1_RECALIBRATION_EVIDENCE_01/A2_PIT_SIMULATION_TRACKS_REDO.json \
  --frozen-market-audit docs/review_packages/V1_RECALIBRATION_EVIDENCE_01/MARKET_SHAPE_AUDIT.json \
  --output-json "$check_dir/audit.json" --output-report "$check_dir/audit.md"
cmp docs/review_packages/V1_RECALIBRATION_EVIDENCE_01/PIT_MARKET_SHAPE_XYZ.json "$check_dir/audit.json"
cmp docs/review_packages/V1_RECALIBRATION_EVIDENCE_01/PIT_MARKET_SHAPE_XYZ.md "$check_dir/audit.md"
```
