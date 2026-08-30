# OOF 方差重估执行回执 — `OOF_VAR_01`

预注册：`OOF_VARIANCE_PREREGISTRATION.json`（冻结于任何计算之前）
来源：外部专家评审 V2.0 建议的唯一合法「更快路径」
执行者：Claude Code

## 边界

```text
数据        仅 TRAIN 前缀（kickoff < 2025-11-11 00:15:00+00）
validation  SEALED —— 未加载、未评分、未查看
Penaltyblog 未涉及
U2          未重开、未修改
```

**本回执不产生任何模型优劣结论。** OOF 均值仅作 nuisance 上下文，不是效应估计。

## 折设计与覆盖

TRAIN `5,869` 场按 kickoff 切成 6 个等量块，扩窗滚动：

```text
fold 1  train 978  -> OOF 978
fold 2  train 1,956 -> OOF 978
fold 3  train 2,934 -> OOF 978
fold 4  train 3,912 -> OOF 978
fold 5  train 4,890 -> OOF 979

OOF d_i = 4,891 / 5,869 = 83.3%
```

每个 `d_i` 均来自**未参与该折 challenger 拟合**的 fixture。

## 方差与可检测下限

```text
OOF d_i     n = 4,891    sd = 0.069810
对照 U2     in-sample    sd = 0.078733     OOF 小 11.3%
```

| 估计量 | SE | MDE @ N=2790 | 所需 N |
|---|---:|---:|---:|
| iid | 0.000998 | 0.003286 | 4,821 |
| kickoff-date 一路聚类（U2 口径） | 0.000972 | 0.003201 | 4,574 |
| league × month block bootstrap（冻结合同，B=2000，seed 20260830） | 0.000986 | 0.003246 | 4,702 |
| **U2 原报告** | 0.001005 | **0.003624** | **5,859** |

单元数：`league × month` = `164`；kickoff 日数 `G = 330`。

## 三项结论

**一、U2 的 futility 停止得到印证，未被推翻。**
三个估计量给出的 MDE 为 `0.0032–0.0033`，全部仍 `> MME = 0.0025`。
所需 validation N 从 `5,859` 降到 `4,574–4,821`，仍高于现有 `2,790`。

**二、U2 的 cluster 执行偏差在数值上不重要。**
冻结合同要求 `matchday + league`，U2 实际只按 kickoff date 聚类。
本次按合同实现的 league × month block bootstrap 给出 SE `0.000986`，
与一路日聚类的 `0.000972` 相差 `1.4%`，与 iid 的 `0.000998` 相差 `1.2%`。
该偏差应当披露且已披露，但它没有改变任何结论。

**三、in-sample 方差是保守的，不是乐观的。**
评审指出该方向不确定。实测为 OOF sd 小于 in-sample sd `11.3%`，
即 U2 高估了 MDE、低估了功效。修正后功效仍不足。

## score identity 的尺度效应（证实评审第 9 点）

```text
等权/市场聚合      sd = 0.069810
16 线扁平平均      sd = 0.076765      U2 实际使用
比值               0.9094
```

仅改变 within-fixture 聚合规则，primary 的尺度就变了 `9%`。
这直接证明：**未绑定完整 `PRIMARY_SCORE_IDENTITY` 的「0.0025 nats」不是稳定单位。**

分市场离散度：`OU sd = 0.084202`，`AH sd = 0.099170`。

## 不得据此做的事

```text
不得据此调整 MME、split、min_history、线网格或 cohort
不得据此声称任一模型更好
不得据此授权任何评分实验
MME 的角色（design effect vs promotion threshold）与
champion / challenger 的 decision utility 仍是待外部论证的开放问题
```

本结果只把功效地板从 `0.003624` 收紧到 `0.0032–0.0033`，
并证实 U2 的两项已披露缺陷在数值上不改变结论。
