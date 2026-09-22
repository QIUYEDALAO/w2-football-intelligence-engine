# Track B 训练集负向过校准来源诊断（v1 artifact 历史记录）

日期：2026-09-22（Asia/Shanghai）  
范围：只读拆解 **v1 artifact** 与其冻结输入；该诊断记录保留为修复前证据。  
状态：修复前诊断已完成；v2 已按本报告建议重拟合。两轮均不改生产、不写生产库、不调用 Provider、不部署；生产仍为 `BASELINE_PRIOR`。

## 结论

`TOTALS/OVER` 从原始 `cal_gap=+0.0185` 变成约 `-0.084`，不是一个单纯的“isotonic 天生过拟合”现象，而是三层问题叠加：

1. **PAVA 曲线序列化/预测存在实现缺陷，是第一根因。** 合并块保存的是块内 `mean(x)`，预测时却把它当阶梯阈值。正确的阶梯阈值应是块的右边界 `max(x)`（或采用标准 isotonic 的等价插值规则）。这使同一块中低于均值的样本被错分到前一个更低的块。
2. **单一 global isotonic 混合了四种不同 selection，是 OVER 被压低的主要结构性原因。** UNDER 原始高估严重、OVER 基本准确，两者共用 global 曲线后，global 在 OVER 的概率分布上系统性偏低。
3. **`n<20` 回退和 `k=20` 放大了 global 错配。** 小格子完全使用 global；即使 `n>=20`，当前大格子的 n 多为 20–50，仍有约 29%–50% 权重落在 global。因此 shrinkage 本身不是方向来源，但把错误方向传给了大部分格子。

所以，修复前 `FITTED_CALIBRATED` artifact 只应保留为**无效离线诊断工件**，不能进入任何 holdout 验收、注册或上线流程。曲线表达与层级先验现已按本报告建议修复，并在新报告与 v2 schema artifact 中重新拟合；本报告本身仍不构成 holdout 验收。

## 1. PAVA 阈值实现缺陷

当前实现合并 PAVA block 时保存：

```python
blocks[-2] = [a.x_sum + b.x_sum, a.y_sum + b.y_sum, a.n + b.n]
return [(block.x_sum / block.n, block.y_sum / block.n)]
```

随后预测规则为：

```python
rightmost fitted block whose knot <= input
```

这两者不相容。`mean(x)` 是块的代表位置，不是块的右边界。以全局曲线的大块为例：

| block n | x 范围 | 当前 knot=mean(x) | 正确阶梯上界 | fitted y |
|---:|---:|---:|---:|---:|
| 140 | 0.3944–0.4549 | 0.4292 | 0.4549 | 0.3429 |
| 191 | 0.4854–0.5347 | 0.5117 | 0.5347 | 0.4607 |
| 199 | 0.6125–0.6555 | 0.6330 | 0.6555 | 0.5327 |
| 224 | 0.6558–0.7511 | 0.6975 | 0.7511 | 0.5446 |

例如第一行中 `x∈[0.3944,0.4292)` 的样本本应得到 `0.3429`，当前预测却落到前一个更低的 block。

量化影响：

| 范围 | 被错分行数 | 总行数 | 当前 knot 相对正确上界造成的平均预测差 |
|---|---:|---:|---:|
| 全体 | 688 | 1,396 | −0.01794 |
| TOTALS / OVER | 156 | 291 | −0.03205 |
| TOTALS / UNDER | 192 | 407 | −0.01890 |
| AH / HOME | 170 | 340 | −0.01183 |
| AH / AWAY | 170 | 358 | −0.01119 |

正确的未 shrink 全局 isotonic 在训练集上的加权均值应与实际均值一致；当前实现的 global 输出均值比实际低 `0.01794`，直接违反这一基本 invariant。因此这里首先是实现 bug，不应仅归类为统计过拟合。

## 2. 为什么 TOTALS/OVER 被压坏

对 OVER 的逐层分解：

| 指标 | 值 |
|---|---:|
| n | 291 |
| 原始模型概率均值 | 0.52025 |
| 实际正向率 | 0.50172 |
| 原始 cal_gap | +0.01853 |
| 当前 global 映射均值 | 0.40893 |
| 当前 global cal_gap | −0.09279 |
| 当前 cell 映射 cal_gap | −0.08924 |
| 当前 shrink 后 cal_gap（以未四舍五入曲线复核） | −0.08732 |

现有 JSON 报告为 `−0.08364`，与用 JSON 中已舍入 knots 回算的 `−0.08732` 有轻微差异；两者方向一致，但也说明输出精度/复算合同需要锁定。

把 PAVA 阈值缺陷仅作数学纠正、其余规则不变的诊断性反事实为：

| 映射 | OVER cal_gap |
|---|---:|
| 原始 | +0.01853 |
| 正确 block 上界、仍使用单一 global | global `−0.06074` |
| 正确 block 上界、当前 cell/global shrink | `−0.03743` |
| 正确 block 上界、改用 market×selection global 的诊断反事实 | `+0.00179` |

最后一行只是归因实验，不是候选重拟合或建议参数。它说明：修阈值 bug 只能消除部分低估；剩余主要来自**global 曲线跨 selection 混用**。冻结协议已经明确 UNDER/OVER/HOME/AWAY 必须分开，但当前实现只在 per-cell 层分开，shrink 的 global 先验仍把四类混在一起，未完全落实该设计意图。

## 3. `n<20` 回退是否带偏大格子

76 个小格子合计 484/1,396 行（34.67%）。分 selection：

| selection | 小格子数 | 小格子行/总行 | 比例 |
|---|---:|---:|---:|
| TOTALS / OVER | 19 | 122/291 | 41.92% |
| TOTALS / UNDER | 18 | 105/407 | 25.80% |
| AH / HOME | 20 | 129/340 | 37.94% |
| AH / AWAY | 19 | 128/358 | 35.75% |

