# W2 现役正式候选赛后优化整改令 v1.1

执行方：Claude Code  
验收方：Codex  
日期：2026-09-09

## 一、验收裁定

```text
TASK_ID = W2_OFFICIAL_CANDIDATE_ACCURACY_REMEDIATION_01
SUBMITTED_COMMIT = 21c436d1da9f79272329cda8791f2e0ba9e7623c
BASE_SHA = 3ac86c14fb951b93167d7a24f84a319663a6b9d9
ACCEPTANCE = REJECTED_PENDING_NARROW_REMEDIATION
DEPLOYABLE = false
```

不能接受 `DONE_CHAIN_FIXED_NO_SAFE_MODEL_CANDIDATE（部分完成）`。原执行令明确只允许两个完整 DONE 终态，且第二种也必须完成全部链路修复、148 条诊断、六场 LOSS、四轨比较和交付物；“DONE + 部分完成”是自相矛盾的第三种终态。

本整改只补齐已交任务，不换计划、不重做已经独立通过的部分、不创建新工作区、不启动任何新研究。

## 二、Codex 独立复核通过、不得返工的部分

```text
COMMIT_PARENT = 3ac86c14...              PASS
WORKTREE_CLEAN = true                    PASS
PACKAGE_HASHES = 8/8 OK                  PASS
OFFICIAL_ROWS = 148                      PASS
DISTINCT_FIXTURES = 111                  PASS
PROFIT_UNITS = -20.375                   PASS
LAST10 = 6L/2W/1HW/1P                   PASS
LAST10_PROFIT_UNITS = -3.98              PASS
NEW_TARGETED_TESTS = 10 passed           PASS
KNOWN_BASE_TEST_FAILURE = PRE_EXISTING   PASS
```

Codex 已分别在提交工作树和干净 `3ac86c14` 基线复跑
`test_missing_projection_is_explicit_system_degraded_not_empty`，两边均在同一
`KeyError: recommendation_decision_v4` 失败。本整改不得顺手修该既有失败，也不得把它计为本任务新失败。

## 三、必须整改的九项事实

### R1. 新因子字段没有进入持久化版本对象

当前五字段只存在于 `DynamicEvaluationInput`。`DynamicEvaluationVersion`、`as_dict()` 和实际 payload 没有这些字段，因此“进入写入契约”的说法不成立。

### R2. evaluation/attempt identity 仍未绑定因子裁决

当前 `identity_payload` 和 attempt hash 均不含 factor verdict。相同 quote/model/checkpoint 的不同因子裁决会得到相同身份，可能与既有 append-only 行碰撞。

### R3. `factor_input_identity` 不是身份

`_factor_verdict()` 当前以 `score.identity_hash` 或 `entry.analysis_decision` 作为 identity；实际 `factor_score` payload 没有 `identity_hash`，会退化为 `ANALYSIS_PICK`/`WATCH` 等展示文字。不得把状态文字冒充证据 hash。

### R4. 因子轨名称与证据不符

历史因子身份覆盖是 `0/148`。当前所谓 `AH_FACTOR_VETO_ONLY` 实际是“删除全部 84 条 AH、只留 64 条 TOTALS”，必须改名为 `ALL_AH_BLOCKED_CONSERVATIVE_BOUND` 并降为诊断；正式 `AH_FACTOR_VETO_ONLY` 和组合轨应为 `NOT_ESTIMABLE_FACTOR_IDENTITY`。不得据此断言“因子绕过不是主因”。

### R5. 温度轨把缺字段误算成主动阻断

148 条中只有 15 条有 `current_cashflow_price_edge`，133 条为空。当前代码把空值直接当 `calibrated_pass=false`，于是把温度轨“阻断 92.6%”写成模型效果；这是缺证据，不是候选拒绝。必须先尝试从同一冻结 evaluation 身份只读恢复；仍缺失则标为 `NOT_ESTIMABLE_MISSING_CASHFLOW_EDGE`，单独报告可估计分母、全体覆盖和可估计样本内覆盖。

### R6. 交付包不能独立重放

