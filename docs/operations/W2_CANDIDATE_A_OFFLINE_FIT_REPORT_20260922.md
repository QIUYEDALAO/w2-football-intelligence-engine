# Track A 离线拟合报告（2026-09-22，当前有效 artifact）

## 结论

Track C 已按预注册标记 `CANCELLED_NO_PIT_DATA`。Track A 已按预注册终止并归档，artifact
状态为 `REJECTED_BY_TRAIN_OOF_SCORELINE_NLL`：`candidate mean_nll=2.973974352639`
高于 `raw mean_nll=2.973314433300`，且三个已评分 rolling-origin folds 方向一致，违反
`track_a_primary.scoreline_nll.required`。因此不打开 holdout、不再重拟合。Track A 原本只拟合
`total_scale` 与 `league_total_scale[league]`；`home_advantage_goals` 沿用生产中已
由 `V1-HOME-ADVANTAGE-RECALIBRATION-01` 验证的 `0.30`，`league_home_advantage`
及其余 delta 路径不拟合、不改写。该 artifact 已归档，不进入 holdout。

## TRAIN manifest

- 来源：只读冻结导出 `team_xg_match.csv` + `home_away.csv`。
- 规则：按 kickoff 排序，每队严格使用此前最近 5 场；两队均满足后保留。
- 独立 fixture：9,325；联赛：26。
- `team_xg_match.csv` SHA-256：`609bbbe3f22d98707906f235a1007e5359a47b23037d58c5e14b50554424d376`
- `home_away.csv` SHA-256：`3a533486d2508bc32861f9632ed9ca0b561ace116e2ce46ff60f49022645df60`
- fixture-id manifest SHA-256：`fb482298257ba76051cd168d9591fae2475e0efb4ec66b75600f0dc2b218a6da`

## 参数化与收敛

候选只优化 `total_scale` 与按联赛分层的 `league_total_scale`，采用
`lambda_reg_total=5.0` 的层级收缩。`home_advantage_goals=0.30` 固定，来源是生产
calibration ledger 中 `V1-HOME-ADVANTAGE-RECALIBRATION-01` 的 10 折 OOF + 2,000 次
bootstrap `APPROVED_VALIDATED` 记录。生产 `dixon_coles_rho=0.0`，因此比分 NLL 使用的
Dixon-Coles 路径在当前生产参数下是 no-op；没有引入新的 DC 参数。

| 指标 | baseline | candidate |
|---|---:|---:|
| 未惩罚总 NLL | 27,673.054423 | 27,629.285841 |
| mean NLL | 2.967620 | 2.962926 |
| 拟合最终状态 | — | `CONVERGED_OBJECTIVE_TOL` |

全局候选参数：

```text
total_scale = 1.015086
home_advantage_goals = 0.300000 (fixed)
```

26 个 `league_total_scale`、收敛尾迹和完整 manifest 见：
`W2_CANDIDATE_A_OFFLINE_FIT_20260922.json`（schema `w2.candidate_a.offline_fit.v2`）。

## TRAIN 内 expanding-window rolling-origin OOF

折数在运行前固定为 4 个连续时间块，因此产生 3 个可评分 validation folds；每折只
用此前块拟合，再评分下一块。OOF 不读取、不评分 holdout/test，也不用于事后改变参数
或预注册规则。

| 指标（3 折合并） | raw baseline | candidate |
|---|---:|---:|
| OOF mean scoreline NLL | 2.973314433300 | 2.973974352639 |
| OOF total absolute gap | 0.058146554189 | 0.004456397579 |
| OOF league n≥20 absolute gap 中位数 | 0.116137931034 | 0.084664443840 |
| OOF 1X2 multiclass Brier | 0.206030582452 | 0.206161293555 |
| OOF rows | 6,994 | 6,994 |

逐折 raw/candidate 指标和训练窗口大小保存在 artifact 的 `oof.folds`。这些是 TRAIN
内部诊断，不能替代前瞻 validation/test 验收。

## 旧 artifact

旧的零 OOF 单切分 home-advantage 回归产物保留为：
`W2_CANDIDATE_A_OFFLINE_FIT_20260922_SUPERSEDED_HOME_ADVANTAGE_REGRESSION.json`。
其状态为 `SUPERSEDED_HOME_ADVANTAGE_REGRESSION`，旧 `home_advantage_goals=0.316214`
不再作为当前候选参数。

## 安全边界

```text
provider_calls=0
production_writes=0
deployments=0
calibration_ledger_writes=0
holdout_read_or_scored=0
production_status=BASELINE_PRIOR
```

本轮没有改生产代码、推荐/结算/EV、ledger、Provider、配额、并发、重试或安全门。
