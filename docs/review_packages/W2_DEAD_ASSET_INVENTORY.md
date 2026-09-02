# W2-DEAD-ASSET-INVENTORY

状态：`INVENTORY_ONLY_OWNER_REVIEW_REQUIRED`

本报告只清点，不删除文件、不修改 package matrix、不改运行逻辑。审计基线为
`1de3c1ef554d00a408577f59f4864e04f1d341da`。

## 1. 总计数

| 项目 | 数量 | 结论 |
|---|---:|---|
| `src/w2` 顶层包 | 40 | 主清单 `KEEP 28 / KEEP_OFFLINE 10 / KEEP_MIGRATION 1 / KEEP_AUDIT 1 / DELETE 0`；整包候选 0 |
| `src/w2` Python 文件 | 285 | 发现 2 个整模块候选、20 个包内孤立符号候选 |
| 当前 `scripts/` 文件 | 162 | 主清单历史 8 个 `DELETE` 路径均已不存在；本轮脚本删除候选 0 |
| 主清单后新增、尚无精确 D 分类的脚本 | 42 | 不满足四项全查，不列候选；须先刷新主清单 |
| 仅测试引用组 | 15 | 不等于死代码，单独交 Owner 判断 |
| 因 A/B/C/D 命中而明确保留的高风险反例 | 7 | 不列候选 |

所以 Owner 所说的“很多”，在当前基线上可操作地收敛为：**22 个待复核清理候选，
15 组仅测试引用项；不存在可直接删除的整包或脚本。**

## 2. 口径与边界

- A：`src/` 内除定义本身外的精确符号调用或模块导入。
- B：`scripts/` 内精确符号调用、模块导入或 shell 内嵌 Python 调用。
- C：`docs/runbooks/`、`docs/operations/` 内精确路径或符号引用。
- D：主清单中对该精确路径/符号的 `KEEP` / `MANUAL_OPS` 分类。父包的
  `KEEP` 只证明不能删整包，不会把包内每个从未使用的私有函数自动变成活代码；父包
  分类仍计入删除风险。
- “命中数”按文件计数；同一文件多次出现仍记 1。测试引用不并入 A，另列 T。
- 动态入口、装饰器注册、console entrypoint、ORM metadata side effect 均人工复核；
  不能仅凭名称或 AST 零调用判死。
- V2、冻结 evidence/artifact/cohort、`docs/review_packages/` 冻结包、已应用 migration
  从候选空间整体排除，未读取 HOLDOUT 内容，也未把它们列入清单。

## 3. 四项全查后仍为零的候选

下表每行均满足精确资产级 `A=0 / B=0 / C=0 / D=0`。建议只是后续删除批次，
**不是本任务的删除授权**。

