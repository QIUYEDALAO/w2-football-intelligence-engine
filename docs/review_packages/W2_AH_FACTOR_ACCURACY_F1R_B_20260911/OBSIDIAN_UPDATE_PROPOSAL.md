# Obsidian update proposal — F1R-B

**Proposal only. Claude Code did not write the Vault.** `OBSIDIAN_WRITES = 0`.
Vault path: `/Users/liudehua/Documents/Obsidian/知识库/20-项目/W2`.
Maintained by Codex after independent acceptance (R1-B).

Below is what changed factually this round, phrased so it can be pasted or
rewritten as the maintainer prefers. Nothing here should be recorded before
R1-B accepts the work.

---

## 1. AH 四因子来源时点 — 状态从「全部未证明」改为「三证一阻」

F1R-A0 记录的结论是 F5/F6 的真实来源时点都无法证明。F1R-B 重新做了只读源码追踪，结论要分开：

| 因子 | 来源时点 | 状态 |
|---|---|---|
| F3_REST_FITNESS | `canonical_team_match_history.kickoff_utc`（赛程事件时间） | 已证明 |
| F9_TRUE_XG | `team_xg_rolling_snapshot.as_of_time` | 已证明 |
| F6_H2H | `canonical_team_match_history.endpoint_capture_id` → `matchday_endpoint_captures.provider_captured_at` | **已证明（本轮新结论）** |
| F5_RECENT_AH_COVER | 无 | **仍阻塞** |

F6 的证明链：`FactorModelRemediation._seed_history` 先 `_persist_capture` 记下
`provider_captured_at = response.captured_at`，再把该 payload 里每一条
FINISHED 赛事绑定到同一个 `capture_id`，交给 `_upsert_history_fixtures` 写进
history 行。因此该行指向的正是「已经把该场报成完场」的那一次 Provider 读取。

需要同时记下被否决的字段：`canonical_team_match_history.captured_at` 被设为
`FactorModelRemediation.now`（物化运行起始时钟），早于它所指向的 Provider 读取，
用它当证据时间会声称结果比实际更早可知。

## 2. F5 阻塞原因（四条，均为代码事实）

1. 生产环境没有任何写入方把 `source/source_group/collection_status =
   canonical_historical_ah_fact / CANONICAL_AH_FACT` 三个标记写进
   `runtime/independent_signal_backfill/raw_payloads/`；唯一写入方
   `write_raw_artifact` 只存 `{endpoint, captured_at, payload}`。全仓 `src/`
   里 `CANONICAL_AH_FACT` 只出现在两个**读取**点。
2. `canonical_historical_ah_facts` 表在 `src/` 内无任何读取方。
3. 该表只有 `kickoff_utc` 与 `quote_captured_at`；后者是赛前赔率捕获
   （`formal_ah` 只接受 `snapshot_semantics == "CAPTURED_AT"`），不证明结算何时可知。
4. `results.confirmed_at` 有两个写入方语义（`materialize_results` 的最早终态
   Provider 捕获时间，与 `:792` 的 `datetime.now(UTC)`），且没有任何列可区分，
   因此该列本身不证明任何观测语义。

结论：F5 保持 fail closed，记录为 `INSUFFICIENT_DATA` / 零权重，不用 kickoff、
推算完场时间、查询时间、文件 mtime 或无语义证明的 `confirmed_at` 代替。

## 3. 新增 factor_version 权威

`src/w2/domain/factor_versions.py` 是唯一映射（有测试扫描全仓证明无第二份）：

```text
F3  w2.factor.f3_rest_fitness.rest_days_diff.v1
F5  w2.factor.f5_recent_ah_cover.settled_cover_rate_diff.v1
F6  w2.factor.f6_h2h.mean_goal_diff.v1
F9  w2.factor.f9_true_xg.rolling_net_xg_diff.v1
```

每条版本钉住其 builder 函数源码的 SHA-256 与该 builder 的 READY reason code；
改算法不改版本会让锁定测试失败。`factor_registry.v1.json` 的 `version: 1`
是治理生命周期版本，不是计算版本，本轮明确不复用。

**重要限制（建议原样记录）**：版本声明在 builder 旁边，不是由 builder 运行时随
contribution 带出。原因是 F1 冻结包 `F1_SOURCE_INVENTORY.jsonl` 钉住了
`team_factors.py` 与 `live_factors.py` 的文件哈希，改这两个文件会破坏冻结包。
补偿控制是上面的算法哈希锁定测试。

## 4. 新增表与迁移（未执行）

`migrations/versions/0071_forward_ah_factor_observation.py` 新增
`forward_ah_factor_observations`，additive，只建一张表。回滚在表非空时拒绝
（`FORWARD_AH_FACTOR_OBSERVATION_DOWNGRADE_WOULD_DESTROY_FACTS`），已写入的
append-only 事实不会被回滚删除；populated 情况走 forward-compatible disable 路径。

在隔离数据库验证过 upgrade → 写入 → readback → 重复 upgrade → 非空回滚被拒 →
空表回滚 → 重复回滚。**本机没有 PostgreSQL，隔离库是临时目录里的 SQLite 文件库**，
这一点在 `ISOLATED_REPLAY_RESULT.json` 里如实标注，未包装成 PostgreSQL 结果。

## 5. 边界（未变）

```text
REAL_PROVIDER_CALLS = 0    PRODUCTION_DB_READS = 0    PRODUCTION_DB_WRITES = 0
LIVE_CAPTURE_ENABLED = false    DEPLOYMENT_EXECUTED = false
TRACK1_FORWARD_CLOCK = NOT_STARTED    HISTORICAL_148_BACKFILLED = false
SCHEDULER/DASHBOARD/V4/PROVIDER_ALLOWLIST = 未修改
```

终态 `BLOCKED_BY_UNPROVABLE_FACTOR_SOURCE`（因 F5）。F2、F3、D1、W1、Shadow 均未解锁。
