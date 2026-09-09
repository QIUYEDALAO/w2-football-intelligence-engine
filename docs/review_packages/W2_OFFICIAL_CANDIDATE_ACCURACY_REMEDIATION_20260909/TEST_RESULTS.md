# 测试与自检结果（整改后）

```text
定向测试 scripts/quant/tests/                              46 passed
  test_factor_gate.py                                      24 passed
  test_independent_oracle.py                               19 passed
  test_factor_gate_consumers.py                             3 passed
全量回归 tests/（本工作树）              10 failed / 3071 passed / 9 skipped
全量回归 tests/（干净基线 3ac86c14）     10 failed / 3071 passed / 9 skipped
新增失败                                                   0
消失的失败                                                 0
Ruff check（改动文件）                                     All checks passed
Ruff check（全仓）                          10 errors，与基线逐条相同（差集为空）
py_compile / compileall                                    exit 0
git diff --check                     clean（两份逐字执行令副本除外，见下）
两次完整生成 byte-identical                                5 个产物全部一致
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

**仍未覆盖**：15–18、20。这些需要现役调度器与真实报价流水的端到端夹具，本轮工作区
既不连生产库写入也不启调度器，因此**如实记为未覆盖，不做替代实现**。