当 `n<20` 时，代码令 `p_cell = p_global`，之后无论 `w=n/(n+20)` 是多少：

```text
w*p_global + (1-w)*p_global = p_global
```

因此 **k=20 对小格子实际上不起任何保护作用**；它们是 100% global fallback。OVER 小格子的正确阈值反事实 cal_gap 仍为 `−0.05911`，说明 global selection 错配足以单独把它们压坏。

小格子不会直接改变已经拟合好的大格子 cell curve，但会通过两条路径间接带偏：

1. 所有行（含 484 条小格子行）共同拟合单一 global curve；
2. 大格子继续向该 global 收缩。

OVER 的 6 个大格子 n 仅为 21–50，`k=20` 使其平均仍有约 **40.53%** 权重来自 global。四类大格子的平均 global 权重约为 35.8%–40.5%。因此错误 global 会显著影响大格子，但问题不是“小格子太多把 cell 直接污染”，而是**层级先验定义错误 + 收缩强度较大**。

## 4. 真正的过拟合来源

排除实现 bug 后，仍有以下统计过拟合风险：

### 4.1 同一训练样本拟合并评估

对 `n>=20` 的格子，正确实现的 unshrunk cell isotonic 在训练集上会机械地把 aggregate cal_gap 拉到接近 0。这是拟合恒等式，不是泛化证据。训练集 cal_gap 不能作为 Track B 通过标准。

### 4.2 cell 曲线尾部高度离散

29 个 `n>=20` 格子平均只有 6.66 个 PAVA blocks，却出现：

- 102 个 singleton block；
- 102 个输出恰为 0 或 1 的极端 block；
- 25/29 个格子的最低概率尾部由单条样本构成；
- 11/29 个格子的最高概率尾部由单条样本构成。

这是真正典型的 isotonic 尾部过拟合：aggregate gap 看似收敛，尾部函数却被单场结果决定。

### 4.3 `min_cell_n=20` 是不连续边界

`n=19` 时完全退回 global；`n=20` 时突然启用 cell curve 且 `w=0.5`。样本只增加 1 条，模型结构却发生跳变。该边界没有解决“20 条内可形成多个 singleton tails”的问题。

### 4.4 `k=20` 不是本轮负向偏差的原始来源

若 global 方向正确，收缩能降低 cell 方差。当前负向过校准是因为 global 自身对 OVER 错配，再由 `k=20` 传播；不能仅靠把 k 调大解决，调大反而会让 OVER 更靠近错误 global。调小则会放大 cell isotonic 尾部过拟合。

## 5. 等 holdout 期间能否填坑

**能填工程与预注册层面的坑，但不能用当前 TRAIN 反复试参并宣称解决。** 建议顺序：

1. **先修 PAVA 表达合同**：block 保存右边界（或直接使用经过固定版本锁定的标准 isotonic 实现）；增加以下独立断言：单调、训练样本落入原 block、未 shrink 曲线的加权预测均值等于实际均值、序列化前后预测逐点一致。当前 artifact 应标记 `INVALID_OFFLINE_IMPLEMENTATION`，不送 holdout。
2. **将 shrinkage 先验改为 market×selection global**：OVER、UNDER、HOME、AWAY 各自拥有 global curve，再让 league cell 向同 selection 的 curve 收缩。不得让 UNDER 的强高估校准形状成为 OVER 的先验。
3. **取消 n=20 的硬切换 cliff**：用连续层级方案，或至少同时冻结“最小 cell n + 最小 block n”。参数选择必须在 TRAIN 内按时间 cross-fitting/rolling-origin 完成，不能查看前瞻 holdout 后再选。
4. **收紧 isotonic 尾部**：候选方案可包括尾部向 selection-global 收缩、最小 block 样本数、概率区间 clipping/winsorization，或对 0/1 block 加 Beta pseudo-count。具体规则须预注册，不能看完 holdout 再挑。
5. **增加低方差基线**：预注册 selection-aware Platt logistic baseline（必要时再比较 beta calibration），与 isotonic 使用相同 TRAIN/时间 OOF/holdout。若 isotonic 未稳定优于 Platt，则选择更简单的映射。
6. **把 TRAIN 评价改成时间 OOF**：报告 raw、global、cell、shrink 四层的 OOF Brier/NLL/cal_gap；训练内 aggregate cal_gap 只作算法完整性检查，不作性能指标。
7. **冻结候选矩阵再等 holdout**：例如 `{selection-global Platt, selection-global isotonic, hierarchical cell isotonic}` 及固定 k/min-block 组合，先在 TRAIN 内完成选择并锁 hash；前瞻 holdout 只作一次验收。

## 验收结论

1. `TOTALS/OVER` 被压坏的直接原因已明确：**PAVA block knot 实现错误 + global 跨 selection 错配**；`k=20` 和小格子 fallback 是放大器。
2. 过拟合的具体来源已明确：同样本拟合/评价、cell 尾部 singleton 0/1、n=20 硬切换和高比例小格子；训练集符号翻转本身主要还包含实现 bug，不可全归因于统计过拟合。
3. 等 holdout 期间可以先修工程合同、重写层级先验并预注册低方差基线；**不得在当前 TRAIN 上反复调 k/min_cell 后把最优结果送 holdout**。

## 安全声明

- 本报告对应修复前版本；修复后的脚本、协议、artifact 和契约测试见同目录的 Track B 拟合报告。
- `provider_calls=0`
- `production_writes=0`
- `deployments=0`
- `calibration_ledger_writes=0`
- 未重新拟合、未生成新候选参数、未读取或评分 holdout/test