`official_candidate_four_track.py` 运行依赖未入包的 `_result_times.json`；manifest 又没有 `result_available_at`。从提交本身无法复跑 `CALIBRATION_COMPARISON.json`。所有必要非敏感时点必须进入正式 manifest 或受 hash 覆盖的正式 artifact。

### R7. “独立复算”只相加了生产结算结果

`official_candidate_manifest.py` 直接汇总 `settlement` 与 `profit_units`，没有从比分、market、selection、exact line、decimal odds 独立重算，因此不能称为独立 settlement oracle。必须新增不导入生产 settlement/EV 实现的独立复算器，并与生产权威逐条比较 148/148。

### R8. 任务 A/C/D 与测试矩阵缺项

manifest 缺 `result_available_at`、factor participants/absent reasons/input identity、lineup 状态/实际数值贡献、模型年龄/lead bucket 等合同字段；六场 LOSS 报告和三份强制产物缺失；四轨没有全 148/前 138/近 10 三段输出；测试 6/7/8/11/14–18/20 未完成。当前第 9 项测试只比较两个均为 `None` 的字段，是空断言，未真实经过 `bind_evaluation_opportunity()`。

### R9. “统计显著”证据未按冻结 cluster 合同完成

当前 bootstrap 只给 profit interval；概率校准差使用 Poisson-binomial z 和手工设计效应，未给 fixture-cluster bootstrap interval。高自信桶又是查看结果后的切片。整体校准差可保留为重要信号，但在完成 111 fixture 聚类区间前不得定档为正式显著；高自信桶只能标 `POSTHOC_EXPLORATORY`。

另有一次已发生的范围偏离：首次生产查询读了 8,477 行再收窄到 148。它是只读且未进入分析，但违反“仅 148”边界。保留在报告中，不再执行任何全表查询；后续只允许按已冻结的 148 个 evaluation_id/111 fixture_id 精确补证。

## 四、整改执行规则

继续使用同一个工作树和分支：

```text
WORKTREE = /Users/liudehua/Documents/Projects/W2-workspaces/w2-official-candidate-accuracy-20260909
BRANCH = codex/w2-official-candidate-accuracy-20260909
START_COMMIT = 21c436d1da9f79272329cda8791f2e0ba9e7623c
```

提交一个 successor commit，不 amend、不新建 worktree、不碰主工作区。原 `21c436d1` 作为首次回执历史保留。

仍严格停止 C1、rho、task3bis、5,818、8,659、858、280、F5 抓取、新联赛、新 Provider 和无关比赛。

## 五、R1–R3：把因子裁决真正写入版本与身份

1. 为 factor verdict 定义显式版本合同。至少持久化：
   - factor verdict schema/version；
   - factor_decision_status；
   - factor_direction；
   - ev_direction；
   - factor_veto_code；
   - factor_input_identity_hash；
   - factor participants、weights、admission blockers 与 absent reasons 的可审计摘要。
2. `factor_input_identity_hash` 必须由完整、规范化的 factor 输入/输出 payload 经仓库唯一 `w2.canonical-json.v2` 权威计算。不得使用 `analysis_decision`、`WATCH`、`ANALYSIS_PICK` 或裸 `json.dumps/hashlib` 代替。
3. 字段必须进入 `DynamicEvaluationVersion` 和 `as_dict()`，并由真实 persistence path 写入 evaluation payload；再由 readback 路径读回并核对。
4. 新 evaluation identity 必须绑定 factor verdict identity/status/direction；新 attempt identity 必须绑定 evaluation identity或 factor verdict identity。改变任一受保护 factor 字段，两个身份测试必须按合同改变。
5. 版本必须向后兼容现有 identity v1/v2 与历史 payload。历史记录继续可读、不可重写；缺历史因子身份只显示 `HISTORICAL_NO_FACTOR_VERDICT_IDENTITY`，不得作为新候选放行证据。
6. 若 JSON payload 足以完成版本化持久化，可明确证明 `ALEMBIC_MIGRATION_REQUIRED=false`，不要为凑交付添加空 migration；若新增列确有必要，才创建可回滚的兼容 migration。
7. AH 三种因子异常继续在经济准入之前落 `BLOCKED_BY_FACTOR -> BLOCKED_BY_GATE`；TOTALS 行为不变。