| 文件:行号 | 符号 | 类型 | A / B / C / D | 归类 | 建议 | 删除风险 |
|---|---|---|---|---|---|---|
| `src/w2/markets/baselight_limited_ah.py:1` | 整模块 | 模块 | `0 / 0 / 0 / 0` | 孤立历史实现 | 第一批整文件候选 | 中：父包 `markets=KEEP`；删除前跑 package matrix 与 market 契约测试 |
| `src/w2/prematch/candidate_notification_cli.py:1` | 整模块 | 手工 CLI | `0 / 0 / 0 / 0` | 无登记孤立入口 | 第一批整文件候选 | 中高：能 enqueue 测试消息；先确认 Owner 从未在仓库外手工调用 |
| `src/w2/ingestion/future_refresh.py:81` | `RefreshLockError` | exception class | `0 / 0 / 0 / 0` | 孤立符号 | 第一批符号候选 | 低：父模块 runtime reachable，须只删符号 |
| `src/w2/ingestion/checkpoint_refresh.py:199` | `checkpoint_plans_from_fixture_payloads` | function | `0 / 0 / 0 / 0` | 被 canonical 同类函数取代 | 第一批符号候选 | 中：保留 `canonical_checkpoint_plans_from_fixture_payloads` |
| `src/w2/ingestion/market_timeline.py:452` | `_market_groups` | private function | `0 / 0 / 0 / 0` | 孤立 helper | 第一批符号候选 | 低：timeline 模块本身仍活跃 |
| `src/w2/ingestion/market_timeline.py:526` | `_select_mainline_group` | private function | `0 / 0 / 0 / 0` | 孤立 helper | 第一批符号候选 | 中：不得误删当前 `select_mainline_snapshot_result` 链 |
| `src/w2/settlement/settle.py:78` | `match_result_from_model` | function | `0 / 0 / 0 / 0` | 孤立 adapter | 第一批符号候选 | 中：settlement package runtime reachable |
| `src/w2/formal/readiness.py:120` | `load_approval_manifest` | function | `0 / 0 / 0 / 0` | 孤立 loader | 第一批符号候选 | 中：formal readiness 契约敏感 |
| `src/w2/matchday/coverage.py:150` | `MatchdayCoverageAudit` | class | `0 / 0 / 0 / 0` | 未构造 facade | 第二批候选 | 中：其内部 reconciler 仍可能被别处直接使用 |
| `src/w2/providers/control.py:222` | `provider_scheduler_skip_payload` | function | `0 / 0 / 0 / 0` | 孤立 fail-closed payload helper | 第二批候选 | 中高：删除不能弱化 scheduler fail-closed 行为 |
| `src/w2/providers/api_football.py:274` | `UndecidedSecondaryOddsProvider` | dataclass/provider stub | `0 / 0 / 0 / 0` | 未构造 provider stub | 第二批候选 | 中高：Provider 默认拒绝语义；先确认无外部插件导入 |
| `src/w2/prematch/analysis_calculator.py:263` | `_public_market_is_primary_pick` | private function | `0 / 0 / 0 / 0` | 孤立旧 pick predicate | 第一批符号候选 | 低：删除前跑 card/decision adapter 契约测试 |
| `src/w2/dashboard/scorelines.py:282` | `_direction_top3_scorelines` | private function | `0 / 0 / 0 / 0` | 孤立旧展示 helper | 第一批符号候选 | 低：当前 scoreline 投影不得连带修改 |
| `src/w2/dashboard/workspace.py:2256` | `_factual_summary` | private function | `0 / 0 / 0 / 0` | 被 `_match_factual_summary` 等现链取代 | 第一批符号候选 | 低：同名 payload 字段不是调用者 |
| `src/w2/markets/market_candidate.py:604` | `_normalize_selected_odds` | private function | `0 / 0 / 0 / 0` | 恒等孤立 helper | 第一批符号候选 | 低：不影响当前 `_selected_price` |
| `src/w2/markets/value_engine.py:133` | `infer_decimal_odds` | function | `0 / 0 / 0 / 0` | 孤立格式转换 | 第二批候选 | 中：该文件其他 settlement/EV 函数仍被生产和脚本使用 |
| `src/w2/markets/value_engine.py:353` | `AsianHandicapLadderEvaluator` | class | `0 / 0 / 0 / 0` | 未构造空子类 | 第一批符号候选 | 低：基类仍有测试引用，活跃 settlement 函数须保留 |
| `src/w2/markets/value_engine.py:357` | `TotalsLadderEvaluator` | class | `0 / 0 / 0 / 0` | 未构造空子类 | 第一批符号候选 | 低：同上 |
| `src/w2/readiness/data_gate.py:576` | `_lineups_next_eval` | private function | `0 / 0 / 0 / 0` | 孤立 readiness helper | 第二批候选 | 中高：lineup fail-closed 与 next-eval 展示不可回归 |
| `src/w2/pricing/supremacy.py:21` | `fair_total_from_independent_xg` | function | `0 / 0 / 0 / 0` | 孤立 totals helper | 第一批符号候选 | 低：同文件 `fair_handicap_from_supremacy` 仍被 `pricing/shadow.py` 使用 |
| `src/w2/infrastructure/persistence/recommendation_lock_snapshot.py:174` | `persist_recommendation_lock_snapshot` | write helper | `0 / 0 / 0 / 0` | 孤立持久化 wrapper | 最后批、单独复核 | 高：recommendation lock 是审计链；不得误删 builder/read path |
| `src/w2/prematch/candidate_notifications.py:678` | `enqueue_brewing_digest` | write wrapper | `0 / 0 / 0 / 0` | 孤立 wrapper | 最后批、单独复核 | 高：同文件 `_in_session` 实现仍被测试覆盖；通知链需独立回归 |

