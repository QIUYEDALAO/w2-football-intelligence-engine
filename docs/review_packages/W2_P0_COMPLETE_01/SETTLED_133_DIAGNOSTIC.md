# W2-P0-COMPLETE-01 — 133 注只读诊断

## 口径与边界

- 诊断日期：2026-09-02。
- 数据访问：生产 PostgreSQL，`REPEATABLE READ READ ONLY` 事务；写入为 0。
- cohort：沿用 `SETTLED_CANDIDATE_DIRECTION_RESCORE` 的最终 fixture-market opportunity 口径，共 133 注。
- 本次没有重拟合、改阈值、读写 ledger、调用 Provider 或部署。

## 注码结构确认

该 cohort 的系统结算合同是每条最终机会归一化为 **1 单位平注**：

- `dynamic_prematch_evaluations`、`recommendations`、`recommendation_locks`、`outcome_ledger` 及 evaluation payload 均没有可变 `stake`、`units` 或已存 `profit` 字段；
- 每条机会的收益按其 decimal odds 与五态结算计算：WIN 为 `odds - 1`，HALF_WIN 为其一半，PUSH 为 0，HALF_LOSS 为 -0.5，LOSS 为 -1；
- ROI 分母因此是机会数，而不是另一个可变注码总和。

这确认的是 W2 保存的 133 条统计机会采用 1 单位口径；它不声明系统之外是否存在另行记录的真实下注金额。

## 拆分结果

| 市场 | 注数 | P&L（单位） | 决定性方向命中 | PUSH | ROI |
|---|---:|---:|---:|---:|---:|
| AH | 73 | -3.685 | 35 / 70 = 50.0000% | 3 | -5.0479% |
| TOTALS | 60 | -12.510 | 21 / 52 = 40.3846% | 8 | -20.8500% |
| 合计 | 133 | -16.195 | 56 / 122 = 45.9016% | 11 | -12.1767% |

结算状态分布：

- AH：WIN 30、HALF_WIN 5、PUSH 3、HALF_LOSS 8、LOSS 27。
- TOTALS：WIN 21、PUSH 8、LOSS 31。

## 结论

流传的 `-12.2%` 没有因注码结构而作废；它是归一化 1 单位口径下 `-16.195 / 133 = -12.1767%` 的四舍五入。以上仅为既有 cohort 的只读诊断，不用于选择或调整任何阈值。
