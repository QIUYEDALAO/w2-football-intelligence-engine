# W2 现役正式候选赛后优化 — 整改后报告 v1.1

终态：**`DONE_CHAIN_FIXED_NO_SAFE_MODEL_CANDIDATE`**

## 1. 身份

```text
REMEDIATION_DISPATCH_SHA256 = 463c08d8b90b62c662aa3a89a5308cdd3336a54cc57d991e9adae0cdc22d9004  [一致]
ORIGINAL_DISPATCH_SHA256    = 761208c67c9215ccc45b4c4ff3d8bb98534dd87bea3f003854fcb0b2bf5dccb6  [一致]
BASE_SHA        = 3ac86c14fb951b93167d7a24f84a319663a6b9d9
PREVIOUS_COMMIT = 68c83c986300cc10cccf68b3b6c6d46c787f8a4a（未 amend；其父为 21c436d1）
生产实测 api_git_sha = release_id = 3ac86c14…    schema = 0070_notification_delivery_routing
```

## 2. R1–R3：因子裁决真正写入版本与身份

- `DynamicEvaluationVersion` 新增 7 个持久化字段（schema/status/direction/ev_direction/
  veto_code/identity_hash/evidence_digest）。`as_dict()` 用 `asdict(self)`，字段自动进 payload。
- `factor_input_identity_hash` 由**完整规范化 factor payload**（direction / admitted / margin /
  strength / weight_sum_used / participants / absent / admission_blockers / veto）经仓库唯一
  `w2.canonical-json.v2` 权威 `canonical_sha256` 计算。**不再**使用 `analysis_decision`、
  `WATCH`、`ANALYSIS_PICK` 或裸 `json.dumps/hashlib`。
- **身份绑定**：有裁决时才并入 identity_payload，历史与无裁决记录身份不变（append-only 安全）；
  attempt identity 绑定 evaluation identity。5 个受保护字段各自变更，
  evaluation 与 attempt 两个身份都必须改变——各 5 个参数化测试，共 10 项，全部通过。
- `ALEMBIC_MIGRATION_REQUIRED = false`：payload 为 JSON 列，版本化持久化无需新增列，
  故**不添加空 migration**。

### 本轮窄整改：读回、严格门、身份兼容

1. **读回**：`repository._version_from_payload` 之前不重建这 7 个字段，重复 append 走
   existing-row 分支时裁决整片丢成 None。现已逐字段重建，并新增真实 repository
   round-trip 测试（第二次 append 强制走 existing-row，逐字段比对；旧 AH payload 显式
   返回 `HISTORICAL_NO_FACTOR_VERDICT_IDENTITY` 且不视为通过；旧 TOTALS 不需要裁决）。
2. **严格 fail-closed**：AH 只有「ADMITTED + 无 veto 码 + identity 与 hash 同时存在且
   相等且为 64 位小写十六进制 + 方向可解析为 HOME/AWAY + 与 EV 侧一致」才放行。
   新增 `FACTOR_VERDICT_MALFORMED`，把「没有裁决」与「有裁决但不可用」分开。
   15 个参数化用例直接覆盖 NOT_ADMITTED、VETOED、垃圾状态、垃圾 veto 码、空方向、
   非法方向、identity 缺失、hash 缺失、两者不一致、非十六进制、大写十六进制、方向冲突。
3. **身份兼容**：上一轮把 `evaluation_identity_hash` 无条件塞进 attempt preimage，
   等于给每条无裁决的 TOTALS/历史 attempt 换了身份。现已分版——无裁决走原 **v2**
   preimage（逐字不变），有裁决才走 **v3**。基线与本工作树各跑一次全量并逐次记录：
   **54/54 条 v2 哈希与基线一致，v2 preimage 出现 factor/evaluation 键 0 次，
   v3 与基线碰撞 0 次**。

## 3. R4：四轨口径已纠正

```text
INCUMBENT                                 ESTIMABLE
AH_FACTOR_VETO_ONLY                       NOT_ESTIMABLE_FACTOR_IDENTITY
ROLLING_TEMPERATURE_ONLY                  ESTIMABLE_ON_CASHFLOW_COMPLETE_SUBSET
AH_FACTOR_VETO_PLUS_ROLLING_TEMPERATURE   NOT_ESTIMABLE_FACTOR_IDENTITY
ALL_AH_BLOCKED_CONSERVATIVE_BOUND         DIAGNOSTIC_ONLY_NOT_A_FACTOR_VETO_COUNTERFACTUAL
```

前版把「删除全部 84 条 AH」当成因子反事实并据此断言「因子绕过不是主因」。
该轨已改名为诊断轨，**该结论已撤回**。

## 4. R5：温度轨口径已纠正

```text
cashflow edge provenance   PERSISTED_IN_FROZEN_PAYLOAD 15
                           NOT_ESTIMABLE_MISSING_CASHFLOW_EDGE 133
缺失原因                    EVALUATION_POLICY_V1_PREDATES_FIELD
                           （candidate-eval.v1 133 条 / v2 15 条，v2 才引入该字段）
```

