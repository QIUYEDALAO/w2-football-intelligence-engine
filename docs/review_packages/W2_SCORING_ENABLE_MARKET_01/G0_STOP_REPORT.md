# W2-SCORING-ENABLE-MARKET-FACTORS · G0 硬停止报告

状态：`STOPPED_READY_COUNT_ZERO / NO_CONFIGURATION_CHANGE`

分支：`codex/w2-scoring-enable-market-01`  
生产基线：`1de3c1ef554d00a408577f59f4864e04f1d341da`

## 1. G0 生产只读快照

最终合并查询的事务时间为 `2026-09-03T03:53:40.344627Z`，隔离级别
`REPEATABLE READ`，`transaction_read_only=on`，结束时执行 `ROLLBACK`。

生产最新实际有 `454` 张 `analysis-card:shadow:v1:*`，不是派发时旧快照的 452 张。

| 运行时 contribution ID | READY | UNAVAILABLE | READY source_group | UNAVAILABLE source_group |
|---|---:|---:|---|---|
| `F1_MARKET_MOVEMENT` | **0** | 454 | 无可测行 | null（454） |
| `F2_BOOKMAKER_DIVERGENCE` | **0** | 454 | 无可测行 | null（454） |

生产 feature contribution 使用的 F2 ID 是 `F2_BOOKMAKER_DIVERGENCE`，不是 registry
中的 `F2_BOOKMAKER_INTENT`。生产 454 张 card 中没有任何
`F2_BOOKMAKER_INTENT` contribution。

由于 READY 集为空，无法从 READY 行实测验证 source_group 是否为 `market`。本地 registry
将 F1/F2 policy 声明为 `market`，但这不能替代生产 READY evidence；生产现有 UNAVAILABLE
contribution 的 source_group 均为 null。

按任务硬停止条件“若 F1/F2 READY 场数为 0，立即停止”，本任务在 G0 终止，未执行 G1。

## 2. 当前与反事实分布

当前生产持久化分布：

| independent_signal_count | 当前 fixture 数 | F1/F2 计入 scoring 的反事实 |
|---:|---:|---:|
| 0 | 429 | 429 |
| 1 | 0 | 0 |
| 2 | 0 | 0 |
| 3 | 16 | 16 |
| 4 | 9 | 9 |
| 5 | 0 | 0 |
| 合计 | 454 | 454 |

F1/F2 没有 READY contribution，故纯计算反事实没有可加入的 market 信号，分布完全不变。
当前 pricing shadow 状态为：

- `INSUFFICIENT_INDEPENDENT_FACTORS`：429；
- `SIMULATION_READY`：25。

因此当前 `DATA_INSUFFICIENT` 为 429，反事实仍为 429；从
`DATA_INSUFFICIENT` 变为可出结果的 fixture 为 **0**。

## 3. G1 未执行及额外代码事实

未修改 `factor_registry.v1.json`，未向 `AUTHORITATIVE_SIGNAL_GROUPS` 加入 `market`。
源码复核还发现派发现状漏列一道现有门：`team_score.py` 的
`ALLOWED_INDEPENDENT_FACTORS` 同样不含 F1/F2。即使未来只改 registry 和 authoritative
group，F1/F2 仍会在构造 `all_factors` 时被过滤。若采集恢复后重新派发接入任务，必须同时
处理这个允许集合，并先统一 `F2_BOOKMAKER_DIVERGENCE` 与
`F2_BOOKMAKER_INTENT` 的 canonical ID；本报告不预授权这些修改。

由于 G1 未发生，G2 的典型 fixture 权重占比、team score、fallback fair_ah/edge_ah
前后对照不存在；将“无修改”包装成前后变化会误导。当前任务只证明开关不是眼下首要卡点。

## 4. 设计后果

若未来把市场数据纳入 team score，再拿该 score 与市场比较，会形成部分循环：用市场信息
描述市场。对于下注产品，这会实质性高估自身边际；对于当前退役下注语义后的分析产品，
影响较小，但 market group 仍不能被称为独立于市场的证据。本次没有因分析产品定位而绕过
READY=0 的采集硬门。

## 5. Identity 与 stop lines

本地基线实测：

- `CALIBRATION_VERSION = w2.formal.lambda_baseline_prior.v1`
- calibration identity：`21960a863fd93dcae01ff8804e73fd0ef9d8360e8f2b8073313f226322e5db71`
- verdict：`APPROVED_VALIDATED`

G0 后无代码或配置修改，因此 λ、概率、`CALIBRATION_VERSION`、identity 均未发生变化。

| 项目 | 结果 |
|---|---|
| 生产写 / ledger / migration / 部署 | 0 |
| GitHub / GHCR | 0 |
| Football Provider | 0 |
| registry / 权重数值 / F4 / F7 / 其他因子字段 | 0 改动 |
| `INDEPENDENT_SIGNAL_MINIMUM` / `REQUIRED_SIGNAL_GROUPS` | 0 改动 |
| λ / `calibrate_lambdas` / `CALIBRATION_VERSION` / split | 0 改动 |
| 系数拟合 | 0 |

本分支仅新增本报告，不需要执行因配置变更而要求的 G2 全量回归；配置变更从未发生。
