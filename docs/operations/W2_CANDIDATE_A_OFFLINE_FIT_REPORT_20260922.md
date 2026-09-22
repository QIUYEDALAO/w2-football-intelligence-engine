# Track A 离线拟合报告（2026-09-22）

## 结论

Track C 已标记 `CANCELLED_NO_PIT_DATA`；本轮仅运行 Track A。Track A 已在当前可重建
的历史 PIT 上完成离线拟合，产出标记为 `FITTED_CALIBRATED`。该标记只表示离线候选
产出，不表示验证通过、注册或上线。

生产仍保持 `BASELINE_PRIOR`。

## TRAIN manifest

- 来源：只读 VPS 导出 `team_xg_match` + `raw_payload fixtures`。
- 规则：按 kickoff 排序；每队严格使用此前最近 5 场；两队均满足后保留；不按数量截断。
- 实际独立 fixture：9,325 场；联赛：26 个。
- `team_xg_match.csv` SHA-256：`609bbbe3f22d98707906f235a1007e5359a47b23037d58c5e14b50554424d376`
- `home_away.csv` SHA-256：`3a533486d2508bc32861f9632ed9ca0b561ace116e2ce46ff60f49022645df60`
- fixture-id manifest SHA-256：`fb482298257ba76051cd168d9591fae2475e0efb4ec66b75600f0dc2b218a6da`

## 参数化与收敛

拟合 `total_scale`、`league_total_scale[league]`、`home_advantage_goals` 和
`league_home_advantage[league]`；分层参数以固定 `lambda_reg=5.0` 向全局参数收缩。
目标为比分 Poisson NLL（保持生产 total/lambda clamp），使用闭区间投影对角 Newton
更新和回溯线搜索。

| 指标 | 值 |
|---|---:|
| baseline NLL | 27,673.054423 |
| baseline mean NLL | 2.967620 |
| candidate NLL | 27,629.285841 |
| candidate mean NLL | 2.962926 |
| penalized objective | 27,631.034930 |
| 迭代次数 | 115 |
| 收敛状态 | `CONVERGED_OBJECTIVE_TOL` |

全局候选参数：

```text
total_scale = 1.015879
home_advantage_goals = 0.316214
```

完整的 26 个联赛分层参数、manifest、收敛尾迹和 NLL 数值见机器报告：

`docs/operations/W2_CANDIDATE_A_OFFLINE_FIT_20260922.json`

## 安全边界

`provider_calls=0`、`production_writes=0`、`deployments=0`、`calibration_ledger_writes=0`。

validation/test 尚未打开；本报告不声称候选通过前瞻验收，也不申请注册或部署。