已按授权范围（精确 148 个 evaluation_id，无全表扫描）尝试恢复：opportunities 表无该列，
evaluation payload 亦无 `required_cashflow_price_edge`，确认不可恢复，**不重算不猜测**。

| 分段 | universe | 可估计 | 发出 | 全体覆盖 | 可估计内覆盖 | 盈亏 |
|---|---:|---:|---:|---:|---:|---:|
| ALL_148 | 148 | 15 | 11 | 0.074 | **0.733** | -3.30 |
| FIRST_138 | 138 | 5 | 5 | 0.036 | **1.000** | -0.20 |
| LAST_10 | 10 | 10 | 6 | 0.600 | 0.600 | -3.10 |

前版把 133 条缺证据写成「温度轨阻断 92.6%」，**该结论已撤回**。真实情况是可估计子集内
保留 73.3%，样本量远不足以判断温度能否识别好的那批。

## 5. R9：校准统计已按冻结 cluster 合同完成

10,000 次 fixture 聚类 bootstrap，同 fixture 的 AH/TOTALS 一起重抽，
seed 由 task_id 的 canonical v2 hash 推导：

| 分段 | 预测 graded | 实测 | gap | 95% CI（聚类） | 排除 0 |
|---|---:|---:|---:|---|:-:|
| ALL_148 | 0.6419 | 0.4296 | **-0.2122** | [-0.3009, -0.1238] | 是 |
| FIRST_138 | 0.6421 | 0.4405 | **-0.2016** | [-0.2922, -0.1108] | 是 |
| LAST_10 | 0.6390 | 0.2778 | -0.3612 | [-0.6165, -0.0706] | 是 |

**这是本轮唯一被聚类区间支持的主结论**：总体预测赢面显著高于实测，且在未被查看过的
前 138 条上同样成立。Poisson-binomial z 与手工设计效应降为 secondary diagnostic。
`[0.65,1.01)` 高自信桶标为 `POSTHOC_EXPLORATORY`，不作预注册主门。

温度网格未因碰到上界而扩展：`rows_at_T_2_00_ceiling = 0`，`rows_at_T_1_00 = 40`
（低于 20 条训练下限），其余落在 1.23–1.39 区间。

## 6. R6–R8：自包含证据、独立 oracle、六场 LOSS、三段输出

- **R6**：`result_available_at` 148/148 已入正式 manifest；四轨脚本只读 Git 内受 hash 覆盖的
  artifact。本轮进一步提交 `OFFICIAL_148_SOURCE_BUNDLE.jsonl`（148 行，
  `sha256 = da9edb11…`，只含 `build_rows` 消费的字段，无凭据/连接串/Provider 原始响应体），
  `official_candidate_manifest.py` 默认只读该 bundle，`--raw` 仅用于从受限原件重建。
  **正式重放不再需要任何 Git 外文件**，且由 bundle 重建的 manifest 与原 manifest 逐字节相同。
- **R7**：新增独立 oracle，`ast` 断言其不 import `w2`。从比分/market/selection/exact line/
  decimal odds 逐条重算：**`SETTLEMENT_MATCH = 148/148`、`PROFIT_MATCH = 148/148`**。
  19 条黄金向量覆盖 quarter line、half win、half loss、push 与主客两侧。
  该 oracle 发现并纠正了一处语义：**`exact_line` 是所选一方的盘口，不是恒定主队盘口**——
  按主队盘口解释会在恰好 25 条 AWAY 记录上不一致。
- **R8**：manifest 补齐 `result_available_at`、policy version、cashflow provenance、
  factor participants/absent/verdict identity、lineup 状态与数值贡献、
  `model_capture_at` / `model_age_seconds` / `lead_bucket`；不可恢复项保留字段名并写明
  `NOT_RECONSTRUCTIBLE` 原因。六场 LOSS 报告见 `LOSS_ROOT_CAUSE_REPORT.md`，
  逐场区分 `CONFIRMED` / `INFERENCE` / `NOT_RECONSTRUCTIBLE`。
  三段输出（全 148 / 前 138 / 近 10）已在 `CALIBRATION_COMPARISON.json` 与 `METRICS.json` 中给出。
- 近 10 事故重放：5 条 Owner 标注冲突（4 LOSS / 1 WIN），保留 5 条
  （1 HALF_WIN / 2 LOSS / 1 PUSH / 1 WIN）合计 **-0.88**，与 Owner 数字精确一致；
  证据等级固定为 `OWNER_ANNOTATED_INCIDENT_REPLAY`，**未**升级为已验证历史因子反事实。

## 7. 已撤回的结论

1. ~~「因子绕过不是主因」~~ —— 依据是诊断轨，不是因子反事实。
2. ~~「温度校准不能识别好的那批」~~ —— 依据把缺证据当成了拒绝。

可保留的是：**当前证据显示总体预测 graded 赢面显著高于实测，是需优先处理的校准风险。**

## 8. 上一轮回归范围过窄，本轮已纠正

