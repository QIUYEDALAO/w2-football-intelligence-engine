# W2 现役正式候选准确率优化 —— 任务 2 报告

```text
TASK_ID       = W2_OFFICIAL_CANDIDATE_ACCURACY_OPTIMIZATION_02
CANDIDATE_ID  = GLOBAL_ROLLING_CONFIDENCE_SHRINKAGE_V1
BASE_SHA      = 82b4b54f548627a7690f6400e9f8de7c0575bcf7
TASK_BRANCH   = codex/w2-official-candidate-accuracy-20260909
MODEL_CANDIDATE = READY
```

## 1. 已验证事实（进入拟合之前先复现的基线）

`shasum -c HASHES.sha256` → **13/13 OK**。冻结输入
`OFFICIAL_148_SOURCE_BUNDLE.jsonl` = `da9edb11…`。

```text
148 条正式候选                        复现
111 个 fixture                        复现
总收益 -20.375u                       复现
近 10 条 6 LOSS / 2 WIN / 1 HALF_WIN / 1 PUSH   复现
预测 graded 赢面 0.641871             复现
实测 graded 命中率 0.429630           复现
ALL_148  calibration gap -0.212242    复现
FIRST_138 calibration gap -0.201600   复现
LAST_10  calibration gap -0.361224    复现
```

incumbent 臂由本任务代码独立重算，与证据包内 `CALIBRATION_COMPARISON.json` 的
`INCUMBENT` 逐字段相等（log loss、Brier、calibration error、predicted graded rate），
这是测试 1，不是引用。

## 2. 模型层结果（全部 148 条参与评分，不筛选、不丢弃）

| 分段 | 行数 | log loss inc → cand | Brier inc → cand | \|gap\| inc → cand |
|---|---:|---|---|---|
| ALL_148 | 148 | 1.074912 → **1.020185** | 0.702589 → **0.662943** | 0.212242 → **0.169882** |
| FIRST_138 | 138 | 1.058028 → **1.007566** | 0.693551 → **0.656979** | 0.201600 → **0.160760** |
| LAST_10 | 10 | 1.307918 → **1.194335** | 0.827308 → **0.745257** | 0.361224 → **0.297587** |
| ASIAN_HANDICAP | 84 | 1.096323 → **1.026562** | 0.718633 → **0.668487** | 0.216312 → **0.166603** |
| TOTALS | 64 | 1.046810 → **1.011816** | 0.681531 → **0.655668** | 0.206321 → **0.174651** |

五个分段、三个指标，**全部改善，无一恶化**。实测 graded 命中率与结算完全未动
（每段 incumbent 与 candidate 的 actual_graded_rate 相同），改变的只有预测侧。

预测 LOSS 概率相应上升（ALL_148 0.279910 → 0.308598），
即候选确实把「过度自信」往回拉，而不是靠改结果。

温度轨迹：20 条处于 `T=1.00`（训练不足 20 条），其余落在 1.16–1.59，
**0 条触到网格上界 2.00**——网格没有替搜索做决定。训练量范围 0–144 条。

### 但这是改善，不是修好

fixture 聚类 bootstrap（10,000 次，同 fixture 两个市场成组重抽）：

| 分段 | incumbent gap 95% CI | candidate gap 95% CI | 仍排除 0 |
|---|---|---|:-:|
| ALL_148 | [-0.302809, -0.122046] | [-0.258822, -0.080880] | **是** |
| FIRST_138 | [-0.293929, -0.106778] | [-0.251681, -0.068020] | **是** |
| LAST_10 | [-0.619634, -0.071555] | [-0.551371, -0.014234] | **是** |

**校准后模型仍然显著过度自信**，区间上界离 0 还有距离。候选把缺口从约 21pp 压到
约 17pp，没有消掉它。这一点必须写在任何后续决定的前面。

## 3. 推荐层结果（只在证据足够时评估）

```text
universe                148
estimable                15
NOT_ESTIMABLE_MISSING_CASHFLOW_EDGE   133
```

| 臂 | 发出 | 阻断 | 可估计内覆盖 | graded 命中 | 盈亏 | 最大回撤 | 最长连败 |
|---|---:|---:|---:|---:|---:|---:|---:|
| incumbent | 15 | 0 | 1.000 | 0.346154 | -4.18 | 5.10 | 3 |
| candidate | 10 | 5 | 0.667 | 0.375000 | -2.30 | 3.22 | 2 |

