# CANDIDATE_SPEC —— GLOBAL_ROLLING_CONFIDENCE_SHRINKAGE_V1

```text
CANDIDATE_ID     = GLOBAL_ROLLING_CONFIDENCE_SHRINKAGE_V1
CANDIDATE_SCHEMA = w2.official_candidate_confidence_shrinkage.v1
实现位置          scripts/quant/official_candidate_confidence_shrinkage.py
运行器            scripts/quant/run_official_candidate_accuracy_optimization.py
性质              纯离线研究；生产链不 import 它，它也不 import 生产链（双向断言）
```

## 1. 候选做什么

只改变完整五态概率分布的**自信程度**，其余一律原样透传。

**不改变**：选择方向、市场类型、`exact_line`、`decimal_odds`、factor verdict、
lineup 状态、model input、cashflow edge、EV-SE、结算公式、原始赛果、生产代码与配置。

代码层面有对应断言：148 条逐条比对 12 个字段全等（测试 10），
且 `T >= 1` 使得校准后分布的峰值必然不高于原分布（不可能变得更自信）。

## 2. 时序合同（PIT）

对每一条目标记录 `i`，训练集合 `j` 必须满足：

```text
utc(result_available_at(j))  <  utc(evaluated_at(i))
```

两侧一律先经 `datetime.fromisoformat()` 解析并转为 aware UTC 再比较。
naive 值按 UTC 读取（本语料所有时间戳来自 UTC 列）；**不可解析、缺失、
或两个时刻相等，一律排除**（相等不算已知）。

**禁止字符串比较**：本语料 `result_available_at` 为
`2026-08-20 02:36:31.442008+00`，`evaluated_at` 为 `2026-08-20T00:22:32.149069Z`，
第 10 个字符 `' '`(0x20) 排在 `'T'`(0x54) 之前，按文本比会把晚结算的结果判成早可用。
排序键 `temporal_key` 同样使用解析后的瞬间。

## 3. 与现有 incumbent 温度轨的区别

```text
                    incumbent（证据包内）        本候选
训练轴              按市场分开（AH / TOTALS）    全局，所有市场合并
温度网格            0.70 – 2.00                  1.00 – 2.00
方向                可锐化也可平滑                只能平滑，不能锐化
```

网格从 1.00 起是刻意的：已记录的偏差只有一个方向——预测 graded 赢面比实测高约 21pp。
给搜索一个可以「更自信」的半区，等于让它回答一个没人问的问题。

### 为什么不放在 src/w2/quant_research/

执行令允许 `src/w2/quant_research/`，我最初也放在那里，但
`tests/contract/test_src_w2_package_matrix.py::test_matrix_covers_every_top_level_package_once`
立刻失败：`src/w2` 下每一个顶层包都必须登记在
`docs/operations/architecture_convergence/W2_ARCHITECTURE_CONVERGENCE_MASTER_CHECKLIST.md`
的矩阵里。那份清单属于**架构收敛工作线**，按既有约定要 Owner 逐项验收，
不该由本任务顺手改。

改放 `scripts/quant/`（同样在执行令允许范围内）后该测试恢复通过，
且 `src/w2` **完全没有被本任务碰过**——隔离性比原方案更强：
候选连一个可被生产 import 的模块路径都不存在，运行器与测试都按文件路径加载它。
移动前后产物 hash 逐字节相同，数值不受影响。

## 4. 拟合

训练记录 < 20 条：`T_i = 1.00`（不拟合）。

达到 20 条后在冻结网格 `T ∈ {1.00, 1.01, …, 2.00}`（101 个值）上最小化：

```text
mean_multiclass_log_loss(T) + 0.10 * (log T) ** 2
```

同分（差 <= 1e-15）先取最接近 1.00 的 `T`，再取较小值。
该 tie-break 使结果只依赖训练集合，与网格遍历顺序无关（测试 7 双向验证）。

## 5. 变换

```text
q_j(T) = exp(log(max(p_j, 1e-12)) / T) / Σ_k exp(log(max(p_k, 1e-12)) / T)
```

变换后重新归一化，并**在归一之前与之后各查一次** 1e-9 概率和约束
（`normalized()` 按总和相除，只在归一后查会把漂移静默缩放掉，那道检查将永不可能失败）。

## 6. EV

一律调用仓库唯一 canonical Decimal 五态权威
`w2.domain.five_state_pricing.expected_value`。
AST 断言：本候选与运行器都不定义任何 `expected_value` / `settle` / `settlement` 函数，
且 `expected_value` 只从该模块导入（测试 9）。

## 7. 推荐层可估计条件

只有同时具备 `current_cashflow_price_edge`、`current_ev_minus_se`、`decimal_odds`
与完整五态分布，才进入推荐层评估。缺 cashflow edge 的 133 条记为
`NOT_ESTIMABLE_MISSING_CASHFLOW_EDGE`，**不猜测、不补写、不从盘口反推**。
准入判定复用生产 `economic_admission_pass`，不另写第二套经济门。