上一轮只跑 `-k "lifecycle or dynamic or prematch_read or projection"` 就宣布回归通过。
本轮跑全量后发现该改动实际引入 **18 条新失败**，全部落在那个过滤之外
（`test_candidate_notification_outbox.py` 12 条、`test_point_ev_calibration_identity.py` 6 条）：
两个文件的输入构造器造 AH 评估时不带任何因子裁决，在新的 fail-closed 门下被判
`BLOCKED_BY_FACTOR`。已在**不删除、不 skip、不 xfail、不弱化任何断言**的前提下，
给这两个构造器补上"已准入、方向一致"的因子裁决并注明理由。

```text
本工作树全量        10 failed / 3071 passed / 9 skipped
干净基线 3ac86c14   10 failed / 3071 passed / 9 skipped
新增失败 0，消失的失败 0，测试 ID 逐条相同
全仓 Ruff 与基线差集为空
```

测试矩阵 6（不进正式推荐列表）、7（不发候选通知）、8（不新增盈亏记录）已用
**真实消费端函数**覆盖，不用状态枚举替代：经生产写入器落库后直接调用
`w2.api.repository._official_funnel_recommendations` 与候选通知 outbox。

15–18、20 本轮全部离线补齐（`test_offline_evidence_contracts.py`，夹具 + 内存库）。
其中 17 顺带修掉一处真缺陷：`distribution_from` 原本先 `.normalized()` 再查 1e-9，
而 `normalized()` 按总和相除会静默把漂移缩放回 1，那道检查永远不可能失败；
现在在归一之前先查一次。修复后四轨产物逐字节不变。

**测试矩阵 1–20 现已全部有断言。**

## 9. 精确变更文件

本轮（`68c83c98` → 整改 commit）：

```text
M  src/w2/prematch/lifecycle.py                  严格 fail-closed + attempt v2/v3 分版
M  src/w2/prematch/repository.py                 _version_from_payload 重建 7 个裁决字段
M  scripts/quant/official_candidate_manifest.py  自包含 source bundle
M  scripts/quant/official_candidate_four_track.py  trainable_for + 1e-9 合同修复
M  scripts/quant/tests/test_factor_gate.py       15 条严格 fail-closed 参数化
A  scripts/quant/tests/test_factor_readback.py   readback round-trip 与身份黄金
A  scripts/quant/tests/test_offline_evidence_contracts.py  矩阵 15–18、20
A  docs/review_packages/.../OFFICIAL_148_SOURCE_BUNDLE.jsonl
M  docs/review_packages/.../FACTOR_BYPASS_REPAIR_REPORT.md
M  docs/review_packages/.../HASHES.sha256
M  docs/review_packages/.../REPORT.md
M  docs/review_packages/.../SOURCE_IDENTITY.json
M  docs/review_packages/.../TEST_RESULTS.md
```

上一轮（`21c436d1` → `68c83c98`）：

```text
M  src/w2/prematch/lifecycle.py, read_model_projection.py
M  scripts/quant/official_candidate_manifest.py, official_candidate_four_track.py
M  scripts/quant/tests/test_factor_gate.py
M  tests/unit/test_candidate_notification_outbox.py, test_point_ev_calibration_identity.py
A  scripts/quant/independent_settlement_oracle.py
A  scripts/quant/tests/test_independent_oracle.py, test_factor_gate_consumers.py
A  docs/review_packages/.../{LAST10_INCIDENT_REPLAY.json,LOSS_ROOT_CAUSE_REPORT.md,
                             METRICS.json,REMEDIATION_DISPATCH_V1_1.md}
M  docs/review_packages/.../{CALIBRATION_COMPARISON.json,FACTOR_BYPASS_REPAIR_REPORT.md,
                             HASHES.sha256,OFFICIAL_148_MANIFEST.jsonl,
                             OFFICIAL_148_RECOMPUTATION.json,REPORT.md,TEST_RESULTS.md}
```

**未新增** `scripts/__init__.py` / `scripts/quant/__init__.py`：把 `scripts/` 变成一等包会让
Ruff 对两个无关既有脚本重新分类 import 并新报 2 条错误，已改为按文件路径 importlib
加载被测模块。四个 `_*.json` 生产原始导出**不在 Git 内**，只作为受限原件保留在
`/Users/liudehua/Desktop/W2文档/evidence/W2_OFFICIAL_148_RAW_20260909`；
本轮起它们**不再是验收脚本的必需输入**。

## 10. 边界

```text
REAL_PROVIDER_CALLS = 0        PUBLIC_HTTP_FETCH = 0
PRODUCTION_DB_READS = READ_ONLY_EXACT_148_REMEDIATION_ONLY（按 148 个 evaluation_id 精确查询）
PRODUCTION_DB_FULL_TABLE_SCAN = 0（本轮）
PRODUCTION_DB_WRITES = 0       PRODUCTION_CONFIG_WRITES = 0
DEPLOYMENT_EXECUTED = false    SCHEDULER_RESTARTED = false
OBSIDIAN_WRITES = 0            GITHUB_PUSH = 0    PR_CREATED = false
REAL_MONEY_ACTIONS = 0
```

首轮已发生的一次范围偏离（读 8,477 行后收窄到 148）按整改令要求保留记录于
`SOURCE_IDENTITY.json`；本轮所有生产查询均按已冻结的 148 个 evaluation_id 精确补证。
