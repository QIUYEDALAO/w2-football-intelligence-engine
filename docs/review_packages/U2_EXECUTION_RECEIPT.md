# U2 执行回执

预注册：`U2_PREREGISTRATION.md` V2 + `U2_ARMING_FREEZE.json`（冻结于任何拟合与评分之前）
执行者：Claude Code
生产权威：`ea557bb8 / schema 0070`

## 结论

```text
INSUFFICIENT_POWER_DO_NOT_SCORE
```

**validation 五态分数未被读取。** 冻结的 futility 规则在评分前触发。

## 执行链

| 步骤 | 结果 |
|---|---|
| cohort 导出 | 生产 `team_xg_match` + `raw_payload` fixtures-endpoint 映射 |
| league 映射 | 9,551 / 9,551 = 100% |
| home/away 映射 | 9,551 / 9,551 = 100%，与 `team_id` 零不一致 |
| cohort 冻结 | SHA-256 `40802614114c06ebc7bf4a3eb93578a313631fd50c6440803c1ff1622f86469c` |
| 冻结文档 | `U2_ARMING_FREEZE.json`，写于任何拟合之前 |
| PIT 特征 | 滚动 xG 严格取 kickoff 之前；目标 fixture 不进入自身特征 |
| min_history=5 | eligible 8,659 / ineligible 892 / total 9,551 |
| 切分 | train 5,869（2024-02-22→2025-11-10）/ validation 2,790（2025-11-11→） |
| proxy Elo 断言 | **通过**：0 例违反；3 例 `raw_delta==0` 均满足 `elo_delta==0` |
| challenger 拟合 | 仅训练前缀，L2 Poisson IRLS，一次成型，无重试无回退 |
| futility | **触发停止** |

## 对照与挑战者

对照 `PRODUCTION_FORMULA_XG_WITH_PROXY_ELO` 复现生产闭式，
`elo_delta = 0.14 × raw_delta` 逐 fixture 断言通过。

challenger 系数（仅训练前缀）：

```text
intercept            -0.779483
home_field           +0.217511
attack_xg_for        +0.426216
opponent_xg_against  +0.283332
elo_gap              +0.459156
```

## Futility 计算

```text
训练集 d_i        n = 5,869    mean = +0.008674    sd = 0.078733
日聚类 SE         0.001005     G = 455 天          膨胀 0.98x
validation N      2,790        预计 SE = 0.001457
MDE (80% power, 单侧 5%)       0.003623 nats
MME                            0.0025  nats

MDE > MME  =>  INSUFFICIENT_POWER_DO_NOT_SCORE
```

训练集 `mean = +0.008674` 是**样本内**量（challenger 在该前缀上拟合），
仅用于估计 `d_i` 的离散度，**不是效应证据**，不得引用为 challenger 优势。

## 不得据此做的事

```text
不得改切分比例以换取 validation 功效
不得下调 MME
不得改 min_history、线网格或 cluster 定义
以上任一改动都是在看到 futility 结果之后调整设计
```

要在此 MME 下获得功效，只能增加 validation 样本本身（等待新比赛），
且必须重新冻结 cohort 与切分。

## 描述性观察（非 primary，非结论）

对照 λ 均值 主 `1.414` / 客 `1.302`（差 0.11），
实际进球均值 主 `1.560` / 客 `1.250`（差 0.31）。
challenger 拟合出的 `home_field = +0.2175`（对数尺度，约 +24%），
而生产 `home_advantage_goals = 0.12` 在 λ≈1.35 上约为 +9%。

这提示生产主场项可能偏低，但**属训练集描述性观察**，
不是 primary estimand，也未经任何 out-of-sample 检验。

## 边界

```text
生产写入        0
部署            0
challenger 进入生产路径   否
validation 分数读取       否
本结论不授权 champion 晋级或任何生产变更
```