分市场：AH 可估计 11 条（发出 11 → 8，-4.97 → -3.22）；
TOTALS 可估计 4 条（发出 4 → 2，+0.79 → +0.92）。

**这 15 条不足以判断盈利能力**，本报告不据此宣称任何收益结论。
推荐层在此只用于证明候选**没有靠删候选换指标**：可估计内仍保留 66.7%，
而模型层的改善根本没有丢弃任何一条（148/148 全部计分）。

## 4. 133 条 cashflow edge 缺失

`candidate-eval.v1` 早于该字段存在，133 条 payload 中根本没有它。
本轮**不猜测、不补写、不从盘口反推**，一律记为
`NOT_ESTIMABLE_MISSING_CASHFLOW_EDGE`。因此推荐层的一切结论只覆盖 15 条，
占全体 10.1%。这是证据缺口，不是候选的性质。

## 5. 候选是否改善

九条通过标准逐条判定，全部为真：

```text
1  ALL_148 log loss 严格下降              1.074912 → 1.020185     PASS
2  ALL_148 Brier 严格下降                 0.702589 → 0.662943     PASS
3  FIRST_138 log loss 与 Brier 未同时恶化  两者均下降               PASS
4  ALL_148 |calibration gap| 下降          0.212242 → 0.169882     PASS
5  FIRST_138 |calibration gap| 下降        0.201600 → 0.160760     PASS
6  方向/盘口/赔率/结算不变                 148 条 12 字段逐条全等   PASS
7  非靠删候选取得改善                      模型层 148/148 全计分；
                                          推荐层可估计内保留 66.7% PASS
8  推荐层同时报覆盖率与未估计原因           已报                    PASS
9  LAST_10 仅作事故回放                    未参与任何参数选择       PASS
10 两次完整运行 byte-identical             3 个产物 hash 一致       PASS
```

`TASK2_MODEL_CANDIDATE = READY`。

## 6. 是否允许后续 Shadow

**建议：可以进入 Shadow，但只在明确以下三点之后。**

1. Shadow 的目的是**继续测量校准**，不是验证收益。当前推荐层证据只有 15 条。
2. Shadow 必须重新采集 `cashflow_price_edge`。否则新样本会重复同一个缺口，
   Shadow 跑再久也无法在推荐层给出结论。
3. Shadow 期间温度必须继续按 PIT 滚动拟合，不得冻结成一个常数——
   本候选的全部合法性来自「只用过去」。

这三点属于建议，不是本任务的裁定；是否开 Shadow 由验收方决定。

## 7. 是否允许部署

**不允许。**

```text
DEPLOYABLE = false
```

理由，按重要性排序：

1. 校准后区间仍排除 0，模型依旧显著过度自信。这是改善，不是达标。
2. 推荐层只有 15 条可估计，无法支持任何上线收益判断。
3. 本候选是离线实现，**从未接入生产链**，也不应通过环境变量或默认配置接入。
4. 因子链修复（任务 1）尚未部署；在因子门未生效前改概率，只会改变一条本就
   不该发出的推荐的自信程度。

## 8. 边界

```text
PROVIDER_CALLS = 0            PUBLIC_HTTP_FETCH = 0
PRODUCTION_DB_READS = 0       PRODUCTION_DB_WRITES = 0
PRODUCTION_CONFIG_WRITES = 0  DEPLOYMENT_EXECUTED = false
SCHEDULER_RESTARTED = false   OBSIDIAN_WRITES = 0
GITHUB_PUSH = 0               PR_CREATED = false
REAL_MONEY_ACTIONS = 0
```

未新建工作区；未修改 `src/w2/prematch/`、`src/w2/strategy/`、
RecommendationDecisionV4、Scheduler、Dashboard、Provider allowlist、生产配置或迁移。
主工作区的 5 个 staged 文件与 `.workbuddy/` 前后一致，未动。

**`src/w2` 整棵树本任务一个字节都没有改。** 执行令允许 `src/w2/quant_research/`，
但在那里新建顶层包会让
`test_src_w2_package_matrix.py::test_matrix_covers_every_top_level_package_once` 失败——
`src/w2` 下每个顶层包都必须登记在架构收敛工作线的总清单里，而那份清单按既有约定
需 Owner 逐项验收，不该由本任务顺手改。候选因此改放 `scripts/quant/`
（同样在允许范围内），该测试恢复通过，隔离性反而更强：生产侧连可 import 的模块路径
都不存在。移动前后产物 hash 逐字节相同。
