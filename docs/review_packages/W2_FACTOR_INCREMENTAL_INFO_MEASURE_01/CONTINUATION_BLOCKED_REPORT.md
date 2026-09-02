# W2-FACTOR-INCREMENTAL-INFO-MEASURE 继续执行硬停止报告

状态：`BLOCKED_HOLDOUT_OUTCOME_INFORMATION_OBSERVED`

## Owner 裁定与恢复边界

Owner 已裁定 `18a52140` 记录的早先事件不构成 holdout 烧毁：当时只显示一条 2026 未赛 fixture，赛果字段全为 null，赛果信息量为零。本轮按 Owner 修正后的信息口径恢复执行，不重跑或修改 `00eb9556` 的冻结预注册。

## 本轮新硬停止事件

在 A1.5 实现前检查冻结 history corpus 结构时，执行了一条 `jq` 投影命令。该命令本意是读取顶层 metadata，但将 `history_rows` 整个数组投影到输出，因而显示了多条 2026 已完赛 fixture 的非空 `goals_for` / `goals_against`。

这次事件与 `18a52140` 不同：

- 确实观察到了 2026 fixture 的非空赛果。
- 违反 Owner 修正后信息规则的第 1 项明确禁止。
- 不属于“只打开混合年份文件”或“只读取未赛 null 赛果”的允许情形。

首次硬停止后，为定位 identity 探针而执行的范围过宽的仓库文本搜索，又命中了含 2026 记录的历史证据 CSV，输出中再次出现同类非空赛果与概率内容。这是停止后的第二次同类信息暴露；未用于任何因子测量，但不影响其构成违规的判定。

## 立即处置

- 发现后立即停止任务 A 的全部数据装载、实现、拟合、指标与 bootstrap。
- 第二次暴露后不再执行任何仓库内容搜索或数据读取，只允许精确的冻结文件哈希与本地 Git 回执操作。
- 未生成四因子 PASS/FAIL，未消耗 VALIDATION one-look。
- 未修改预注册文件的任何字节。
- 不进入顺序任务 B；Owner 的授权是“任务 A 交回后”开始 B，本次 A 未完成。
- 不删除、隐藏或降级本次信息暴露。

## 未产生的交付物

- A1.5 loader 与断言：未实现。
- 装载后逐年计数与断言触发计数：未生成。
- A2 / A3 / A4 测量结果：未运行。
- 定向、canonical、package matrix、Ruff 与全量 pytest：未运行。

## Stop lines

- Football Provider 调用：`0`；remaining 未查询。
- 生产写、ledger、migration、部署、GitHub/GHCR：均为 `0`。
- `CALIBRATION_VERSION`、模型参数/权重、`factor_registry.v1.json`、λ、`historical_replay_cutoff`、split 边界：改动均为 `0`。
- HOLDOUT 信息口径：非空 2026 赛果已被显示，不能对账为 0，任务必须标为 BLOCKED。

## 需要 Owner 裁定

本会话不再继续测量。若仍需执行 A，需 Owner 重新明确不受本次 holdout 信息暴露影响的执行主体/隔离方式，以及现有分支和预注册应如何处置。
