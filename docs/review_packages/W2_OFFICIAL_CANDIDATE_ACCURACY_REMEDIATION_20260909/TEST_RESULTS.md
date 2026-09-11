# 测试与自检结果（整改后）

```text
定向测试 scripts/quant/tests/                             112 passed
  test_factor_gate.py                                      46 passed
  test_independent_oracle.py                               19 passed
  test_factor_readback.py                                  11 passed
  test_offline_evidence_contracts.py                       33 passed
  test_factor_gate_consumers.py                             3 passed
全量回归 tests/（本工作树）              10 failed / 3071 passed / 9 skipped
全量回归 tests/（干净基线 3ac86c14）     10 failed / 3071 passed / 9 skipped
新增失败                                                   0
消失的失败                                                 0
Ruff check（改动文件）                                     All checks passed
Ruff check（全仓）                          10 errors，与基线逐条相同（差集为空）
py_compile / compileall                                    exit 0
git diff --check                     clean（两份逐字执行令副本除外，见下）
两次完整生成 byte-identical                                6 个产物全部一致
两次 bundle replay（含无 --raw 一次）                      manifest 逐字节一致
```

## `git diff --check` 的唯一例外

`DISPATCH.md` 与 `REMEDIATION_DISPATCH_V1_1.md` 是两份执行令的**逐字副本**，
其 SHA-256 必须分别等于 `761208c6…` 与 `463c08d8…`，因此其中 Markdown 硬换行用的
行尾双空格**不得清理**。除这两个文件外，`git diff --check` 全部干净。

## 上一轮回归范围过窄，本轮已纠正

上一轮只跑了 `-k "lifecycle or dynamic or prematch_read or projection"`（263 passed / 1 failed）
就宣布回归通过。**这个范围是错的**：本轮跑全量后发现该改动实际引入了 **18 条新失败**，
全部在 `-k` 过滤之外：

```text
tests/unit/test_candidate_notification_outbox.py          12 条
tests/unit/test_point_ev_calibration_identity.py           6 条
```

失败原因单一且真实：这两个文件的输入构造器造 `ASIAN_HANDICAP` 评估时不带任何因子裁决，
在新的 fail-closed 门下被判为 `BLOCKED_BY_FACTOR`，而断言仍写 `ANALYSIS_PICK_ACTIVE`。

处理方式：**不删除、不 skip、不 xfail、不弱化任何断言**，只在这两个文件各自唯一的输入
构造器里补上一条"已准入、方向一致"的因子裁决，并在注释里写明理由——与它们原有
`calibration_status="PRODUCTION_VALIDATED"` 那条注释同一形式。所有断言原样保留。
补完后这两个文件 66/66 全过。

## 与基线逐条一致的 10 条既有失败

```text
tests/contract/test_api_projection_read_authority.py::test_missing_projection_is_explicit_system_degraded_not_empty
tests/contract/test_compose_env_dedup.py::test_compose_expansion_matches_authorized_runtime_delta[path0]
tests/contract/test_compose_env_dedup.py::test_compose_expansion_matches_authorized_runtime_delta[path1]
tests/contract/test_production_odds_reads.py::test_api_dashboard_card_keeps_historical_v3_identity_immutable
tests/contract/test_src_w2_package_matrix.py::test_matrix_rows_match_the_current_dependency_graph
tests/contract/test_src_w2_package_matrix.py::test_matrix_callers_entrypoints_and_classifications_are_complete
tests/integration/test_future_refresh_staging_parity.py::test_preflight_fails_root_0700_runtime_for_worker_uid
tests/integration/test_future_refresh_staging_parity.py::test_preflight_passes_worker_owned_0750_runtime
tests/regression/test_stage3_contracts.py::test_no_hardcoded_real_teams_leagues_or_fixtures
tests/unit/test_ev_migration_2b.py::test_frozen_29601_rows_match_exactly
```

在**未修改、干净**的基线工作树 `w2-settlement-fix-20260909`（HEAD = `3ac86c14`，
`git status --porcelain` 为空）上跑同一条命令，得到**同一组 10 条**测试 ID 与同样的
`10 failed / 3071 passed / 9 skipped`。`test_src_w2_package_matrix` 两条在两个工作树里
先触发哪一句断言随字典/集合遍历顺序变化（`matchday` 的 `python_file_count` 或
`reverse_callers`），但根因同为矩阵文档行过期，两边一致。
**未修复**其中任何一条——整改令明确禁止修复已知既有失败。

## `scripts/` 未被改成 Python 包