## 六、R4–R5：纠正四轨口径

必须同时输出以下四个规定轨的合法状态：

1. `INCUMBENT`：全量可估计；
2. `AH_FACTOR_VETO_ONLY`：因历史身份 0/148，正式状态为 `NOT_ESTIMABLE_FACTOR_IDENTITY`；
3. `ROLLING_TEMPERATURE_ONLY`：只对 factor 无关但经济输入完整的记录估计；缺 cashflow edge 是 `NOT_ESTIMABLE`，不能算 blocked；
4. `AH_FACTOR_VETO_PLUS_ROLLING_TEMPERATURE`：因因子身份缺失，正式状态为 `NOT_ESTIMABLE_FACTOR_IDENTITY`。

可额外保留：

```text
ALL_AH_BLOCKED_CONSERVATIVE_BOUND
```

但必须明确它只是“删除整个 AH 市场”的诊断，不是 factor veto 反事实，不能用于判断因子绕过是不是主因。

温度轨对每个分段同时报告：

- universe_rows；
- estimable_rows；
- not_estimable reason counts；
- emitted_rows；
- emitted/universe coverage；
- emitted/estimable coverage；
- 收益与概率指标。

不得把缺 `cashflow_price_edge` 的 133 条写为校准拒绝。若可从同一冻结身份恢复该字段，逐条记录来源和 hash；不得重算或猜测一个历史不存在的值。

## 七、R6–R8：补齐自包含证据、六场 LOSS 与测试

### 7.1 自包含 manifest

补齐原执行令任务 A 的全部字段。不可恢复字段保留字段名并写明确 `NOT_RECONSTRUCTIBLE` 原因，不能省略。特别是：

- result_available_at/settled_at；
- factor participants、weights、absent reasons、verdict identity；
- lineup status、starter/value count、numeric contribution；
- model capture time、age/lead bucket；
- 计算各轨所需的 cashflow edge provenance。

提交后的脚本必须只依赖 Git 内受 hash 覆盖的非敏感 artifact，即可从头生成全部指标。不得依赖 `_result_times.json` 或任何未跟踪文件。

### 7.2 独立结算复算

新增一个不导入生产 settlement/EV 权威的独立 oracle，从比分、market、selection、exact line、decimal odds 逐条重算五态和 profit_units；再与生产权威输出比较：

```text
SETTLEMENT_MATCH = 148/148
PROFIT_MATCH = 148/148
```

quarter line、half win、half loss、push 必须有黄金向量。独立 oracle 只用于验收，不得成为第二生产权威。

### 7.3 六场 LOSS 报告

完成 `LOSS_ROOT_CAUSE_REPORT.md`。四场冲突比赛若因子身份不可重建，只能标为 Owner annotation + 当前代码机制解释；不得伪造逐因子权重。乌迪内斯–拉齐奥和卡利亚里–莱切必须按冻结模型/报价/lineup 时点逐项回答。每场结论区分：`CONFIRMED`、`INFERENCE`、`NOT_RECONSTRUCTIBLE`。

### 7.4 三段输出

所有轨/诊断必须分别输出：

- 全 148；
- 前 138；
- 近 10 `INCIDENT_REPLAY`。

近 10 的 5 条因子冲突只能生成 `OWNER_ANNOTATED_INCIDENT_REPLAY`；`-0.88u` 可复算，但不得升级为历史因子身份已验证。

### 7.5 补齐测试

完成原矩阵 6、7、8、11、14–18、20，并把第 9 项改为真实绑定测试：实际调用 `bind_evaluation_opportunity()`，断言 `official_funnel_eligible=true`、`opportunity_state=BLOCKED_BY_GATE`、不属于 candidate。

通知、正式推荐、赛后台账测试必须走真实消费函数，不接受“枚举值不相等所以自然不会进入”的替代断言。