### 建议分批

1. 第一批只删低风险私有 helper、空子类与真正孤立历史模块。
2. 第二批处理 provider/readiness/settlement 等安全边界符号，每类单独提交。
3. 两个 write wrapper 最后处理；须先证明无仓库外运维调用，再跑完整通知/lock 测试。

## 4. 仅测试引用：不等于死代码

这些项没有生产调用，但测试本身可能是未接线能力的唯一契约、package matrix 的依赖边，
或未来恢复入口。必须由 Owner 决定是“删除实现与测试”还是“恢复产品接线”。

| 文件:行号 | 符号/组 | 类型 | A / B / C / D；T | 归类 | 建议 | 删除风险 |
|---|---|---|---|---|---|---|
| `src/w2/dashboard/l2_diagnostics.py:29` | `build_l2_diagnostics` | function | `0/0/0/0；T=1 test file` | test-only module | Owner 判断是否废弃 L2 contract | 中：dashboard contract |
| `src/w2/ingestion/quota.py:7` | `QuotaPolicy`, `QuotaManager` | module surface | `0/0/0/0；T=1` | test-only legacy quota | 与现役 `quota_budget.py` 对账后决定 | 高：Provider 配额安全 |
| `src/w2/ingestion/retry.py:7` | breaker/retry 四符号 | module surface | `0/0/0/0；T=1` | test-only retry library | 不与现役 HTTP retry 混删 | 高：Provider 容错 |
| `src/w2/ingestion/scheduler.py:10` | `SNAPSHOT_PHASES`, `build_snapshot_schedule` | module surface | `0/0/0/0；T=1` | test-only legacy scheduler | 与 apps scheduler 实际链对账 | 高：调度安全 |
| `src/w2/matchday/settlement.py:30` | `MatchdaySettlementService` | class | `0/0/0/0；T=1` | test-only Stage10C facade | Owner 判断是否保留离线恢复能力 | 中高：Stage10C 手工运维仍 KEEP |
| `src/w2/strategy/candidate.py:93` | `hard_gate_reasons`, `generate_candidate` | legacy candidate cluster | `A=1（仅 test-only correlation type）/B=0/C=0/D=0；T=2` | test-only cluster | candidate 与 correlation 同批裁决 | 高：候选语义契约 |
| `src/w2/strategy/correlation.py:45` | `low_correlation`, `select_uncorrelated_candidates` | legacy candidate cluster | `0/0/0/0；T=1` | test-only module | 同上 | 中：package matrix 依赖边会变化 |
| `src/w2/markets/value_engine.py:257` | `MarketValueEngine` | class | `A=2（仅两个空子类）/B=0/C=0/D=0；T=1` | test-only evaluator | 保留同文件活跃纯函数；仅裁决 class surface | 中高：Stage6B contract |
| `src/w2/ingestion/checkpoint_refresh.py:232` | 五个 retry/budget planner | function group | `0/0/0/0；T=1` | test-only planners | 先确认 scheduler 是否应恢复接线 | 高：调用上限与比赛日峰值 |
| `src/w2/ingestion/market_timeline.py:106` | `select_mainline_snapshot` | compatibility wrapper | `0/0/0/0；T=2` | test-only wrapper | 可与测试一起简化到 `_result` API | 中：lock snapshot semantics |
| `src/w2/lineups/value_identity.py:85` | `approved_crosswalk_for_team` | function | `0/0/0/0；T=1` | test-only crosswalk query | 暂缓；身价展示任务会消费同域能力 | 高：身份映射 |
| `src/w2/competitions/league_whitelist_audit.py:369` | `evaluate_league_whitelist_audit` | function | `0/0/0/0；T=1` | test-only audit API | 与 `run_stage14a` 的另一入口对账 | 中：联赛准入 |
| `src/w2/prematch/evaluation_slots.py:84` | `expected_opportunity_count` | function | `0/0/0/0；T=1` | test-only denominator helper | 不得削弱 evaluation denominator | 高：评估分母 |
| `src/w2/strategy/score_card.py:118` | `render_score_card` | function | `0/0/0/0；T=1` | test-only renderer | Owner 判断旧文本卡是否仍需恢复 | 低中：展示契约 |
| `src/w2/prematch/candidate_notifications.py:483,933` | `deliver_pending_notifications`, `enqueue_operational_summaries` | write wrappers | `0/0/0/0；T=1` | test-only write APIs | 单独审计 scheduler/外部运维调用后决定 | 高：通知投递与幂等 |

