# R11 —— R10 闭环确认执行结果

线上最终测量时刻：`2026-08-15T09:15:40Z`

## 结论

- R10 四项维持关闭；R11-1 已实现、测试并部署。
- R11-2 仅完成只读节奏估算与 Owner 选项说明；冻结策略保持
  `FIRST_ELIGIBLE_FREEZE_IMMUTABLE`。
- 线上仍为 `FREE_MODE_MODEL_VALIDATION_CANARY_PASS`，账本完整性为 `0/0`；
  模型质量仍为 `INSUFFICIENT_SAMPLE`。
- 本轮未调用 Provider、未新增 Statistics、未改 cadence、阈值、联赛或冻结策略，
  未启动 Formal、Lock、Production 或 Round4。

## 代码与部署身份

- source commit：`8257d009d4ac57c21d4fd1e90e391cd1446eab51`
- source tree：`4f453fe41bd5f7c19ad7630485cc5a724dbd8131`
- source archive SHA-256：`77a1ba10bcba9e541198f38d68edc4a76360a7e1c19d4ef50b373e973438a23c`
- Python image：`sha256:7e0123fa12604cb7632daedaf0182a0e692874469354d50a84139bc0ee7f90b9`
- Web image：`sha256:cf1001c9fffcad9747da26fb03eaa93050b39516900100fec183cb17e2445fb3`
- schema：`0056_floor_model_forecast_lead_time`
- warm switch：`35s`，API/Web exact release 一致，`/ready=READY`。

## R11-1：列与受哈希事实交叉校验

`ModelForecastLedgerRepository.integrity()` 现在额外校验：

1. Capture 的 `kickoff_utc`、`captured_at` DB 列必须分别等于受哈希 payload 同名字段；
2. Outcome 的 `settled_at` DB 列必须等于受哈希 payload 同名字段；
3. Outcome 表没有独立 final-score 列，因此 `payload.final_score` 与
   `authoritative_result_identity` 绑定的 `results` 权威行交叉校验。

这样即使有人绕过 append-only ORM，直接把派生列改成内部自洽值，只要它与受哈希
payload 或权威 Result 不同，完整性即 fail closed。

回归测试显式模拟了三类绕过：Capture 的 kickoff/lead-time 一起修改、Outcome 的
settled-at 修改、权威 Result 比分修改；新校验分别报 invalid。现有 9/1 线上账本在新代码下
仍为 capture `0 invalid`、outcome `0 invalid`。

## R11-2：xG-ready 赛程密度

只读口径：VPS `matchday_fixture_identities` 与
`team_xg_rolling_snapshot(as_of_fixture_id)`，按 fixture 两队快照齐全判定 xG-ready；
观察完整 ISO 周为 2026-07-20、07-27、08-03、08-10，排除 08-17 的未完整周。

| 联赛 | 每周总赛程 | 每周 xG-ready | 四周 xG-ready |
|---|---:|---:|---:|
| 瑞超 | 7 / 5 / 8 / 9 | 7 / 5 / 8 / 9 | 29 |
| 中超 | 8 / 3 / 8 / 8 | 0 / 0 / 1 / 1 | 2 |

当前实测自然速率约为瑞超 `7.25` 条/周、中超 `0.50` 条/周，合计 `7.75` 条/周。
现有 capture 分布：瑞超 `0/1/6/1`，中超 `0/0/1/0`，总计
`LT_6H/H6_TO_LT_24H/D1_TO_D3/GT_3D = 0/1/7/1`。

在“过去四周 xG-ready 速率与现有联赛内 bucket 比例保持不变”的粗估假设下：

| lead-time bucket | 估算速率/周 | 达到 30 条 | 达到 200 条 |
|---|---:|---:|---:|
| `LT_6H` | 当前观测为 0 | 无有限估计 | 无有限估计 |
| `H6_TO_LT_24H` | 0.91 | 约 33.1 周 | 约 220.7 周 |
| `D1_TO_D3` | 5.94 | 约 5.1 周 | 约 33.7 周 |
| `GT_3D` | 0.91 | 约 33.1 周 | 约 220.7 周 |

这是 `n=9` 的节奏估算，不是预注册样本承诺。首批 9 条同一时刻冻结，也会使现有
bucket 比例带有上线时点偏差。

R17 复核：上述周数只由真实赛程密度、xG-ready 覆盖与现有 lead-time 分布计算，未把
GENERAL/POSTMATCH 配额当作估算变量；配额计数缺陷不改变这些算术，但自然采集停机期间不得
把估算速率写成保证速率。

## `<6h` 是否结构性不可达

代码上不是结构性不可达：Capture 接受任意非负 lead time，线上 ledger tick 为每 600 秒，
若 fixture 身份或四字段 xG 首次在开球前 6 小时内就绪，仍会进入 `LT_6H`。

但在当前运行方式下它是低概率、无速率保证的档位：已有 xG-ready fixture 会在首次可见时
立即冻结；当前不开新 Statistics，也没有专门的临场二次冻结。因此 `0/9` 不能外推为永久
不可达，也不能给出“多少周一定达到 30 条”的有限答案。

## Owner 可选项（均未实施）

- A：接受 `<6h` 可能长期为空，只对已填满 bucket 作验证结论。代价是模型有效性范围不覆盖
  临场预测。
- B：同一 fixture 临近开球再追加独立 capture。代价是需要新 `capture_policy`、修改当前
  `(fixture_id, model_family, model_version)` 唯一约束与 identity 契约，并分别结算、分层统计；
  同场多样本还存在相关性，不能冒充独立样本。
- C：保持现有冻结策略，只报告达到门槛的 bucket，其余固定标注
  `INSUFFICIENT_SAMPLE`。代价最小，但不解决 `<6h` 样本积累。

Owner 决定前维持现状。

## 验收与零调用守卫

- focused：`11 passed`；Ruff PASS；focused MyPy PASS；
- full：`2643 passed, 14 skipped, 2 warnings`；
- full MyPy：`284 source files` PASS；Ruff PASS；`git diff --check` PASS；
- 部署前后固定口径：Provider `3118 -> 3118`、raw fixtures `167 -> 167`、
  raw Statistics `141 -> 141`、captures `9 -> 9`、outcomes `1 -> 1`；
- Canary：`9/9/1/1`、`RAW_STATISTICS_RESTORE_HASH_MATCH=true`、
  provider calls `0`、DB writes `0`。

剩余 8 条 capture 在最终测量时均未到真实完场条件，仍逐场分类为 `NOT_YET_DUE`。
heartbeat 保持 ACTIVE，继续观察 08-16 的首次真实 capture POSTMATCH 触发。
