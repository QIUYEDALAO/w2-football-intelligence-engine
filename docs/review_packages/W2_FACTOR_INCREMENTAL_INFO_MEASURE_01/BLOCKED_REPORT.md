# W2-FACTOR-INCREMENTAL-INFO-MEASURE 硬停止报告

状态：`BLOCKED_HOLDOUT_ACCESS_BOUNDARY_VIOLATED`

## 已完成且仍有效

- 分支从生产基线 `1de3c1ef554d00a408577f59f4864e04f1d341da` 建立。
- 预注册 JSON/MD 在任何本任务结果读取之前以独立 docs-only commit `00eb9556` 冻结。
- 冻结族大小为 4：`F3_REST_FITNESS`、`F5_RECENT_AH_COVER`、`F1_MARKET_MOVEMENT`、`F2_BOOKMAKER_INTENT`。
- 主指标、Bonferroni `alpha=0.0125`、TRAIN 2024 / VALIDATION 2025、fixture-cluster paired bootstrap 和停止规则均已冻结。

## 硬停止事件

预注册提交后，执行者在检查现有本地只读数据文件结构时运行了一个组合命令。该命令前两部分只读取冻结的 xG CSV 表头、行数和 SHA；第三部分错误地对下面文件执行了 `head -3`：

`/Users/liudehua/.hermes/worktrees/w2-model-forecast-validation-ledger/tmp/factor_model_v2/production_fixtures_exact13_2022_2026_asof_20260822T055041929427Z.jsonl`

输出的第一条 raw payload 属于 2026 fixtures discovery，内容为尚未开赛 fixture，`goals/score` 均为 `null`。没有读取 F6 字段、F6 结果、2026 已赛赛果、因子指标或候选模型结果；也没有运行拟合、bootstrap 或生成本任务任何性能数字。

但是派发合同规定 **HOLDOUT 2026 本任务完全不碰**。该边界按访问而不是按“是否看见非空赛果”解释，因此本次读取仍构成违规，不能以数据为空为理由降级。

## 处置

- 发现后立即停止 A 的全部数据读取、测量、拟合与结果生成。
- 不修改已冻结的 `PREREGISTRATION.json` 或 `PREREGISTRATION.md`。
- 不进入顺序任务 B。
- 不删除或掩盖本次访问记录；本报告作为第二个独立 docs-only 提交保存。
- 若要重启 A，需要 Owner 明确授权新的隔离执行上下文和分支处置方式；本会话不自行假设原预注册仍可继续执行。

## 未产生的交付物

- 四因子 Brier/log-loss/ECE/decomposition：未运行。
- PASS/FAIL：未判定。
- F3 delta/total 筛选：未运行。
- TRAIN/VALIDATION 实际 complete-case 样本量与因子分布：未生成。
- 全量 pytest：硬停止后未运行；不得用未执行结果填充。

## Stop lines

- Football Provider 调用：`0`；未查询或消费配额，remaining 起止均为 `NOT_QUERIED`。
- 生产写、ledger、migration、部署、GitHub/GHCR：均为 `0`。
- `CALIBRATION_VERSION`、模型参数/权重、factor registry、λ、historical replay cutoff、split 边界：改动均为 `0`。
- HOLDOUT 2026：发生一次本地 raw fixtures 文件读取，故本任务必须标为 BLOCKED，不能对账为 0。
- identity/verdict：代码与 ledger 均未修改；独立只读探针结果记录在最终交回中。
