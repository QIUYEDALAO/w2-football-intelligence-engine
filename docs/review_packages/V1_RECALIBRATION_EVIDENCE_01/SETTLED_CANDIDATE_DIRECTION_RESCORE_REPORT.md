# 已结算候选：输入重评分与方向诊断

状态：`IMPLEMENTED_PENDING_ACCEPTANCE`（生产只读；Provider 0；生产写入 0；未部署）

## 这次回答的问题

本报告不是把原下注的 EV 再算一遍，而是逐注复现：

`冻结的 Football-API 四字段 xG 输入 → 生产模拟比分矩阵 → 该盘口两侧概率 → 模型方向 → 与完赛方向对照`。

输入 CSV 是此前冻结的 `121` 条、`91` 场候选评价。结果只在原评价/输入身份冻结后读取；不用于选择参数、阈值或授权状态。模型方向与 EV 来自每条 evaluation 自己冻结的五态分布、赔率和 `current_ev`；不拿更早的 model capture 或后来覆盖的 shadow checkpoint 替代评价当时的计算口径。

复核命令：

```bash
cd /Users/liudehua/.hermes/worktrees/w2-v1-recalibration-evidence-01
PYTHONPATH=src .venv/bin/python scripts/audit_settled_candidate_direction_rescore.py \
  --input /tmp/settled_rescore.csv \
  --output docs/review_packages/V1_RECALIBRATION_EVIDENCE_01/SETTLED_CANDIDATE_DIRECTION_RESCORE.json
```

artifact SHA-256：`15218931849bb7416250b7211787504be6077fa1e8f790edd5331db58db288e9`。

## 定义

- evaluation 保存的是被推荐方向的完整五态分布；反方向按 `WIN↔LOSS`、`HALF_WIN↔HALF_LOSS`、`PUSH` 不变精确镜像。
- “较高概率方向”按有效概率 `WIN + 0.5×HALF_WIN + 0.5×PUSH` 比较；它与按赔率形成的推荐方向是两个概念，不能混为同一个门。
- EV 按生产五态现金流公式逐注复算：`WIN×(odds−1) + HALF_WIN×0.5×(odds−1) − HALF_LOSS×0.5 − LOSS`。
- “实际方向”由同一既有结算函数从权威完赛比分得到：目标侧 WIN/HALF_WIN 记目标方向，反向侧 WIN/HALF_WIN 记反向方向，双方 PUSH 记 PUSH。
- PUSH 不计为方向正确或错误，单独列出；“决定性样本准确率”分母为非 PUSH 条数。

## 汇总

| 市场 | 条数 | 模型方向 | 实际方向 | 决定性方向正确 | 决定性准确率 | 原推荐=模型方向 |
|---|---:|---|---|---:|---:|---:|
| AH | 66 | 主 20 / 客 46 | 主 34 / 客 30 / PUSH 2 | 32 / 64 | 50.0% | 66 / 66 |
| TOTALS | 55 | 大 22 / 小 33 | 大 24 / 小 23 / PUSH 8 | 19 / 47 | 40.4% | 55 / 55 |
| 合计 | 121 | — | — | 51 / 111 | 45.9% | 121 / 121 |

原推荐方向与较高有效概率方向 `121/121` 一致；保存的 EV 也由保存的五态分布与赔率 `121/121` 在 `1e-6` 内精确复现。因此这批数据没有发现“方向选择器把模型想选的另一边丢掉”或“展示 EV 与保存分布不一致”的证据；问题在于模型方向本身在决定性样本上只有 AH 50.0%、TOTALS 40.4% 命中。高 EV 是概率与价格的现金流比较，本来就不等于高胜率。

## 按结算结果分组

| 市场 | WIN | HALF_WIN | PUSH | HALF_LOSS | LOSS |
|---|---:|---:|---:|---:|---:|
| AH | 27（方向正确 27） | 5（5） | 2（不判方向） | 7（0） | 25（0） |
| TOTALS | 19（19） | 0 | 8（不判方向） | 0 | 28（0） |
| 合计 | 46（46） | 5（5） | 10（不判方向） | 7（0） | 53（0） |

这说明“赢单为什么会被推荐”可以精确回答：赢单上，重评分方向与原推荐方向一致（51 条 WIN/HALF_WIN）；但这不是模型已验证的证明，因为同一模型在 LOSS 上也坚定地给了原方向，且样本是被原准入筛过的。

## 输入身份纠正

此前报告把历史 evaluation 与该场“开赛前最后一个”shadow checkpoint 比较，得到 `35/121` 条 simulation hash 不同，并误称为生产 identity 漂移。该关联不是 immutable child 关系；所有 121 条均指向各自的 model capture，且实测 `evaluation.model_forecast_capture_identity_hash == model_capture.capture_identity_hash` 为 `121/121`，`evaluation.model_input_hash == model_capture.model_input_manifest_hash` 为 `121/121`。因此 `35/121` 是审计假阳性，已撤回；latest-checkpoint 比较仅保留为非权威诊断。

### V1 / V2 边界

Elo、身价、首发属于 V2 扩展，不是 V1 必需输入。本 V1 artifact 不对这些因子做反事实，也不把它们的缺失列为 V1 缺陷。

### 当前实际驱动因子

121 条均为 `xG READY`，并保留四字段 xG 快照（每队 5 场窗口摘要及其组成身份）。这正是 V1 的设计范围：四字段 xG、固定主场项和 Poisson/Dixon-Coles 模拟；V2 才扩展其它因子。

## 结论边界与下一步

本审计证明了：原候选方向、evaluation 冻结的五态分布与保存 EV 自洽；在这 121 条被准入的已结算样本中，AH 决定性方向命中 32/64、TOTALS 19/47，亏损不是简单的“系统选了错误的另一边后又被 EV 过滤掉”。此前基于错误 checkpoint 的“去掉主场项”反事实已撤回；V2 因子不进入 V1 结论。

这不是“EV 已修复”、不是“生产有效性已验证”，也不授权直接调参。V1 下一步按已冻结预注册校准 xG/主客强弱与盘口链；首发、身价等 V2 因子不纳入 V1 修复。任何参数或准入修改都必须另行预注册。
