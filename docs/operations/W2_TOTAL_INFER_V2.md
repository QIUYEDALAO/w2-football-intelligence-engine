# TOTAL_INFER_V2 — total 反推唯一权威公式（DRAFT 待 Owner 冻结）

- 文档 ID：`W2-TOTAL-INFER-V2-DRAFT`
- 日期：2026-09-25（+08:00）
- 状态：**DRAFT_AWAITING_OWNER_FREEZE**（验收发现 V1 一处半态方向错误，按变更规则新起版本；Boss 冻结前 V1 仍为现行口径，但 UNDER x.25 行结果按本文件修正值使用）
- 取代：`W2-TOTAL-INFER-V1-FROZEN`（V1 的 UNDER x.25 半态定义作废，其余条款继承）
- 变更规则：本文件冻结前不得修改；冻结后公式变更 = 新文档 + 新版本号 + 新预注册

## 1. 与 V1 的唯一差异

**UNDER x.25 在 total = ib（floor(line)）时的半态方向：V1 写 HALF_LOSS（错），V2 修正为 HALF_WIN。**

依据（标准亚盘 quarter-line 结算规则）：UNDER x.25 = 各半押 UNDER x.0 与 UNDER x.5。total = ib（例：2.25 球盘进 2 球）时，押 x.0 部分走盘、押 x.5 部分赢 → 半走盘半赢 = **HALF_WIN**。OVER x.25 同位置为半走盘半输 = HALF_LOSS（V1 此项原本正确，不变）。

| 线型 | selection | W | HW | PU | HL | L |
|---|---|---|---|---|---|---|
| 整数线 L | UNDER | ple(L−1) | 0 | pk[L] | 0 | 1−ple(L) |
| 整数线 L | OVER | 1−ple(L) | 0 | pk[L] | 0 | ple(L−1) |
| x.5 | UNDER | ple(ib) | 0 | 0 | 0 | 1−ple(ib) |
| x.5 | OVER | 1−ple(ib) | 0 | 0 | 0 | ple(ib) |
| x.25 | UNDER | ple(ib−1) | **pk[ib]（V2 修正：HW）** | 0 | 0 | 1−ple(ib) |
| x.25 | OVER | 1−ple(ib) | 0 | 0 | pk[ib] | ple(ib−1) |
| x.75 | UNDER | ple(ib) | 0 | 0 | pk[ib+1] | 1−ple(ib+1) |
| x.75 | OVER | 1−ple(ib+1) | pk[ib+1] | 0 | 0 | ple(ib) |

## 2. 错误发现经过与实锤证据

- 发现：Codex Gate 2 审计标注「.25 半态规格冲突」，未擅改冻结文件、未伪造结果。
- 实锤（kimi 独立重算，2026-09-25）：v3-only 的 UNDER x.25 共 54 行，用 V1（半输）映射反推时 **54/54 行 SSE > 0.01**（五态系统性对不上）；用 V2（半赢）映射 **54/54 行 SSE = 0**（完美拟合）。
- 归因更正：V1 文档中「x.25 行 SSE>0.01 疑 Dixon-Coles ρ 调整所致」的表述作废——真因是半态方向映射错误，非 ρ。

## 3. 数值影响登记（重算结果）

| 指标 | V1（含错误） | V2（修正） | 变化 |
|---|---|---|---|
| v3-only 模型 total 均值（n=373） | 2.8230 | 2.8194 | −0.004 球 |
| gap（模型 − 实际 2.8794） | −0.056 | −0.060 | −0.004 |
| **scale = actual/model** | 1.020 | **1.021** | +0.001 |

**主结论不变**：v3 的 total 刻度无系统性低估（gap 量级 0.06 球、<1σ），REL-CALIB-06「total_scale = 1.0、Track A 关闭」的决策不受本修正影响。

## 4. 继承条款（V1 未变部分全部继承）

作用域（仅 TOTALS 行、五态非空）；算法（argmin λ∈[0.5,6.0] step 0.005 五态 SSE，无过滤无剔除）；聚合口径（简单平均）；拟合优度报告规则；FROZEN 变更规则。

## 5. 附带：AH 反解误差声明（闭环 Codex 标注的 NOT_ESTIMABLE）

kimi 参数化扫描（2026-09-25）：total ∈ {1.5~4.5} × rho ∈ {0, 0.05, 0.10, 0.15} × delta ∈ {−0.8~0.9} 共 140 点 × 3 线型（−0.25/−0.5/−0.75），**DC 矩阵二分反解 vs Skellam 逐字反解的 delta 偏差 ≤ 0.091 球（P90 ≤ 0.070）**，对 success 概率影响 ≤ ~3pp。

处理：生产统一以 **DC 矩阵反解为唯一定义**（与生产五态生成同源），Skellam 逐字式仅作交叉验证手段；本声明替代「NOT_ESTIMABLE」标注。
