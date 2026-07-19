# W2 V3-07 AH 正式能力离线证据协议

本协议在执行评估前冻结。它只定义如何判断证据是否足够，**不改变**模型因子、阈值、方向、canonical performance cohort，也不会开启 AH/OU 正式推荐、锁单或 production。

## 输入与边界

- 截止时点：`2026-07-20T00:00:00Z`；输入是不可变 JSONL 导出，报告记录 canonical JSON SHA-256。
- 仅 `canonical_cohort=true`、非 legacy ambiguous、具备 fixture 与 identity trace、`as_of_utc <= kickoff_utc` 的 AH 样本。
- 每行必须同时拥有模型与去水市场的五态 AH 结算分布：WIN、HALF_WIN、PUSH、HALF_LOSS、LOSS；还须有选择赔率、已结算结果、市场/模型版本。
- 历史身份不完整的记录继续隔离，绝不由本协议恢复或修改 ledger。

## 固定时间划分与指标

| 集合 | 时间 | 最少样本 |
| --- | --- | ---: |
| train | 至 2024-12-31 | 300 |
| validation | 2025 年 | 100 |
| holdout | 2026-01-01 至冻结时点 | 100 |

holdout 绝不用于任何调参。评估在同一 fixture、同一盘口、同一已知时点比较模型和 devig 市场：多类 log loss、Brier、ECE、AH 期望回报、CLV 概率变化与 1,000 次（seed=7）配对 percentile bootstrap 95% CI。市场是比较基准，**不是独立证据因子**。

holdout 同时按联赛、盘口区间、主/客选择、distinct evidence groups（0、1、2、3+）分层；评估 factor ablation（仅在导出中有冻结 ablation 分布时）及模型-市场残差与证据组数的 Pearson 相关。每个分层至少 30 条，否则诚实标注样本不足。

## 固定结论规则

`PASS_FOR_SHADOW` 必须同时满足三段最小样本、完整 holdout CLV、有效 bootstrap，且 holdout 模型相对 devig 市场的 log loss/Brier 差值均不大于 0，log-loss 差值 95% CI 上界不大于 0。

样本、字段、CLV 或 bootstrap 不足时为 `INSUFFICIENT_EVIDENCE`；样本充分但 no-harm 不通过时为 `FAIL`。无论哪种结论，当前代码均强制 `formal_ah_enabled=false`。阶段结束后必须人工审批，不能自动进入开启正式能力的工作。
