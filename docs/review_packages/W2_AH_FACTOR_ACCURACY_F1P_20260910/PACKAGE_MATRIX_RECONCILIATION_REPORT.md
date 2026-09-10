# 架构 package matrix 收口报告（F1P 前置）

```text
TASK_ID   W2_ARCHITECTURE_MATRIX_RECONCILIATION_FOR_F1P_20260910
HEAD      （见回执 TASK_COMMIT）
PARENT    cf2d5725829d1319a0f4b5e41a5e2278d9526049
上一轮    8208eb3f21923da85e96b9e36c7a4cae72302861  (F1P 合同)
```

## 1. 结论

package matrix 已按当前源码图谱**机械重算**并更新 **23 个字段**，
`tests/contract/test_src_w2_package_matrix.py` **5/5 全部通过**。
治理文档 diff 为 **17 增 / 17 删**，无格式改动。

全仓失败集合从 10 条降到 **8 条**：修好的正是那 2 条矩阵测试，**新增失败为空集**。

```text
F1P_FINAL_STATE = F1P_ACCEPTED
```

## 2. 方法：不手填，由测试自己的图谱算

新增 `scripts/quant/regenerate_src_w2_package_matrix.py`。它**直接 import
契约测试本身**，复用 `_graph()` / `_packages()` / `_external_callers()` /
`_runtime_reachability()` / `_cycle_memberships()` 产出每一个数字。

因此矩阵不可能被"凑"到通过：检查器与生成器共用同一张图谱，
图谱不变则输出不变，图谱变了则重新生成。

**三列是治理判断，不是图谱事实，一律原样保留**：`role`、`decision`、`evidence`。
已用 diff 逐包核对：**没有任何一个包的这三列发生变化**。
`DEAD_PACKAGES` / `DELETED_PACKAGES` / `INVESTIGATION_REQUIRED_PACKAGES`
等叙述行同样未动。

工具还提供 `--check` 模式（只报漂移、不写文件），重算后再跑为 `DRIFT_ROWS=0`，
即结果幂等。

## 3. 更新的 24 个字段（全部由图谱重算）

### 3.1 外部 caller 计数（10 处）

```text
api.direct_callers             scripts 2 → 3
competitions.direct_callers    tests 29 → 30
domain.direct_callers          scripts 12 → 19,  tests 42 → 43
infrastructure.direct_callers  scripts 20 → 23,  tests 59 → 63
ingestion.direct_callers       tests 26 → 27
matchday.direct_callers        scripts 5 → 4,    tests 15 → 14
models.direct_callers          tests 8 → 9
prematch.direct_callers        scripts 8 → 12,   tests 37 → 39
pricing.direct_callers         tests 3 → 4
strategy.direct_callers        tests 20 → 25
tracking.direct_callers        tests 21 → 24
```

### 3.2 matchday 退役造成的图谱变化（7 处）

```text
matchday.python_file_count     12 → 10
matchday.internal_dependencies 去掉 providers, readiness, refresh
matchday.entrypoints           w2-matchday → -
providers.reverse_callers      去掉 matchday
readiness.reverse_callers      domain,matchday → domain
refresh.reverse_callers        matchday → -
refresh.cycle_membership       SCC-1 → -
refresh.scheduler_or_worker_reachability  YES → NO
refresh.api_or_web_reachability           YES → NO
```

### 3.3 指标（3 处）

```text
DEPENDENCY_EDGE_COUNT             150 → 147
RUNTIME_REACHABLE_PACKAGE_COUNT    28 → 27
OFFLINE_ONLY_PACKAGE_COUNT         12 → 13
```

`TOP_LEVEL_PACKAGE_COUNT`、`MAPPED_PACKAGE_COUNT`、`UNMAPPED_PACKAGE_COUNT`、
`CYCLE_COUNT`、`DEAD_PACKAGE_COUNT`、`DELETED_PACKAGE_COUNT`、
`ROLE_COUNTS`、`DECISION_COUNTS` 重算后与原值相同，未变。

### 3.4 只改内容，不改格式

生成器只重建数据行，**表头与对齐行原样复用**（`|---|---:|...` 的右对齐保留），
并保留块尾换行。首版曾把对齐行写成全 `---`、并把结尾的 ``` 与 END 标记粘到同一行，
已修正——现在治理文档 diff 为 17 增 / 17 删，全部是真实内容变化。
生成器另有 `--check` 模式，重算后跑为 `DRIFT_ROWS=0`。

## 4. 过期的根因：不是 F1P

矩阵最后一次更新与 matchday 退役是**同一个提交** `85d5b592`
（2026-09-06，"Runtime main-chain slim: retire dormant matchday execution surfaces"）。
该提交删掉了 `w2-matchday` console script、缩减了 matchday 的文件与依赖，
但矩阵只被改了一部分，§3.2 那 7 处一直停在退役前的状态。

§3.1 的 caller 计数则是此后陆续新增测试与脚本累积的漂移。

**这两类都与 F1P 无关，且都早于 F1P 存在。**

## 5. F1P 对图谱的唯一影响，以及它为什么合规

```text
domain.direct_callers 的 scripts 计数
  8208eb3f 之前（71cffa8d）真实值   18
  8208eb3f（F1P）真实值             19
  唯一新增引用                      scripts/quant/f1p_forward_factor_contract.py
  它 import 的是                    w2.domain.canonical_serialization
