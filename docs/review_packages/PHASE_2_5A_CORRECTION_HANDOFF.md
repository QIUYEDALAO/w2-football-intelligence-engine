# Phase 2.5a 更正交接单

用途：更正 `PHASE_2_5A_FINDINGS_HANDOFF.md` 中的一处事实错误，及其已传播进
`W2_BASELINE_PROBABILITY_QUALITY_AUDIT.md` 的三处表述。
执行者：Claude Code，只读静态审计
审计基线：`origin/main@3b7f87db`
状态：`CORRECTION_HANDOFF_DOCS_ONLY`
授权范围：**仅文档更正**。不改业务代码、不接 Penaltyblog、不访问 VPS/Provider、不部署。

---

## 1. 错误内容

`PHASE_2_5A_FINDINGS_HANDOFF.md` 第 167 行写：

```text
该验证结论未见于仓库
```

**该陈述错误。** 稳健性验证已经完成，报告在仓库中：

```text
docs/archive/league_whitelist/W2_UNDERSTAT_MODEL_ITERATION_1_ROBUSTNESS_20260707.md
Status: ROBUST_IMPROVEMENT
```

错误由 Claude Code 引入（只搜索了 `docs/league_whitelist/` 未搜 `docs/archive/`），
已传播进审计报告三处，须一并更正。

### 需要修改的三处

| 位置 | 现文 | 应改为 |
|---|---|---|
| `W2_BASELINE_PROBABILITY_QUALITY_AUDIT.md:79` | `robustness conclusion is absent from the repository` | `robustness conclusion exists: ROBUST_IMPROVEMENT, 2026-07-07 archived report` |
| 同上 `:122` | 「仓库内没有该稳健性验证的结论」 | 按第 2 节改写为已完成，并引用稳健结果 |
| 同上 `:134` | 「2026-07-07 已存在单折定量证据」 | 改为「已存在单折 + 稳健性(跨季 + 4 折 rolling-origin)定量证据」 |

---

## 2. 正确的事实

### 2.1 稳健性验证已完成且通过

`W2_UNDERSTAT_MODEL_ITERATION_1_ROBUSTNESS_20260707.md`，工单要求的三张表全部产出：

**train/validation gap**（train 2236 / val 959，fitted+temperature）

```text
log_loss +0.008477   Brier +0.007031   RPS +0.008246   ECE +0.022574
→ 无明显过拟合
```

**跨季双向**

```text
train 2023 → val 2024 (N=1685):  delta log_loss -0.024113,  delta ECE -0.054554
train 2024 → val 2023 (N=1510):  delta log_loss -0.032057,  delta ECE -0.060520
```

**滚动 origin 4 折**

| fold | train | val | fitted LL | prior LL | delta |
|---:|---:|---:|---:|---:|---:|
| 1 | 1437 | 479 | 0.976957 | 1.017201 | −0.040244 |
| 2 | 1757 | 479 | 0.985057 | 1.012744 | −0.027687 |
| 3 | 2076 | 479 | 0.996999 | 1.018464 | −0.021465 |
| 4 | 2396 | 479 | 1.000485 | 1.016593 | −0.016108 |

```text
4/4 折胜过 baseline prior 与 Elo-only
mean delta log_loss = -0.026376,  sd = 0.009400
```

报告结论：`ROBUST_IMPROVEMENT`，并明确 `0.969900` 为乐观值、非生产启用决定。

### 2.2 真实效应量应改用稳健值

审计报告目前引用单折 delta `-0.035368`。应改为并列引用：

```text
单折 (N=453)          delta log_loss -0.035368   ← 报告自述为乐观值
跨季双向              -0.024113 / -0.032057
滚动 4 折均值          -0.026376  (sd 0.009400, 4/4 胜)
```

结论段应以**稳健值 ~-0.026 nats** 为准，单折值仅作历史记录。

### 2.3 新增待验证项：优势单调衰减

4 折 delta 单调收缩 `-0.0402 → -0.0161`，相对衰减 **60%**。
同期 baseline prior 四折基本持平（1.0172 / 1.0127 / 1.0185 / 1.0166，跨度 0.0006）。

由于 prior 是固定常数、不随训练量改善，「后期窗口更难」无法解释该趋势；
更可能是拟合模型在后期窗口特异地丢失优势。

**必须登记为待验证假设，不得写成结论。** 4 个点、sd 0.0104、跨度约 2.3 SD，
是警告信号而非统计证据。折间训练集嵌套、验证窗口相邻，观测不独立。

原报告注意到「Fold 4 弱于单折结果」，但未指出单调趋势，也未指出 prior 是平的。

