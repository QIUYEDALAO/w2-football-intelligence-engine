# SCHED-DEDUP-01 报告

日期：2026-08-24
状态：本地实现与离线验证完成；未部署、未写生产数据库

## 结论

冻结的 6 个投影事件上，修复前后 6 份 canonical artifact 的字节长度与 SHA-256 逐项完全一致。性能从 `483.830291s wall / 123.767577s CPU / 1,097 SQL / 24 analysis cards` 降至 `218.899288s / 65.136922s / 527 SQL / 12 cards`：墙钟下降 `54.7570%`，CPU 下降 `47.3716%`，SQL 下降 `51.9599%`。

这次只改变读取与重建方式：模型、门槛、求积、推荐状态、序列化格式和对外 payload 均未改。

## 根因与修法

### 1. 写后重复完整读取

`AnalysisCardCanaryMaterializer.build()` 对 shadow artifact 本来就会计算两张卡：

1. `analysis_card`：写前投影；
2. `read_time_reference`：同一冻结读集上的独立逻辑重算，用于 shadow reconciliation。

SCHED-PEAK-02 的冻结演练又执行了 `initial build + post-write rebuild`，所以是 `2 builds × 2 cards = 4 cards/event`，6 个事件即 24 张卡。

代码复核还发现真实 writer 原来有两处事务内 full build：一处在 evaluation/lineup 写后重建 artifact，另一处在 checkpoint flush/readback 后再次生成 current-read card。因此真实写路径最多是 `initial + 2 post-write builds = 6 cards/event`；上一轮 24-card 演练只覆盖了其中一次写后重建。

写路径实际改变的分析卡输入只有 `dynamic_prematch` lifecycle。修复后：

- 初始 build 的两次业务计算仍保留；
- 写后只用 `lifecycle_in_session()` 的两个定界查询读取 evaluation 与 supersession；
- 把 lifecycle 增量合入写前 artifact，沿用原函数重算 `shadow_reconciliation / projection_hash / artifact_hash`；
- checkpoint flush 后仍执行 schema/hash/source identity 校验，并把 persisted card 与增量 current-read 做原有 reconciliation；
- 不再重读 fixture、盘口、xG、阵容、估值和模拟链。

单元测试用同一事务比较“旧 full rebuild”与“新增量 refresh”，canonical bytes 完全相同。

### 2. 任务级 Round3 批量预取

剩余墙钟的主项是 Round3 market lineage：旧路径在事件循环内逐事件查询。冻结批次有 6 个事件、5 个 fixture，旧路径执行 6 次；新路径使用仓库原有的 `<=64 fixtures` 接口一次预取，按 fixture 分桶后交给 materializer。排序仍由原查询的 `fixture_id / captured_at / observation_id` 保证，每场仍单独执行 `MAX_ROUND3_EVIDENCE_ROWS_PER_FIXTURE` 和 cross-fixture scope 校验。

批量查询本身仍耗时 `208.122108s`，说明其成本主要随 lineage 行数与 JSON/ORM 物化增长，不是网络往返。它是本轮之后最明确的剩余瓶颈，但不影响本次去重成立。

### 3. 1,097 次 SQL 中的 N+1 判定

口径分三类，避免把所有重复语句都叫 N+1：

- 完全重复读取：同一事件阶段、同一 SQL、同一参数，修复前 734 次；修复后 343 次。主要来自完整 build 重复执行与单卡内部重复 authority 读取。
- 可证实的 event-loop N+1：Round3 对 6 个事件逐项查询，可合并为 1 次；多出的 5 次已消除。
- 参数型 N+1：同一事件阶段、同一 SQL family、多个参数集合，并且代码已有列表/`IN` 查询能力。修复前多出 42 次，分布如下；去掉一次完整 build 后剩 21 次。

| SQL family | 修复前 N+1 多余调用 | 修复后 | 后续批量化方式 |
|---|---:|---:|---|
| `provider_team_identity_crosswalks` | 14 | 7 | 为 home/away 建一次 request-scoped crosswalk map |
| `team_xg_match` | 12 | 6 | 复用现有 `team_xg_matches_for_w2_teams([home, away])` 的一次结果 |
| `raw_payload` | 12 | 6 | endpoint/scope 合并为一次 bounded `IN` 读取后分桶 |
| `team_lineup_baselines` | 2 | 1 | home/away 一次批读 |
| `structured_lineup_players` | 2 | 1 | 两个 lineup snapshot id 一次批读 |

这 21 次剩余参数型 N+1 在本次 profile 中合计数据库 driver 时间不足 `0.25s`，不是当前 208 秒主瓶颈。本轮不扩大到 analysis service 的跨模块请求上下文重构；后续若处理，应建立显式 `ProjectionReadSet`，而不是全局缓存或固定联赛/球队数。

## 字节不变量

| fixture | event | bytes | canonical bytes SHA-256 |
|---|---|---:|---|
| 1492341 | ODDS_CHANGED | 641159 | `559b1f14e9732700150c211b300a815f8f2cff1a08d41d8ab2ae27f957caf925` |
| 1492341 | LINEUP_CHANGED | 644164 | `9afed376b843061cbb5f442047770b95792bc582aa0de116bc2de6831eb2fc62` |
| 1492347 | ODDS_CHANGED | 616580 | `36d541ca43a2fca186031d479ad0ecc959d22453ac2408a1a28c5d1862b10b2c` |
| 1492349 | ODDS_CHANGED | 521872 | `fcd3853477e91a4d5b0c1e19133a719a6a1398a93da6cddc61305127ca14e0ea` |
| 1492342 | ODDS_CHANGED | 530456 | `4831dffacb42655b5066f41604162012b945825a887ae57e22748bbdb1bdc937` |
| 1492348 | ODDS_CHANGED | 585570 | `66fad1b2ac6b4f32c8964707aab4a1a7f51ec646d628dbccc9fb4778df4a2c6d` |

`--check` 对 profile digest、manifest、I/O stop line、逐事件 byte hash、A/B 数字与 evidence 派生关系交叉验证。把 evidence 的 `wall_seconds.after` 单字段增加 `0.000001` 并重算总 digest 后，检查仍以 `COMPARISON_MISMATCH:wall_seconds` 失败。

## 安全与边界

- Provider calls：0
- production database writes：0
- `outcome_ledger` SQL reads：`24 → 12`；本任务未禁止该只读输入，profile 从 SQL family 实数统计，不再硬编码为 0
- deployment：否
- 基准库：从生产只读 `pg_dump` 一次恢复出的临时隔离 clone；A/B 均强制 `transaction_read_only=on`
- 生产 release、schema、worker concurrency：未改
- 临时扩容 2 仍不是长期容量基线；08-28 coverage 撤除后的容量重测应使用本修复之后的代码，并继续记录 Round3 单次批读成本

## 剩余风险

1. 一次批量 Round3 lineage 仍占本次优化总墙钟约 95%，需要单独研究查询计划、返回列和物化边界；不得把它与本次纯去重捆绑。
2. writer 的增量路径依赖明确事实：当前写单元只改变 dynamic evaluation/supersession/lineup plan/checkpoint，分析卡中唯一受影响的 current-read 字段是 lifecycle。新增其他会反向影响分析输入的写操作时，必须扩展 targeted read set 或恢复 fail-closed。
3. 本轮未部署；线上容量改善尚未成立，须部署决策后以真实高峰槽验收。
