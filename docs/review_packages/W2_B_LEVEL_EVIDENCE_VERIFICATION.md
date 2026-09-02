# W2-B-LEVEL-EVIDENCE-VERIFICATION-01

只读验证；未改代码、未拟合参数、未选阈值、未部署、未写生产库/ledger、未调用 Provider、未操作 GitHub。

## 验证 1：准入逆向选择

### Cohort 身份

冻结 CSV：`admission_relative_accuracy_20260830T212500Z.csv`  
SHA-256：`e3a3cccf24ec751a6bca0fff5c6f6f6ff9cbb6896adb1a9747bb6b1f0ed72883`

冻结审计报告 SHA-256：`181883093a1bbf2e8bd109a0453ab6ddd5c62baa33441b0b5143e2000e4fb8e5`  
报告内 snapshot SHA-256：`e3a3cccf24ec751a6bca0fff5c6f6f6ff9cbb6896adb1a9747bb6b1f0ed72883`  
报告内 audit JSON SHA-256：`783af0742951c6efbaf94e53b5bd6e299a7d33b31c5b786c6d45c036c8bd7239`

独立计数复现：

| 项目 | 冻结值 | 实测值 | 判定 |
|---|---:|---:|---|
| evaluation rows | 354 | 354 | CONFIRMED |
| fixtures | 177 | 177 | CONFIRMED |
| AH | 177 | 177 | CONFIRMED |
| TOTALS | 177 | 177 | CONFIRMED |
| EVALUATED_CANDIDATE | 110 | 110 | CONFIRMED |
| EVALUATED_NO_EDGE | 111 | 111 | CONFIRMED |
| BLOCKED_BY_GATE | 133 | 133 | CONFIRMED |

### 独立统计复算

独立实现重新从冻结行计算 `model_brier=(model_probability-target)^2`、
`market_brier=(market_probability-target)^2`，按 fixture 聚类后使用 Python 独立
`Random(seed=20260831)`、5,000 次有放回 cluster resample；2.5%/97.5% 使用与冻结
实现相同的整数索引规则。没有改分箱、聚类单位、resamples 或 seed。

| 市场/对比 | 原始点 | 实测点 | 差异 | 原始 CI | 实测 CI | 判定 |
|---|---:|---:|---:|---|---|---|
| AH lifecycle pass-fail | +0.067037 | +0.0670365164 | -0.0000004836 | [+0.032949,+0.102071] | [+0.032949495,+0.102071156] | CONFIRMED |
| TOTALS lifecycle pass-fail | +0.033896 | +0.0338959769 | -0.0000000231 | [+0.005200,+0.061057] | [+0.005200420,+0.061057310] | CONFIRMED |
| AH delta>=0.10 vs lower | +0.103616 | +0.1036162262 | +0.0000002262 | [+0.056238,+0.147835] | [+0.056237740,+0.147834658] | CONFIRMED |
| TOTALS delta>=0.10 vs lower | +0.073865 | +0.0738654333 | +0.0000004333 | [+0.022297,+0.123638] | [+0.022296867,+0.123638335] | CONFIRMED |

四个 95% CI 均完全高于 0。故「economic-pass 子集相对市场更不准」在这份后验诊断
cohort 上成立，判定 **CONFIRMED**。这不是前瞻有效性、参数选择或阈值授权证据。

口径自由度：冻结报告已写死 fixture cluster、5,000 reps、seed `20260831`、
effective-settlement target 映射和分组布尔条件；本轮没有可影响结论的未决自由度。
若更换聚类单位、resample 数、seed 或 target 定义，将是另一项验证，不得用来改善本结果。

## 验证 2：生产 Elo proxy

### Producer 标记

生产 xG-derived rating producer 位于 [analysis_calculator.py](/Users/liudehua/.hermes/worktrees/w2-b-level-evidence-verification-01/src/w2/prematch/analysis_calculator.py:4728)：

- `elo = 1500 + (xg_for - xg_against) * 100`
- `source="rolling_xg_proxy"`
- `source_group="xg"`
- `is_independent_signal=False`
- `proxy_of="ratings"`
- `collection_status="PROXY_ONLY"`

其进入 λ 的计算位于 [calibration.py](/Users/liudehua/.hermes/worktrees/w2-b-level-evidence-verification-01/src/w2/strategy/calibration.py:67)：
`elo_delta=((home_elo-away_elo)/400)*elo_gap_weight`，当前 `elo_gap_weight=0.28`。
[simulate.py](/Users/liudehua/.hermes/worktrees/w2-b-level-evidence-verification-01/src/w2/strategy/simulate.py:535)
的 `_eligible_elo()` 对 `PROXY_ONLY`/`rolling_xg_proxy` 返回 `None`，所以生产实际 λ 不使用该 proxy。

### 反事实关系

若不经过 `_eligible_elo()` 置空，设
`d_home=home_xg_for-home_xg_against`、`d_away=away_xg_for-away_xg_against`，则：

`raw_delta = 0.5*(d_home-d_away)`；  
`home_elo-away_elo = 100*(d_home-d_away) = 200*raw_delta`；  
`elo_delta = (200/400)*0.28*raw_delta = 0.14*raw_delta`。

因此在任何 raw_delta 有方差的样本上，反事实 OLS 结果必为：

| 统计量 | 结果 |
|---|---:|
| slope | 0.14 |
| intercept | 0 |
| R² | 1.0 |
| residual structure | 无；逐行代数恒等式，残差为 0（仅浮点舍入噪声） |

本 checkout 没有未烧 `season_zips`/raw xG 样本可供另行批量回归；上述结果是由生产 producer
公式逐行代数推导，不冒充实测样本回归。该限制判定为 **PARTIALLY_CONFIRMED**（关系确认，
大样本实测回归未执行）。

### 有状态 Elo 输入

在 [models/independent.py](/Users/liudehua/.hermes/worktrees/w2-b-level-evidence-verification-01/src/w2/models/independent.py:299)
开始的 `update()` 中，`actual_home` 由 `match.home_goals` 与 `match.away_goals` 比较得到，
margin 为两者进球差绝对值，[311](/Users/liudehua/.hermes/worktrees/w2-b-level-evidence-verification-01/src/w2/models/independent.py:311)
使用 `k = 18 * log1p(margin)`，并在 [316-319] 用赛果进球更新 attack/defence。
结论：有状态 Elo 输入是赛果进球，不是 xG，判定 **CONFIRMED**。

## Stop-line 对账

- 代码改动：0
- Provider 调用：0
- 生产数据库读取/写入：0
- ledger 写入：0
- 参数拟合/阈值选择：0
- 部署：0
- GitHub 操作：0
