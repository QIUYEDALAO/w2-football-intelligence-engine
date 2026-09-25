# ERRATA — Candidate C 重校准预注册 v5 三处勘误

- 文档 ID：`W2-CANDIDATE-C-RECALIBRATION-ERRATA-20260924`
- 日期：2026-09-24（+08:00）
- 对象：`W2_CANDIDATE_C_RECALIBRATION_PREREGISTRATION_20260923.json`（v5，commit `4a803fdc`）
- **覆盖声明：本 ERRATA 覆盖 v5 下列对应字段；v5 冻结原文一字不改。** 后续 fit / 回放 / 验收以「v5 原文 + 本 ERRATA」合并口径为准。

## 勘误 ① — `confirmed_findings.total_underestimate` → 单一口径

v5 原文为三口径并存（−0.22 / −0.30 / −0.17，附「实施时冻结唯一公式」待办）。REL-CALIB-02 已冻结唯一权威公式 **TOTAL_INFER_V1**（见 `W2_TOTAL_INFER_V1.md`，FROZEN），重算单一口径：

| 口径 | 模型 total | 实际 total | gap | scale |
|---|---|---|---|---|
| **v3-only（权威）** | 2.823 | 2.879 | **−0.056 球** | **1.020** |
| v2+v3 全量（仅对照） | 2.836 | 3.007 | −0.171 | 1.060 |

分 selection（v3-only）：UNDER 行 −0.402 / OVER 行 +0.440（条件于选边的镜像，非全局刻度）。三口径归并：−0.17 与本公式全量一致（互验通过）；−0.22 系诊断 1,394 分母差异；**−0.30 系 x.75 映射 bug，作废**。

## 勘误 ② — `track_design.track_a_total_scale.initial_estimate`：1.05 → 1.020

v5 原文初值 1.05（及更早 1.11）均来自带 x.75 映射 bug 的反推实现，作废。以 TOTAL_INFER_V1 为准：**v3-only 无条件低估仅 0.056 球，total_scale 初值 = 2.879 / 2.823 = 1.020**。

附带影响（评审时注意）：v3 的 UNDER bias +11.2pp 中 total 成分仅约 1.5pp（0.056 球 × ~27pp/球），主成分为全局过自信；Track A 预期收益下调，Track B（w_AH 0.9 高模型权重融合）相对重要性上调。

## 勘误 ③ — `frozen_replay_result_v4.walkforward_params_by_fold` 的 scale 折估

v4 回放账本（SHA-256 `ee128188…`）中 Track A 修正路径与 scale 折估 **1.066 / 1.030 / 1.070 使用带 x.75 映射 bug 的反推实现，作废**；OOS 结论（重点档 +1.53%/注）标记为**待重跑**，由 REL-CALIB-03 用 TOTAL_INFER_V1 复跑后取代。

bug 说明：初版脚本 UNDER x.75 的 WIN 区间错位一档（误用 ple(ib−1)=P(≤1) 而非 ple(ib)=P(≤2)），致该行 λ̂ 系统性偏低约 1 球（x.75 行占 TOTALS 行约 21%），scale 与 total 低估量级被高估。

**不受影响项：** `w_AH = 0.9` / `w_TOTALS = 0.0` 的取值与结论不变——AH 路径不经过 totals 五态映射；Track D 反转机制核心证据（UNDER 行市场 P(over)=49.7% vs 实际 54.8%）亦不经过 λ 反推，维持有效（机制解释中「UNDER 行低估 0.72 球」修正为 0.40 球）。

### 勘误 ③ 闭环 — REL-CALIB-05 重跑完成（2026-09-24 01:40 +08:00）

已用 TOTAL_INFER_V1（无过滤无剔除、x.75 修复版）重跑 v3-only 三段 walk-forward，产出**账本 v5**：

- 路径：`W2_重校准回放账本_v5_v3only_TotalInferV1_20260924.jsonl`
- SHA-256：`f91b3651a49297aa78a177465152d09ab1959c2b6266bfcd8059876e4ff257fc`

**真实 total_scale 折估（取代 bug 版）：**

| fold | bug 版（作废） | TOTAL_INFER_V1（权威） |
|---|---|---|
| 1 | 1.066 | **0.9895** |
| 2 | 1.030 | **0.9533** |
| 3 | 1.070 | **0.9772** |

**OOS 结论确认不变**：重点 43 注 +0.66u（**+1.53%/注**，与 v4 逐笔一致）；一般 2 注、观察 5 注、不推 207 注 −2.79%。机制：w_TOT=0 时 TOTALS 融合概率=纯市场（Track A 不进权重），AH 路径不经过 totals 映射——bug 的影响被实证限定在 scale 折估数字本身。

**w 取值不受影响确认**：w_AH 1.0/1.0/0.9（预注册取 0.9）、w_TOTALS 0/0/0，三折重扫结果与 v4 一致。

