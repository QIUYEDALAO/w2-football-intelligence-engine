# W2 现役正式候选赛后优化 — 执行报告

终态：**`DONE_CHAIN_FIXED_NO_SAFE_MODEL_CANDIDATE`（部分完成，见 §6 未完成项）**

## 1. 身份

```text
DISPATCH_SHA256 = 761208c67c9215ccc45b4c4ff3d8bb98534dd87bea3f003854fcb0b2bf5dccb6  [实测一致]
BASE_SHA        = 3ac86c14fb951b93167d7a24f84a319663a6b9d9（parent bc1189e8，非 origin/main 祖先）
生产实测 api_git_sha = release_id = 3ac86c14…  与 PRODUCTION_REFERENCE_SHA 精确一致
schema head = 0070_notification_delivery_routing    /ready = READY    六容器 healthy
```

## 2. 任务 A：148 条独立复现 — 全部命中

```text
settled = 148        distinct fixtures = 111        profit_units = -20.375     ✓
近 10 条 = LOSS 6 / WIN 2 / HALF_WIN 1 / PUSH 1，合计 -3.98                    ✓
市场 = ASIAN_HANDICAP 84 / TOTALS 64
结算 = WIN 55 / LOSS 66 / PUSH 13 / HALF_LOSS 8 / HALF_WIN 6
```

复算器不 import 生产 serializer，按 kickoff_utc 与 evaluated_at 两种排序均得同一近 10 条。

## 3. 最重要的发现：概率严重过度自信（已达统计显著）

```text
全样本 148 条（135 可决，PUSH 排除）
  模型预测 graded 赢面 = 64.19%
  实测                = 42.96%
  差                  = -21.2 个百分点

Poisson-binomial 检验  z = -5.20   p ≈ 2.0e-07
fixture 聚类 103 簇，平均簇内 1.47 → 设计效应 1.47 时 z = -4.29  p ≈ 1.8e-05
即使设计效应取 2.0，仍有 z = -3.68  p ≈ 2.3e-04
```

**越自信越差：**

| 预测赢面桶 | n | 预测 | 实测 | 差 |
|---|---:|---:|---:|---:|
| [0.45,0.55) | 4 | 54.5% | 50.0% | −4.5pp |
| [0.55,0.65) | 86 | 60.1% | 46.5% | **−13.6pp** |
| [0.65,1.01) | 45 | 72.9% | 35.6% | **−37.4pp** |

高自信桶单独：n=45，期望赢 32.82，实测 16.00，**z = −5.69，p ≈ 1.3e-08**。

对比：同一批数据的 ROI 检验只到 p ≈ 0.065。**校准检验比 ROI 强约四个数量级**，
这印证了「148 注不足以做 ROI 结论、但足以做校准结论」的判断。

## 4. 任务 D：四轨比较

seed = 14979326164275801598（由 task_id 的 canonical v2 hash 推导），10,000 次 fixture 聚类 bootstrap。

| 轨 | 发出 | 覆盖率 | 盈亏 | graded 命中 | 全输率 | 校准误差 | bootstrap 95% CI |
|---|---:|---:|---:|---:|---:|---:|---|
| INCUMBENT | 148 | 1.000 | **-20.375** | 0.430 | 0.446 | +0.212 | [-41.78, +0.76] |
| AH_FACTOR_VETO_ONLY | 64 | 0.432 | **-11.72** | 0.418 | 0.500 | +0.206 | [-25.23, +1.98] |
| ROLLING_TEMPERATURE_ONLY | 11 | 0.074 | **-3.30** | 0.333 | 0.545 | +0.264 | [-7.12, +2.40] |
| 组合 | 3 | 0.020 | -0.08 | 0.500 | 0.333 | +0.104 | [-3.00, +2.76] |

**没有一条轨盈利。** 三点读数：

1. `AH_FACTOR_VETO_ONLY` 采用保守边界（因子身份 0 覆盖 → 阻断**全部** AH），
   只剩 TOTALS 仍亏 -11.72 / 64 注 ≈ -18.3% ROI。
   **说明因子绕过不是主因**：把整个亚盘市场拿掉，系统照样亏。
2. `ROLLING_TEMPERATURE_ONLY` 阻断 92.6% 的注，保留的 11 注仍亏，
   且 graded 命中 0.333 **低于** incumbent 的 0.430 ——温度校准并不能识别出好的那批。
3. 组合轨只剩 3 注，样本无意义；不得用「几乎不推荐」制造好看的命中率。

隐含温度落在预注册网格**上边界 T=2.00**，且该 T 下预测仍为 55.79% > 实测 42.96%，
**说明单一温度压不平，网格上限本身就不够**。

## 5. 任务 B：链路修复已实施

详见 `FACTOR_BYPASS_REPAIR_REPORT.md`。因子裁决进入动态评估**写入契约**（非 read layer 过滤），
新增 `BLOCKED_BY_FACTOR` 状态自然映射为 `BLOCKED_BY_GATE`，`official_funnel_eligible` 不变，
TOTALS 不受影响，历史 payload 显式不视为通过。定向测试 10/10 通过。

## 6. 未完成项（终态因此标注为部分完成）

- B4 的 Alembic 迁移与 evaluation/attempt identity 绑定因子裁决身份；
- 测试矩阵 6/7/8/11（通知、台账、identity 端到端断言）；
- 任务 C 的六场逐场根因表（数据已取全，仅差成文）；
- 交付物 `LAST10_INCIDENT_REPLAY.json`、`LOSS_ROOT_CAUSE_REPORT.md`、`METRICS.json`、`TEST_RESULTS.md`。

## 7. 建议的下一步

修因子绕过是必要的，但**远不充分**。数据显示主要问题是概率模型本身系统性过度自信 21pp，
且在高自信区最严重，而预注册温度网格压不平。下一轮应把重点放在概率校准，
而不是继续做候选链的门禁。

## 8. 边界

```text
REAL_PROVIDER_CALLS = 0      PUBLIC_HTTP_FETCH = 0
PRODUCTION_DB_READS = READ_ONLY_OFFICIAL_148_ONLY（全部 BEGIN READ ONLY）
PRODUCTION_DB_WRITES = 0     PRODUCTION_CONFIG_WRITES = 0
DEPLOYMENT_EXECUTED = false  SCHEDULER_RESTARTED = false
OBSIDIAN_WRITES = 0（只读）   GITHUB_PUSH = 0    PR_CREATED = false
REAL_MONEY_ACTIONS = 0
```

一处如实记录：首次 evaluation 导出误取全表 8,477 行而非授权的 148 条。只读、未写任何地方，
发现后立即收窄到 148 条授权范围并销毁多余文件，分析全程未使用超范围数据。