初版为让测试 `from scripts.quant...` 而新增了 `scripts/__init__.py` 与
`scripts/quant/__init__.py`。这会把 `scripts/` 变成一等包，导致 Ruff 对两个**无关**的既有
脚本（`audit_v1_pit_market_shape.py`、`run_gate_a_staged_canary.py`）重新分类 import 并
新报 2 条 I001。已回退：两个 `__init__.py` 删除，oracle 测试改为按文件路径
`importlib` 加载。全仓 Ruff 结果与基线**差集为空**。

## 测试矩阵覆盖

```text
1  AH 无因子裁决 + 经济通过 → 阻断                    PASS
2  AH 因子准入失败 + 经济通过 → 阻断                  PASS
3  AH 因子/EV 方向冲突 + 经济通过 → 阻断              PASS
4  AH 因子/EV 一致 + 经济通过 → 候选                  PASS
5  TOTALS 行为不变                                    PASS
6  被阻断 AH 不进正式推荐列表                         PASS（真实消费端，见下）
7  被阻断 AH 不发候选通知                             PASS（真实消费端，见下）
8  被阻断 AH 不新增盈亏记录                           PASS（真实消费端，见下）
9  被阻断 AH 仍在正式漏斗分母                         PASS
10 历史 payload 向后兼容且显式非通过                  PASS
11 因子裁决进入 evaluation 与 attempt 身份            PASS（5 字段 × 2 身份 = 10 条参数化）
12 148 条精确复现 -20.375u                            PASS（独立 oracle，不 import w2）
13 近 10 条精确复现 -3.98u                            PASS
14 事故重放保留 5 条 = -0.88u                         PASS
19 两次完整运行 byte-identical                        PASS
```

### 6/7/8 用真实消费端函数，不用状态枚举替代

`scripts/quant/tests/test_factor_gate_consumers.py` 通过**生产写入器**
`DynamicPrematchRepository.append_evaluation` 落库，然后调用真正决定"进不进记录"的三个函数：

```text
6  w2.api.repository._official_funnel_recommendations   被否决 fixture/market 不在返回列表
7  CandidateNotificationOutboxModel（写入由 append_evaluation 完成）
                                                        被否决 opportunity 无任何事件，
                                                        且 CANDIDATE_FORMED 只有对照组一条
8  同 6 的返回行的 profit_units 列                      合计 = -1.0（只有对照组那一注）
```

每条都是**成对**测试：同一构造，一条带"已准入、方向一致"裁决，一条带
`FACTOR_EV_DIRECTION_CONFLICT`。对照组的正向断言保证消费端确实被调用——
如果消费链断了，失败的会是对照组，而不是静默通过。两个 fixture 都按 0:1 结算，
被否决那注若进了记录会再添 -1.0。

### 15–18、20 全部离线补齐

`scripts/quant/tests/test_offline_evidence_contracts.py`，只用夹具与内存数据库，
不需要现役调度器：

```text
15 温度训练的时间合同   trainable_for 逐条：早于 evaluated_at 且已权威结算 = 可训练；
                        晚于、同一瞬间、结果时间未知、不可解析、跨市场轴 = 全部拒绝；
                        14 条混合写法参数化：空格 / T / Z / +00:00 / +00 / naive /
                        真实非零时区 / 同一瞬间两种写法 / None / 空串 / 垃圾串；
                        4 条断言各写法归一到同一 UTC 瞬间；
                        1 条锁定触发泄漏的那对时间戳的方向；
                        1 条断言排序键用解析瞬间而非文本；
                        再经 build_tracks 端到端确认首条 training_rows = 0
16 fixture 聚类重抽     把 RNG 固定为「总取第一个键」，样本必须同时含该 fixture 的
                        AH(1.0) 与 TOTALS(0.0) 两条 → 实测 0.5；若按行重抽会得 1.0。
                        另断言 clusters 数 = fixture 数而非行数
17 五态归一 <= 1e-9     整条冻结温度网格 × 4 个分布，Decimal 合计全部落在
                        PROBABILITY_TOLERANCE(1e-9) 内；并断言不满足的分布会抛错
18 EV 唯一权威          AST：expected_value 只从 w2.domain.five_state_pricing 导入，
                        模块内不定义任何 EV 函数；再用 canonical 权威独立重算，
                        与 build_tracks 的 calibrated_ev 逐位相等
20 重放不改旧行         内存库快照全部表的全部行；同一 identity 连续 append 三次，
                        created 全为 False 且快照逐字不变；换裁决则新增一行，
                        旧行 payload 保持原样，总行数 2
```

**17 顺带修掉一处真缺陷**：`distribution_from` 原本先 `.normalized()` 再查 1e-9。
`normalized()` 是按总和相除，任何漂移都会被静默缩放回 1，那道检查因此永远不可能失败。
现在在**归一之前**先查一次，合同才真的有效。已确认修复后四轨产物逐字不变。