**附带发现（评审注意）**：修复后 scale 折估在 0.95~1.02 围绕 1 波动（合法池口径），叠加全样本 1.020——**v3 的 total 刻度已无系统性低估**（bug 版"低估 3~7%"是假象）。Track A 的可修正空间接近零，根因进一步向「全局过自信 + 条件于选边的镜像 ±0.4 球」集中；Track B/Track D 的相对权重继续上调。

---

## 勘误 ④（追加）— Track A 最终决策（REL-CALIB-06，2026-09-24 01:55 +08:00）

**决策 1：`total_scale` 冻结值 = 1.0（不修正）。** 数据依据：

- 三段 walk-forward 折估 0.9895 / 0.9533 / 0.9772，围绕 1 波动且 fold 2 < 1；
- 全样本 v3-only gap = −0.056 球，逐行 SD≈1.7 球、n=373 → SE≈0.088，**|gap| < 1σ，统计上与 0 不可区分**；
- 分联赛 gap（v3-only，冻结公式）：mls −0.445（n=51）~ ligue_1 +0.539（n=19），方向不一致且单联赛均 < 2σ；全局一刀切必错一半联赛，且含选边合成偏差（±0.4 镜像按各联赛方向比例加权）；
- 预注册纪律：无证据不动参数。Track A 立项依据（total 低估 0.22~0.30 球）已证为 x.75 映射 bug 假象，依据不存在。

**决策 2：Track A 形态 = 关闭（跳过 fit，`total_scale` 恒 1，不进入 calibration identity 参数表）。** 理由：保留一个恒 1 的"验证性参数"要付出 identity 快照、fit、验收项的维护成本，而其验证价值（total 校准度）用描述性指标即可零成本获得；关闭后实施面收窄至 Track B/C/D，出错面同步收窄。

**替代安排（验证价值不丢失）：**

- total 校准度降级为 validation/test 的**描述性监测项**：报告 |mean(model_total) − mean(actual_total)| 全局与分联赛（n≥20），仅告警、不作选择依据；
- Track B λ 层融合中 `lambda_total_model_trackA ≡ 原生模型 total`（scale 恒 1）；
- 重启触发器：validation 或周复盘连续两期出现全局 |Δtotal| > 0.15 球 → 重新立项（新预注册 + 新 cohort），禁止就地调参。

**不受影响项（Track B/C/D 参数维持）：** `w_AH = 0.9`、`w_TOTALS = 0.0`（仅作 Track D 反转信号）、`fade_delta = +0.05`、三档边界 0.05/0.02/0.00、`rebate = 0.025`、档位映射与展示全集定义。

---

## 勘误 ⑤（追加）— TOTAL_INFER_V1 的 UNDER x.25 半态方向错误 + AH 反解误差量化闭环（2026-09-25，kimi 二次验收发现）

**问题 1：V1 公式一处方向错误。** V1 冻结版将 UNDER x.25 在 total = ib 时的半态写为 HALF_LOSS；按标准亚盘 quarter-line 规则应为 **HALF_WIN**（押 x.0 走盘 + 押 x.5 赢）。实锤：v3-only UNDER x.25 共 54 行，V1 映射反推 54/54 行 SSE>0.01，修正映射 54/54 行 SSE=0。V1 中「x.25 行 SSE>0.01 疑 Dixon-Coles ρ 调整」归因作废（真因=映射错误）。

**影响**：v3-only 模型 total 均值 2.8230 → 2.8194（−0.004 球），scale 1.020 → 1.021。**主结论不变**（total 无系统性低估、Track A 关闭决策不受影响）。

**处置**：已按变更规则新起 `W2_TOTAL_INFER_V2.md`（DRAFT 待 Owner 冻结；仅改此一处，其余继承 V1）。V1 的 UNDER x.25 半态定义作废，V2 冻结前 V1 仍为名⽬现⾏但该行结果按修正值使用。

**问题 2：AH DC/Skellam 反解误差 NOT_ESTIMABLE → 已量化闭环。** kimi 参数化扫描（140 点 × 3 线型，rho ≤ 0.15）：DC 矩阵二分反解 vs Skellam 逐字反解的 delta 偏差 **≤ 0.091 球（P90 ≤ 0.070）**，对 success 概率影响 ≤ ~3pp。声明：生产统一以 DC 矩阵反解为唯一定义（与生产五态生成同源），Skellam 仅作交叉验证。原「NOT_ESTIMABLE」标注由本量化声明取代。

**对 Codex 两处标注的评价**：不伪造结果、不擅改冻结文件、不假装闭环——处理合规且专业；其中 NOT_ESTIMABLE 一项经参数化扫描证明可估，已闭环。

---

签署：kimi（REL-CALIB-02 收尾交付）。本文件落盘后，v5 + ERRATA + TOTAL_INFER_V1 三者构成当前唯一有效口径集。