```

这次引用是**被强制要求的复用**，不是违规：

- `AGENTS.md` — "Required reuse: `src/w2/domain/canonical_serialization.py`;
  `w2.canonical-json.v2`"，并明令"Do not create a second canonical serializer"；
- `QUANT_AGENTS.md` — 同样的必需复用清单；
- Freeze A0 Binding **E2** — "quant subsystem must directly reuse
  `src/w2/domain/canonical_serialization.py`"，"A second serializer … is forbidden"。

同时：`scripts/quant/` 正是 `AGENTS.md` 与 `QUANT_AGENTS.md` 指定的 quant 隔离路径，
F1P **没有**在 `src/w2/` 下新建任何顶层包，
`test_matrix_covers_every_top_level_package_once` 在收口前后都通过。

本次收口把 domain 的 caller 记录改成真实的 19，其中就包含这一个合规的 quant caller，
**保留为合规 quant caller，未把 `scripts/quant` 移入生产包，未新增第二套序列化器**。

## 6. 一处必须报告的遗留不一致

叙述行 `CYCLE_1_MEMBERS` **仍列出 24 个成员（含 `refresh`）**，
而重算后 `refresh` 的 `cycle_membership` 已是 `-`。两者不一致。

**这是有意保留的，不是遗漏。** 原因：

- package matrix 契约测试**不断言** `CYCLE_1_MEMBERS`，只断言逐行的
  `cycle_membership`，所以收口本身不需要动它；
- `tests/contract/test_arch_p2_05_final_acceptance.py` 把
  `len(CYCLE_1_MEMBERS.split(","))` **硬钉为 24**，那是 ARCH-P2-05 已完成验收的一部分；
- 我一度把该行同步成 23，结果**打破了那条已冻结的断言**（全仓多出 1 条新增失败）。
  把 `24` 改成 `23` 属于调整阈值，本执行令 §五.4 明确禁止。

因此已把该行**恢复原值**，并在生成器里写明它被刻意排除的理由。
要真正消除这处不一致，需要重新开启 ARCH-P2-05 的验收，
**不在本任务授权范围内**，据此登记为遗留项。

## 7. 验证

```text
package matrix                    5 passed（收口前 2 failed / 3 passed）
test_arch_p2_05_final_acceptance  6 passed（未被本次收口破坏）
F1P 定向                          72 passed / 1 skipped
scripts/quant 全集                294 passed / 1 skipped
全仓                              8 failed / 3073 passed / 9 skipped
markdown 结构                     42 行表格 / 13 列 / 对齐行与围栏完好
  相对 3ac86c14 基线：修好 2 条矩阵测试，新增失败 = 空集
ruff check .                      10 errors，与 3ac86c14 基线差集为空
compileall src scripts            exit 0
git diff --check                  clean
regenerate --check                DRIFT_ROWS=0（幂等）
```

### 基线失败集合（8 条，全部保留未修）

```text
tests/contract/test_api_projection_read_authority.py::test_missing_projection_is_explicit_system_degraded_not_empty
tests/contract/test_compose_env_dedup.py::test_compose_expansion_matches_authorized_runtime_delta[path0]
tests/contract/test_compose_env_dedup.py::test_compose_expansion_matches_authorized_runtime_delta[path1]
tests/contract/test_production_odds_reads.py::test_api_dashboard_card_keeps_historical_v3_identity_immutable
tests/integration/test_future_refresh_staging_parity.py::test_preflight_fails_root_0700_runtime_for_worker_uid
tests/integration/test_future_refresh_staging_parity.py::test_preflight_passes_worker_owned_0750_runtime
tests/regression/test_stage3_contracts.py::test_no_hardcoded_real_teams_leagues_or_fixtures
tests/unit/test_ev_migration_2b.py::test_frozen_29601_rows_match_exactly
```

**新增失败集合：空。**

## 8. 冻结产物哈希

```text
                                                     收口前      收口后
W2_AH_FACTOR_ACCURACY_F0_20260910                    5/5 OK      5/5 OK
W2_AH_FACTOR_ACCURACY_F1_20260910                    6/6 OK      6/6 OK
W2_AH_FACTOR_ACCURACY_F1P_20260910                   7/7 OK      7/7 OK
W2_OFFICIAL_CANDIDATE_ACCURACY_REMEDIATION_20260909  13/13 OK   13/13 OK
F1P runner 两次运行                                   逐字节一致
```

F1P 的 6 份合同产物内容未变；本报告为该包内新增/更新的第 7 份文件。

## 9. 边界

```text
PROVIDER_CALLS = 0            PRODUCTION_DB_READS = 0
PRODUCTION_DB_WRITES = 0      DEPLOYMENT_EXECUTED = false
```

未部署、未重启 VPS、未 push、未建 PR、未新建工作区。
未修改 `src/w2/prematch`、`src/w2/strategy`、RecommendationDecisionV4、
future-refresh 业务路径、Scheduler、Dashboard、Provider allowlist、
`migrations`、生产配置。`src/w2` 整棵树变更 0 字节。
未修改 F0/F1/F1P 合同语义，未修改 `scripts/quant` 中 F1P 的计算逻辑。
未删除、skip、xfail 或弱化任何治理断言。

F1P 唯一 skip 予以保留：`market` 被合同硬钉为 `ASIAN_HANDICAP`，
构造不出"仅 market 改变但仍合法"的身份变异，属设计必然。

## 10. 状态

```text
F1P = F1P_ACCEPTED
F1R = NOT_STARTED       R1 = BLOCKED_BY_F1P（F1P 已 ACCEPTED，解锁待授权）
D1  = NOT_AUTHORIZED    W1 = NOT_STARTED
F2  = BLOCKED           F3 = BLOCKED        F4 = BLOCKED
```

F1P 接受的是**离线合同**，不是数据、不是权重、不是方向、不是部署。
F1R 需另行授权后才可开始。