## 八、R9：校准统计的正确表述

1. 对 overall calibration gap、profit、graded hit 等主报告指标做 10,000 次 fixture-cluster bootstrap，并报告 95% interval；同 fixture 的 AH/TOTALS 必须一起重抽。
2. Poisson-binomial z 与设计效应只能作为 secondary diagnostic，不得替代聚类区间。
3. `[0.65,1.01)` 高自信桶标为 `POSTHOC_EXPLORATORY`，不得作为预注册主门。
4. 记录每条温度的 training rows、result knowledge cutoff、T；报告 T=1/T=2 边界计数。网格仍按原冻结范围，不得因碰到 2.00 而事后扩网格。
5. 在 cashflow/因子不可估计问题修正前，撤回“温度校准不能识别好的那批”“因子绕过不是主因”两句结论。可保留：当前证据显示总体预测 graded 赢面高于实测，是需优先处理的校准风险。

## 九、交付包补齐

继续使用原目录：

```text
docs/review_packages/W2_OFFICIAL_CANDIDATE_ACCURACY_REMEDIATION_20260909/
```

必须至少包含并由 `HASHES.sha256` 全覆盖（除 hash 文件本身）：

- DISPATCH.md；
- REMEDIATION_DISPATCH_V1_1.md；
- SOURCE_IDENTITY.json；
- OFFICIAL_148_MANIFEST.jsonl；
- OFFICIAL_148_RECOMPUTATION.json；
- LAST10_INCIDENT_REPLAY.json；
- LOSS_ROOT_CAUSE_REPORT.md；
- FACTOR_BYPASS_REPAIR_REPORT.md；
- CALIBRATION_COMPARISON.json；
- METRICS.json；
- TEST_RESULTS.md；
- REPORT.md。

`REPORT.md` 不得再把实际存在的 `TEST_RESULTS.md` 写成缺失。报告必须列出从 `21c436d1` 到整改 commit 的精确 changed files。

## 十、自检和回执

固定使用：

```text
uv run --offline --python 3.12.13
```

执行：定向测试、相关生产回归、Ruff、compileall、`git diff --check`、全部生成器两次 byte-identical、交付包 hash 校验。不得删除、skip、xfail 或弱化既有测试。

最终仍只能返回原执行令两个完整终态之一，不能再附加“部分完成”：

```text
DONE_CHAIN_FIXED_MODEL_CANDIDATE_READY
DONE_CHAIN_FIXED_NO_SAFE_MODEL_CANDIDATE
```

鉴于当前因子历史身份 0/148 和 cashflow 大量缺失，若整改后仍无安全校准候选，合法终态就是第二种；这不妨碍链路修复必须完整。

回执除原字段外增加：

```text
PREVIOUS_COMMIT
FACTOR_VERDICT_PERSISTED
FACTOR_IDENTITY_VERSION
FACTOR_IDENTITY_MUTATION_TESTS
HISTORICAL_READBACK_COMPATIBILITY
SETTLEMENT_INDEPENDENT_ORACLE_MATCH
CASHFLOW_EDGE_PROVENANCE_COUNTS
TRACK_ESTIMABLE_DENOMINATORS
ALL_AH_BLOCKED_DIAGNOSTIC_LABEL
CALIBRATION_CLUSTER_INTERVAL
REQUIRED_ARTIFACTS_PRESENT
```

## 十一、硬边界

```text
REAL_PROVIDER_CALLS = 0
PUBLIC_HTTP_FETCH = 0
PRODUCTION_DB_READS = READ_ONLY_EXACT_148_REMEDIATION_ONLY
PRODUCTION_DB_FULL_TABLE_SCAN = 0
PRODUCTION_DB_WRITES = 0
PRODUCTION_CONFIG_WRITES = 0
DEPLOYMENT_EXECUTED = false
SCHEDULER_RESTARTED = false
OBSIDIAN_WRITES = 0
GITHUB_PUSH = 0
PR_CREATED = false
REAL_MONEY_ACTIONS = 0
```

完成后停止，交 Codex 独立验收；不得自行部署。
