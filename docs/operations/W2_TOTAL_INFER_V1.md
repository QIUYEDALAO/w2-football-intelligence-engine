# TOTAL_INFER_V1 — total 反推唯一权威公式（FROZEN）

- 文档 ID：`W2-TOTAL-INFER-V1-FROZEN`
- 任务：REL-CALIB-02（消除 total 反推三口径并存）
- 状态：**FROZEN**（2026-09-24 00:55 +08:00）
- 变更规则：本文件任何字段不得修改；公式变更 = 新文档 + 新版本号 + 新预注册。
- 关联：勘误见 `W2_CANDIDATE_C_RECALIBRATION_ERRATA_20260924.md`；预注册 `W2_CANDIDATE_C_RECALIBRATION_PREREGISTRATION_20260923.json`（v5，commit 4a803fdc，原文不改）。

## 1. 作用域

- 仅 `market = TOTALS` 的评估行；`selection ∈ {OVER, UNDER}`；`exact_line ∈ {整数, x.25, x.5, x.75}`；五态非空。
- `ASIAN_HANDICAP` 行**不参与**（其五态依赖 λ_home/λ_away 双参数，单参数反推不适定）。

## 2. 输入 / 输出

- 输入：`(selection, exact_line, p_win, p_half_win, p_push, p_half_loss, p_loss)`
- 输出：`lambda_hat`（模型隐含总进球期望）与拟合 SSE。
- **无过滤、无剔除、无截断**（grid 内必有解；不得设置 SSE 阈值过滤任何行）。

## 3. 算法

```
lambda_hat = argmin_{λ ∈ grid} Σ_{s ∈ {W,HW,PU,HL,L}} ( poisson_five_state(λ, selection, exact_line)[s] − p_s )^2
grid = [0.5, 6.0]，步长 0.005；并列时取最接近 2.6 者。
```

`poisson_five_state`：设 total ~ Poisson(λ)，`pk[k] = e^(−λ)·λ^k/k!`（k=0..15），`pk[16] = 1 − Σ_{0..15}`，`ple(q) = P(total ≤ q)`，`ib = floor(line)`：

| 线型 | selection | W | HW | PU | HL | L |
|---|---|---|---|---|---|---|
| 整数线 L | UNDER | ple(L−1) | 0 | pk[L] | 0 | 1−ple(L) |
| 整数线 L | OVER | 1−ple(L) | 0 | pk[L] | 0 | ple(L−1) |
| x.5 | UNDER | ple(ib) | 0 | 0 | 0 | 1−ple(ib) |
| x.5 | OVER | 1−ple(ib) | 0 | 0 | 0 | ple(ib) |
| x.25 | UNDER | ple(ib−1) | 0 | 0 | pk[ib] | 1−ple(ib) |
| x.25 | OVER | 1−ple(ib) | 0 | 0 | pk[ib] | ple(ib−1) |
| x.75 | UNDER | ple(ib) | 0 | 0 | pk[ib+1] | 1−ple(ib+1) |
| x.75 | OVER | 1−ple(ib+1) | pk[ib+1] | 0 | 0 | ple(ib) |

> ⚠️ x.75 行为 2026-09-24 修复版：x.75 = x.5 与 (x+1).0 各半。2026-09-23 初版脚本此分支错位一档（UNDER x.75 的 W 误用 ple(ib−1)），已作废，禁止内联复制任何旧脚本（见 ERRATA ③）。

## 4. 聚合口径

```
model_total_mean  = mean(lambda_hat)   对作用域全部行简单平均
actual_total_mean = mean(total_goals)  同批行
gap   = model_total_mean − actual_total_mean
scale = actual_total_mean / model_total_mean
```

## 5. 重算结果（单一口径）

**主口径 = schema `w2.dynamic_quote_evaluation.v3`（预注册 v4 版本 hard rule）：**

| 口径 | n | 模型 total | 实际 total | gap | scale |
|---|---|---|---|---|---|
| **v3-only（权威）** | 373 | 2.823 | 2.879 | **−0.056** | **1.020** |
| v2+v3 全量（仅对照，不入参数） | 548 | 2.836 | 3.007 | −0.171 | 1.060 |

分 selection（v3-only）：UNDER 行 2.757 vs 3.159（**−0.402**）；OVER 行 2.917 vs 2.477（**+0.440**）。无条件低估仅 0.056 球；±0.4 球为条件于选边的镜像（选择效应），非全局刻度问题。

拟合优度：整数线 / x.5 / x.75 行 SSE = 0（精确拟合）；x.25 行 SSE 全部 > 0.01（模型五态非纯 Poisson 形，疑 Dixon-Coles ρ 调整所致，lambda_hat 均值仍可用；不过滤为权威规则）。

## 6. 与历史三口径的关系

- 官方 2.84 vs 3.06（−0.22）：诊断 1,394 条口径，actual 分母更大，方向一致。
- 独立复核 2.84 vs 3.01（−0.17）：与本公式全量结果（2.836 vs 3.007，−0.171）一致，互验通过。
- 2.68 vs 2.98（−0.30）：**作废**——x.75 映射 bug + SSE≤0.01 过滤双重污染（详见 ERRATA ③）。