## 本轮：温度轨赛后结果泄漏已修复

`trainable_for()` 原本用**字符串**比较时间。两个字段写法不同——
`result_available_at` 是 `2026-08-20 02:36:31.442008+00`，
`evaluated_at` 是 `2026-08-20T00:22:32.149069Z`——第 10 个字符
`' '`(0x20) 排在 `'T'`(0x54) 之前，于是任何空格写法的结算时间都被判为早于任何
T 写法的评估时间。独立复算与验收方数字完全一致：

```text
被错误纳入的未来结果配对   412
受影响的目标记录          107
温度发生变化的记录          69
```

修复：`utc()` 一律 `datetime.fromisoformat()` 解析后转 aware UTC 再比较，
naive 按 UTC 读取，不可解析返回 None 并 fail-closed；排序键 `_temporal_key`
同样改用解析瞬间。**代码中不再有任何字符串时间比较。**

重算影响（发出条数与盈亏不变，被污染的是校准指标）：

```text
ALL_148   five_state_log_loss  1.126561 → 1.125916
ALL_148   calibration_error    0.264136 → 0.264053
ALL_148   multiclass_brier     0.714576 → 0.714078
LAST_10   five_state_log_loss  1.279387 → 1.278204
LAST_10   calibration_error    0.392878 → 0.392730
FIRST_138 全部指标             无变化
发出/盈亏 ALL_148 11 / -3.30u；FIRST_138 5 / -0.20u；LAST_10 6 / -3.10u   均不变
```

未改动：148 条原始结算、近 10、事故重放、独立 oracle、R9 聚类校准区间、
因子 readback 修复。分段切分在改用解析排序后逐条不变，已实测确认。

`METRICS.json` 已重新生成但**逐字节不变**：被污染的 log-loss / calibration_error /
Brier 只存在于 `CALIBRATION_COMPARISON.json`，`METRICS.json` 携带的
`track_status` / `temperature` / `calibration_by_segment` / `reproduction` /
`incident_replay` 本就不含这些量。这是自洽结果，不是漏跑。

## 身份兼容：用生产基线实测，不是自证

`attempt_identity` 现在分两条路：无因子裁决走原 **v2** preimage（逐字不变），
带裁决才走 **v3**（额外绑 `evaluation_identity_hash` 与五个裁决字段）。

验证方式是把干净基线 `3ac86c14` 与本工作树各跑一次全量，
用同一个探针记录**每一次** attempt 身份的 preimage 与结果：

```text
基线 3ac86c14   119 次绑定，全部 v2
本工作树        119 次绑定 = v2 54 + v3 65
v2 哈希出现在基线集合中                        54 / 54
v2 preimage 含 factor 或 evaluation 键          0（必须为 0）
v3 哈希与基线哈希碰撞                            0
基线 119 条 preimage 用当前代码重算              119 / 119 完全一致
```

即：**没有任何一条无裁决的 attempt 身份被改写**；v3 只出现在本轮给了裁决的 AH 夹具上。

黄金值 `test_factor_readback.py::GOLDEN_VERDICTLESS_TOTALS_ATTEMPT`
= `72110414f0a80392e5b140daec873fe8a3466f332679d6ea3a7bb23c5bc1c9aa`，
由同一夹具在干净基线 `3ac86c14` 上实跑得出，再在本工作树复现一致。

### 整改令给的 `efc5ec46…` 未能复现，原因如实说明

整改令要求旧 verdict-less TOTALS attempt 保持
`efc5ec46aefac2d8c7391d980889da7e331db88ab8a7eb8c8f95ff5e1b31a226`。
该值**不在**仓库任何位置，也**不在**基线全量套件产生的 119 条 attempt 身份里（0 命中），
因此它对应的是验收方自己的夹具，我无法反推其 preimage。

我**没有**去构造一个恰好得出该数的夹具——那是凑数，不是验证。改为：
(a) 冻结一个可由基线实跑推导的黄金值；(b) 在此写出 v2 preimage 的精确合同，
验收方可用自己的夹具直接核对：

```text
v2 preimage（键序由 canonical 序列化决定，值取自 version / context）
  attempt_identity_version = "w2.dynamic_quote_evaluation.attempt_identity.v2"
  opportunity_identity_hash
  quote_identity_hash
  model_input_hash                （取自 context，不是 version）
  lineup_input_hash
  source_event_identity
  calibration_status
  calibration_recommendation_admissible
```

若验收方提供该夹具，我可立即加为第二个黄金断言。