---

## 3. PR #193 的正确解释

审计报告若提及该 PR，须使用下列表述，不得写成「工作被放弃」或「组织性搁置」：

```text
PR #193 创建 2026-07-06T19:47Z，关闭 2026-07-07T01:22Z，未合并，零评论。
关闭原因见接续 commit 8e82c4b6 的提交信息：

  replacement for closed #193 after dependent base branch deletion
  BASELINE_PRIOR remains online champion

即 PR 因依赖的基分支被删除而关闭，工作以 commit 8e82c4b6 重新落地，
该 commit 已验证为 origin/main 的祖先。
稳健性报告经 2026-07-29 的 daf935fb 归档进 main。
```

### 3.1 代码仍然可用

```text
scripts/run_w2_free_tier_2024_backtest.py          （复现入口，报告含完整命令）
src/w2/backtest/free_tier_2024.py
    _fit_offline_lambda_model              :1280
    _fit_temperature                       :1606
    _cross_season_robustness               :1465
    _rolling_origin_robustness             :1496
    build_understat_model_robustness_report :576
```

`runtime/` 下无缓存数据，重跑需重新获取 Understat 公开数据。

### 3.2 未接入生产

`src/w2/strategy/`、`src/w2/prematch/`、`src/w2/domain/` 中
**无任何**对 `free_tier_2024` 或 `_fit_offline_lambda_model` 的引用。
拟合模型是纯离线 backtest 能力，从未进入 `calibrate_lambdas()` 路径。

### 3.3 准确的状态描述

```text
模型已建立、已验证 ROBUST_IMPROVEMENT、代码已落地 main、报告已归档。
未发生的是晋级决定：该模型未替换 BASELINE_PRIOR，
且 8e82c4b6 的提交信息显式记录 "BASELINE_PRIOR remains online champion"。
稳健性报告本身也声明 "not production enablement"。

因此这不是工程失败，也不是工作丢失，而是一个从未作出的晋级裁决。
```

---

## 4. 要求

1. 按第 1 节修正审计报告三处；
2. 按 2.2 改用稳健效应量，单折值保留为历史记录；
3. 按 2.3 新增待验证假设条目，措辞须为假设；
4. 按第 3 节补充 PR #193 与代码可用性的准确记录；
5. 在 `PHASE_2_5A_FINDINGS_HANDOFF.md` 第 167 行处追加更正说明，
   **不要删除原文**，保留错误与更正的审计轨迹；
6. 结论字段仍只允许原两个值，不得因稳健性证据升级为
   `BASELINE_QUALITY_ESTABLISHED` 或 `PRODUCTION_DEFECT_CONFIRMED`；
7. 计划书的 `OWNER_DECISION_REQUIRED` 一节补一句：
   已存在一个经稳健性验证、优于当前 champion 约 0.026 nats 的离线拟合模型，
   其晋级裁决从未作出；该事实应纳入 Owner 的优先级判断。
   不得自行改变阶段顺序。

## 5. 边界

不改业务代码、不重跑 backtest、不获取 Understat 数据、不申请 Gate 0B、
不把任何拟合结果写入生产路径、不更新 Obsidian、不改 A–J 与 Gate 结构。
计划书状态保持唯一一处 `PROPOSED_NOT_AUTHORIZED`。

---

## 6. U1 对照身份更正（2026-08-29）

本交接单第 2.2 节与第 4.7 节把 `-0.026376` nats 写成相对“当前 champion”的效应，该归属错误。原文保留在上方，本节追加更正以保留审计轨迹。

本地 `main@3b7f87db` 静态复核确认：

```text
free_tier_2024.py:1375
  -> models/independent.py::predict_from_features(INDEPENDENT_POISSON)

strategy/simulate.py:128
  -> strategy/calibration.py::calibrate_lambdas
```

两条路径的函数形式、常数、输入与调用点不同，不是同一模型。因此正确记录为：

```text
Understat fitted vs 离线 predict_from_features 对照
  rolling-origin mean delta log_loss = -0.026376 nats

Understat fitted vs 生产 calibrate_lambdas champion
  NOT_MEASURED

生产 calibrate_lambdas champion 自身概率质量
  NOT_MEASURED
```

单折 `-0.035368`、四折均值 `-0.026376` 与 ECE `0.114102` 均不得归给生产 `BASELINE_PRIOR`。本更正不改变 `ROBUST_IMPROVEMENT` 只对离线 challenger-vs-offline-comparator 关系成立的事实，不升级结论字段，不授权 U2 执行或生产替换。
