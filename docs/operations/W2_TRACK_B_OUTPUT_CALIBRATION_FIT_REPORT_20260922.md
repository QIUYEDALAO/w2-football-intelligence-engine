# Track B 输出层校准：修复后 TRAIN-only 离线拟合报告

日期：2026-09-22（Asia/Shanghai）  
状态：`FITTED_CALIBRATED`；仅离线候选，不上线、不推荐、不写 calibration ledger。  
边界：未读取或评分 holdout/test，未改生产代码、未写生产库、未调用 Provider、未部署；生产仍为 `BASELINE_PRIOR`。

## 结论

三个实现问题已修复并重新拟合：

1. PAVA 合并块阈值从 `mean(x)` 改为右边界 `max(x)`，保留既有 rightmost-knot 阶梯预测合同。
2. global 先验改为 `market × selection`：`TOTALS/OVER`、`TOTALS/UNDER`、`ASIAN_HANDICAP/HOME`、`ASIAN_HANDICAP/AWAY` 四条曲线互相独立。
3. 删除 `n=20` 硬切换；所有联赛格子均使用连续权重 `w=n/(n+20)` 向对应 market×selection global 收缩。

预注册同步加入 selection-aware Platt logistic baseline 与 TRAIN 内 expanding-time OOF family 选择：每个 market×selection 先比 Brier，再比 NLL，再按固定名称打破平局。此流程没有接触 holdout/test。

修复后的层级 isotonic 不再被跨 selection global 压坏：时间 OOF 为 OVER 选择 hierarchical isotonic，训练集 OVER `cal_gap` 从 `+0.018530` 到 `+0.005049`；其余三个 market×selection 选择 Platt。OOF 上 OVER 两个候选的 cal_gap 仍为负（isotonic `-0.092736`、Platt `-0.109699`），说明时间漂移/泛化风险仍大；本轮不据 TRAIN 收敛申请上线。

## 数据与独立样本

复用冻结 TRAIN 导出 `/private/tmp/w2-trackb-latest.csv`；脚本接口不接受 holdout/test 文件。

| 项目 | 值 |
|---|---:|
| 独立评估行 | 1,396 |
| 覆盖 fixture | 698 |
| 格子数 | 105 |
| 按 admission 排除行 | 26 |
| 按 admission 排除 fixture | 13 |
| 排除原因 | `no_model_settlement_distribution`（26 行） |
| `ASIAN_HANDICAP` 行 | 698 |
| `TOTALS` 行 | 698 |
| evaluation CSV SHA-256 | `901ffc1409677a3a68160a8d3ad16ac9b3fa35a596007e57819bbedc64e7a159` |
| home/away CSV SHA-256 | `3a533486d2508bc32861f9632ed9ca0b561ace116e2ce46ff60f49022645df60` |
| team-xG CSV SHA-256 | `609bbbe3f22d98707906f235a1007e5359a47b23037d58c5e14b50554424d376` |

独立样本仍是每场×盘口最后一次评估；正向目标仍为 `P(WIN)+P(HALF_WIN)` 对实际正向结算事件。没有改推荐、结算、EV 或赔率口径。

## 时间 OOF family 选择

| market × selection | raw Brier / NLL / gap | hierarchical isotonic Brier / NLL / gap | Platt Brier / NLL / gap | 选中 family | OOF n |
|---|---:|---:|---:|---|---:|
| TOTALS × OVER | 0.241061 / 0.674755 / -0.030368 | 0.262316 / 0.718902 / -0.092736 | 0.267178 / 0.729656 / -0.109699 | hierarchical isotonic | 233 |
| TOTALS × UNDER | 0.267547 / 0.730932 / +0.158269 | 0.251952 / 0.707734 / +0.005869 | 0.240557 / 0.674133 / +0.003558 | Platt | 326 |
| AH × HOME | 0.240702 / 0.673792 / +0.066701 | 0.243733 / 0.748198 / +0.006689 | 0.237149 / 0.666286 / -0.016589 | Platt | 272 |
| AH × AWAY | 0.270086 / 0.742250 / +0.120811 | 0.277087 / 1.332965 / +0.069308 | 0.257490 / 0.708884 / +0.066664 | Platt | 286 |

这里的 OOF 只承担预注册的 family 选择，不是 holdout 结果；raw 只作对照，不参与选择。OVER 选择 isotonic，其余三层选择 Platt。完整曲线和参数保存在机器 artifact。本轮没有据结果改动 family、`k=20`、`min_cell_n`、分桶或选择规则。

## TRAIN cal_gap 汇总

定义：`cal_gap = mean(calibrated_probability - realized_positive)`。

| 分层 | n | 原始 cal_gap | 选中 family 的 TRAIN cal_gap |
|---|---:|---:|---:|
| 全体 | 1,396 | +0.092006 | +0.001052 |
| TOTALS / OVER | 291 | +0.018530 | +0.005049 |
| TOTALS / UNDER | 407 | +0.157099 | -0.000000 |
| AH / HOME | 340 | +0.068603 | +0.000000 |
| AH / AWAY | 358 | +0.099954 | +0.000000 |

这是在同一 TRAIN 上拟合/选择后的完整性结果（OVER 用层级 isotonic，其余分层用 Platt），不是泛化改善证据；判断必须以未来未见 holdout/test 为准。

排除披露：当前输入中 26 行、13 个 fixture 因缺少 `model_settlement_distribution` 被原
admission 规则排除；artifact 的 `manifest.excluded_fixture_ids` 保留完整 ID 清单。本轮
只补披露，没有改变 admission 规则，也没有把这些行或 fixture 捞回训练集。

## 产物与验证

- 脚本：[fit_track_b_output_calibration.py](../../scripts/quant/fit_track_b_output_calibration.py)
- 机器 artifact：[W2_TRACK_B_OUTPUT_CALIBRATION_FIT_20260922.json](W2_TRACK_B_OUTPUT_CALIBRATION_FIT_20260922.json)
- 预注册协议：[W2_CANDIDATE_C_RECALIBRATION_PREREGISTRATION_20260922.json](W2_CANDIDATE_C_RECALIBRATION_PREREGISTRATION_20260922.json)
- 契约测试：[test_fit_track_b_output_calibration.py](../../tests/unit/test_fit_track_b_output_calibration.py)

验证结果：`.venv/bin/python -m pytest -q tests/unit/test_fit_track_b_output_calibration.py` → **4 passed**；JSON 可解析；冻结输入重放得到 4 条 market×selection global、105 条 cell 曲线、单调曲线和连续权重；PAVA 右边界契约测试覆盖了 mean(x) 提前切换的回归场景。

## 安全状态

```text
provider_calls=0
production_writes=0
deployments=0
calibration_ledger_writes=0
production_status=BASELINE_PRIOR
holdout/test_read_or_scored=false
```

本 artifact 不构成注册或上线授权；任何前瞻验收必须在 family、参数和输入 digest 冻结后单独打开。