## 5. 明确保留的反例

| 资产 | A/B/C/D 命中 | 结论 |
|---|---|---|
| `src/w2/gates/gate5_preflight_cli.py` | D：console entrypoint、`KEEP_OFFLINE` | 无普通 caller 也不得列死 |
| `src/w2/observability/stage7i_observer_cli.py` | D：console entrypoint、`KEEP_OFFLINE` | 保留 |
| `src/w2/shadow/comparison_import_cli.py` | D：console entrypoint、`KEEP_OFFLINE` | 保留 |
| `src/w2/matchday/cli.py` | D：`w2-matchday` runtime entrypoint、`KEEP` | 保留 |
| `src/w2/schemas/domain.py` | D：`schemas=KEEP_OFFLINE / INVESTIGATION_REQUIRED` | 即使多项仅测试引用，也不列候选 |
| `src/w2/ingestion/future_refresh.py:3445 deterministic_task_key` | B：`scripts/run_predeploy_e2e_smoke.sh:194,302` | 保留；shell 内嵌 Python 是真实调用 |
| `src/w2/prematch/simulation_reconciliation.py:48 reconcile_simulation` | C：两个 architecture operations 文档 | 保留；链路对账仍有人工运维含义 |

Stage10C 相关 `scripts/check_w2_stage10c.py`、`scripts/run_stage10c_daily_cycle.py` 在主清单
均为 `MANUAL_OPS / KEEP`，因此未列候选。所有已应用 migration、冻结 cohort/evidence、
V2 和已冻结 review package 同样未进入扫描结果表。

## 6. Scripts D 分类缺口

主清单 script authority matrix 早于当前基线。当前有 42 个脚本没有精确 D 行；它们中包含
验收、修复、发布、SC21、V1 PIT 与 xG 恢复工具。由于四项全查缺 D，**本报告不把其中
任何一个列为清理候选**。后续删除任务应先更新主清单，而不是以“没有 runtime caller”代替
人工运维分类。

## 7. 删除前最低验收门

每一批删除都应：

1. 只删清单内精确资产，不顺手重构相邻活跃链。
2. 先更新 D 分类与 package matrix 的预期依赖边，再由 Owner 复核。
3. 跑受影响定向测试、canonical、package matrix、Ruff 与全量 pytest。
4. 任一失败必须在 `1de3c1ef` 对同 node ID 复跑；不得用历史失败概括新失败。
5. recommendation lock、notification、Provider、readiness、denominator 分别独立提交。

## 8. 验证结果

- 定向清理风险相关测试：`58 passed`
- canonical：`18 passed`
- package matrix：`5 passed`
- Ruff：`PASS`
- 全量：`2950 passed / 9 skipped / 4 failed`
- 父提交 `1de3c1ef` 对相同 4 个 node ID 复跑：`4/4` 原样失败
  - Compose 2 个：本机有 `docker` CLI，但没有 Compose 子命令，`docker compose -f` 报
    `unknown shorthand flag: 'f'`
  - staging parity 2 个：macOS Docker UID/GID 行为使准备目录在检查端呈现 `MISSING`
- 任务相关失败：0

## 9. Stop-line 对账

- 删除：0
- 生产写：0
- Provider 调用：0
- ledger 写：0
- migration：0
- 部署：0
- 参数 / `CALIBRATION_VERSION`：0
- GitHub / GHCR：0
- package matrix 登记块修改：0
- V2 / 冻结 evidence / frozen review package 修改：0

本报告不改变 calibration authority；identity 仍为
`21960a863fd93dcae01ff8804e73fd0ef9d8360e8f2b8073313f226322e5db71`，verdict 仍为
`APPROVED_VALIDATED`。
