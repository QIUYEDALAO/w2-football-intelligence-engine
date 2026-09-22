# Candidate C 离线拟合启动报告（2026-09-22，已被新授权 supersede）

> 本文件记录前一版“精确 8,659 + Track C”协议下的阻塞结果。Owner 随后已取消
> Track C、解除精确 8,659 硬锁，并授权 Track A 扩展拟合；当前有效结果见
> `W2_CANDIDATE_A_OFFLINE_FIT_REPORT_20260922.md`。

## 结论

本次离线拟合**未产出候选参数**，状态为 `BLOCKED_INPUT_RECOVERY`，不是
`FITTED_CALIBRATED`。原因是冻结协议要求的 TRAIN cohort 与 PIT 特征快照无法由当前
可复核工件完整恢复；按 fail-closed 规则没有用近似 cohort、按数量截取或事后插补来拟合。

协议文件已冻结：

`docs/operations/W2_CANDIDATE_C_RECALIBRATION_PREREGISTRATION_20260922.json`

其中 `status=FROZEN`，`frozen_at=2026-09-22T09:31:00+08:00`，validation/test 各为
1,000；总 look gate 已同步为 2,000 条。

## 只读输入检查

检查对象为 VPS `root@45.207.194.97` 的 `w2-staging-postgres-1`，仅执行只读
`SELECT/COPY`，没有写库、Provider 调用或部署。

| 检查项 | 结果 | 解释 |
|---|---:|---|
| `team_xg_match`（截至 2026-08-30） | 21,686 行 / 10,843 场 | 可用于重建候选 PIT，但不是冻结 cohort artifact |
| 严格此前至少 5 场的重建结果 | 9,325 场 | 与冻结 TRAIN 8,659 不一致，不能按计数倒截 |
| 当前 enabled 联赛集合（13 个历史 enabled ID）重建 | 8,671 场 | 仍比 8,659 多 12 场，缺少冻结排除身份/原因 |
| `team_rating_snapshots` | 242 行 / 242 队 | 不是 8,659 场逐场 PIT Elo 覆盖 |
| `team_value_asof_artifacts` | 0 行 | squad value PIT 特征完全缺失 |
| `model_forecast_capture` 中 Elo/squad 字段 | 无可用于该 TRAIN 的完整逐场快照 | 不能替代 PIT artifact |

已发现的本地/历史证据只包含 `V1_SLOPE_FIT_TRAIN.json` 的汇总值和 SQL 导出定义，
没有冻结的 8,659 行 identity、league、PIT 特征及排除清单。另一个历史
`CURRENT_XG_CORPUS.json` 是 9,401 场、不同 schema/排除规则的 corpus，不能冒充本协议
TRAIN。

## Track A / Track C 执行判定

- Track A：`NOT_RUN_BLOCKED_EXACT_TRAIN_COHORT_MISSING`。虽然 xG 可重建出近似数据，
  但这会改变 TRAIN identity，不能据此报告 `total_scale` 或 NLL 收敛。
- Track C：`NOT_IDENTIFIABLE`。冻结规则要求 Elo 与 squad value 缺失时按生产语义为 0；
  当前 squad value 无任何 PIT artifact，且 Elo 无逐场覆盖，三个权重不能被识别，禁止
  伪拟合。
- validation/test：未读取、未计算、未暴露任何 metric，符合协议的 `before_look` 规则。
- 生产回退：仍为 `BASELINE_PRIOR`；未写 calibration ledger、未改生产参数、未上线。

## 安全证明

`REAL_PROVIDER_CALLS=0`、`PRODUCTION_DB_MODIFIED=false`、`DEPLOYMENT_EXECUTED=false`。
本报告仅记录数据可用性与 fail-closed 判定，不构成候选通过、注册或部署授权。

要继续拟合，必须先提供/恢复带 digest 的冻结 8,659 TRAIN artifact（含每场 PIT xG、
league identity、结果和排除原因）以及逐场 Elo/squad value PIT 特征；恢复后应在不打开
validation/test outcome 的情况下重新运行 Track A/C。
