# 已结算候选：输入重评分与方向诊断

状态：`IMPLEMENTED_PENDING_ACCEPTANCE`（生产只读；Provider 0；生产写入 0；未部署）

## 这次回答的问题

本报告不是把原下注的 EV 再算一遍，而是逐注复现：

`冻结的 Football-API 四字段 xG 输入 → 生产模拟比分矩阵 → 该盘口两侧概率 → 模型方向 → 与完赛方向对照`。

输入 CSV 是此前冻结的 `121` 条、`91` 场候选评价。结果只在原评价/输入身份冻结后读取；不用于选择参数、阈值或授权状态。

复核命令：

```bash
cd /Users/liudehua/.hermes/worktrees/w2-v1-recalibration-evidence-01
PYTHONPATH=src .venv/bin/python scripts/audit_settled_candidate_direction_rescore.py \
  --input /tmp/settled_rescore.csv \
  --output docs/review_packages/V1_RECALIBRATION_EVIDENCE_01/SETTLED_CANDIDATE_DIRECTION_RESCORE.json
```

artifact SHA-256：`92c4fd6578ae44651fafd9647caa8f7e504e416159211e77f96df7938f2e3ceb`。

## 定义

- AH 的“模型方向”按该注选定盘口的 HOME/AWAY 两侧五态结算分布计算有效概率（WIN + 0.5×HALF_WIN + 0.5×PUSH），取较高侧；AWAY 盘口线先转换为等价的 canonical HOME line，避免符号误读。
- TOTALS 同理比较 OVER/UNDER 有效概率。
- “实际方向”由同一既有结算函数从权威完赛比分得到：目标侧 WIN/HALF_WIN 记目标方向，反向侧 WIN/HALF_WIN 记反向方向，双方 PUSH 记 PUSH。
- PUSH 不计为方向正确或错误，单独列出；“决定性样本准确率”分母为非 PUSH 条数。

## 汇总

| 市场 | 条数 | 模型方向 | 实际方向 | 决定性方向正确 | 决定性准确率 | 原推荐=模型方向 |
|---|---:|---|---|---:|---:|---:|
| AH | 66 | 主 20 / 客 46 | 主 34 / 客 30 / PUSH 2 | 32 / 64 | 50.0% | 66 / 66 |
| TOTALS | 55 | 大 22 / 小 33 | 大 24 / 小 23 / PUSH 8 | 19 / 47 | 40.4% | 55 / 55 |
| 合计 | 121 | — | — | 51 / 111 | 45.9% | 121 / 121 |

原推荐方向与模型重评分方向 `121/121` 一致。因此这批数据没有发现“方向选择器把模型想选的另一边丢掉”的证据；问题在于模型方向本身在决定性样本上只有 AH 50.0%、TOTALS 40.4% 命中，且高 EV 并不等于高真实命中率。

## 按结算结果分组

| 市场 | WIN | HALF_WIN | PUSH | HALF_LOSS | LOSS |
|---|---:|---:|---:|---:|---:|
| AH | 27（方向正确 27） | 5（5） | 2（不判方向） | 7（0） | 25（0） |
| TOTALS | 19（19） | 0 | 8（不判方向） | 0 | 28（0） |
| 合计 | 46（46） | 5（5） | 10（不判方向） | 7（0） | 53（0） |

这说明“赢单为什么会被推荐”可以精确回答：赢单上，重评分方向与原推荐方向一致（51 条 WIN/HALF_WIN）；但这不是模型已验证的证明，因为同一模型在 LOSS 上也坚定地给了原方向，且样本是被原准入筛过的。

## 反事实因子诊断

### 主场项

对每注保留的 λ，构造仅移除 `applied_home_advantage_goals` 的诊断轨，保持总进球、sigma、Dixon-Coles 参数与其它生产值不变：主 λ 减半个主场项、客 λ 加半个主场项，并重新生成不确定性混合比分矩阵。

- 121 条中只有 `1` 条方向翻转：AH fixture `1492352`，生产轨主队 → 去主场项客队；该场实际方向为主队，因此去掉主场项并没有修正它。
- 其余 `120` 条方向不变；“主场项导致大量选错边”在这批数据上不成立。

### Elo、身价、首发

冻结 capture 明确记录：

- `ratings_used_in_lambda=False`：121/121；
- `squad_value_used_in_lambda=False`：121/121；
- lineup `numeric_adjustment_enabled=False`：121/121。

因此这三类反事实没有真实的当时数值可以重放，artifact 对 121 条分别标为 `NOT_AVAILABLE`。不使用赛果倒推或伪造输入；要判断它们是否能翻转方向，必须先修复并冻结生产输入可见性，再另行预注册。

### 当前实际驱动因子

121 条均为 `xG READY`，并保留四字段 xG 快照（每队 5 场窗口摘要及其组成身份）。所以该批次的真实生产方向主要由四字段 xG、固定主场项和 Poisson/Dixon-Coles 模拟驱动，而不是一个已经启用的多因子评分器。

## 结论边界与下一步

本审计证明了：原候选方向确实等于当时模型方向；在这 121 条被准入的已结算样本中，AH 决定性方向命中 32/64、TOTALS 19/47，亏损不是简单的“系统选了错误的另一边后又被 EV 过滤掉”。它同时显示，去掉主场项几乎不改变方向，Elo/身价/首发因缺失无法评估。

这不是“EV 已修复”、不是“生产有效性已验证”，也不授权直接调参。下一步应先解释 35/121 条 capture 与 checkpoint simulation identity 漂移，并补齐因子输入的 PIT 可见性；任何参数或准入修改都必须另行预注册。
