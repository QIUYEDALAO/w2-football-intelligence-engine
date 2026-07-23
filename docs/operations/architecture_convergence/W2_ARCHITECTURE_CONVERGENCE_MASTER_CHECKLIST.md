# W2 架构收敛执行总清单与 Codex 工作指令

> 本文件依据老板最终审理决定制定。  
> Codex 执行任何代码修改前，必须先将本文件内容写入 GitHub 仓库：
>
> `docs/operations/architecture_convergence/W2_ARCHITECTURE_CONVERGENCE_MASTER_CHECKLIST.md`
>
> 后续所有架构收敛 PR 只更新这一份总清单，不再为每个小步骤重复创建大量日期型上下文文档。
>
> **只有完成代码审核、完整 CI、必要的 staging 验收并合并后，才允许把 `[ ]` 改为 `[x]`。**
> 本地完成、只提交报告、CI 尚未结束、部署尚未验证，都不能打勾。

---

## 一、老板已批准的最终决定

- [x] 暂停新增功能。
- [x] 批准架构调整。
- [x] PostgreSQL 作为运行时唯一权威。
- [x] Dashboard 只读取一套当前状态。
- [x] 部署改为 CI 构建镜像、服务器拉取镜像。
- [x] 在现有系统上分阶段调整，不推倒重建，不并行建设第二套系统。
- [x] PR #370 范围冻结；其已验证代码通过独立 baseline integration PR 接入
  `main`，不得继续向 PR #370 追加代码或文档。
- [x] 真实首发 canary 延后为独立 ops 验收任务，不再是 P0 架构工作的
  前置条件；只有真实首发窗口出现时才执行。
- [x] P0 两周内完成；整体工程参考周期 6–8 周。

### 唯一允许继续的现有功能工作

在功能冻结期间，只允许：

```text
PR #370 VERIFIED BASELINE INTEGRATION
ARCHITECTURE CONVERGENCE TASKS IN CHECKLIST ORDER
REAL LINEUP CANARY AS A SEPARATE OPS ACCEPTANCE TASK
```

以上均不得新增功能。真实首发 canary 属于后续既有功能验收；没有真实
首发窗口时不得开启 Provider 或伪造结果。

---

## 二、执行红线

整个收敛期间不得违反：

1. 不新增联赛、市场、模型因子或 Dashboard 功能。
2. 不修改模型权重、EV/Delta 门槛、盘口主线规则和 quote freshness。
3. 不开放 Formal、Lock、Production。
4. 不新增竞争性的事实表、配置文件或 fallback。
5. 不把架构改造继续塞入 PR #370。
6. 每个 PR 只解决一个明确问题，必须可独立回滚。
7. 历史业务数据不删除。
8. 删除或 drop 前必须证明该路径零读、零写、零依赖。
9. 已证明零读、零写、零任务、零报表、零外键阻塞且无独有数据价值的表，
   必须在当前任务同一 PR 通过新 migration 正式 drop；证据不足的表保持原状
   并继续调查，不 rename 隔离。
10. Provider、Formal、Lock 等安全熔断环境变量继续保留。
11. 不以本地测试或 Markdown 报告代替 GitHub CI 和 staging 证据。
12. 不使用 `[skip ci]` 作为任何任务的最终验收提交。
13. 不再创建大量重复的日期型证据文档；统一更新本文件。
14. Codex 不得自行把任务并行化，也不得跨任务顺手重构。

---

## 三、任务执行顺序

任务必须严格按顺序执行。ARCH-01 的代码范围已冻结，真实首发 canary
已移出 P0 前置条件。PR #370 已验证基线经独立 integration PR 接入
`main` 且 PR #370 关闭后，立即开始 ARCH-P0-01。

# 阶段 0：冻结、收口 PR #370

## ARCH-00：在 GitHub 建立总清单

- [x] 在仓库创建本文件：
  `docs/operations/architecture_convergence/W2_ARCHITECTURE_CONVERGENCE_MASTER_CHECKLIST.md`
- [x] 记录当前 main SHA、PR #370 head、staging SHA、migration head。
- [x] 在文件中写明功能冻结和红线。
- [x] 不修改生产代码。
- [x] 建立一个 docs-only Draft PR。
- [x] 完整 CI 通过并合并。

**完成标准**

```text
MASTER_CHECKLIST_COMMITTED
FEATURE_DEVELOPMENT_FREEZE_RECORDED
```

---

## ARCH-01：完成并关闭 PR #370

- [x] 重新核验 PR #370 exact head。
- [x] 冻结 PR #370 范围，不再追加代码或文档。
- [x] 将真实首发 canary 延后为独立 ops 验收任务，并从 P0 前置条件移除。
- [x] 不增加任何架构收敛代码。
- [x] 不增加新联赛、新市场、新表、新 Dashboard 功能。
- [x] 核验 migration current=head。
- [x] 核验 recommendation、lock、OFFICIAL、formal settlement 仍为 0。
- [x] exact-head CI 全绿。
- [x] 独立 baseline integration PR exact-head CI 全绿并完成外部审核。
- [x] baseline integration PR 合并到 `main`。
- [x] 基线接入后关闭 PR #370，并确认所有证据已进入 `main`。

```text
Status: DONE
Branch: codex/w2-pr370-baseline-integration
PR: #374 (Merged)
Base SHA: cb2a040f826926af98154c644718f013e96d0e79
Started at: 2026-07-22T23:20:00+0800
Owner: Codex
Merged PR: #374
Merge SHA: 160a67505e2ba725b70250635ee71ce99e11b812
CI run: 29933191521
Staging acceptance: STAGING_PARITY_AND_PREDEPLOY_E2E_PASS
Completed at: 2026-07-22T22:59:28Z
PR_370_SCOPE_FROZEN
PR_370_STATE_CLOSED
REAL_LINEUP_CANARY_DEFERRED
P0_ARCHITECTURE_WORK_UNBLOCKED
Evidence: PR #370 exact head remains 210367a99fa8b448e2ab00bdd878ec485fe1e42a;
  exact-head CI run 29929890310 passed verify, staging-parity and predeploy-e2e.
  Baseline integration is limited to merging that verified tree into current
  main and retaining this checklist. No feature, table, configuration or
  fallback is added beyond the verified PR #370 tree.
Next required action: merge the baseline integration after external review,
  close PR #370, then start ARCH-P0-01 immediately.
```

ARCH-01 当前核验：

```text
PR_370_EXACT_HEAD=210367a99fa8b448e2ab00bdd878ec485fe1e42a
PR_370_HEAD_CHANGE=STATUS_DOCUMENT_CONTRACT_ONLY
PR_370_PRODUCTION_CODE_DELTA=0
PR_370_ARCHITECTURE_SCOPE_DELTA=0
STAGING_SHA=81b4dd2bd4a23d6ad8f5782abf05f904a88c38a8
PR_370_MIGRATION_HEAD=0036_require_reviewed_player_identity
STAGING_MIGRATION_CURRENT=0036_require_reviewed_player_identity
RECOMMENDATIONS_CURRENT_COUNT=0
RECOMMENDATION_LOCKS_CURRENT_COUNT=0
FORWARD_PREDICTION_LOCKS_CURRENT_COUNT=0
GATE5_RECOMMENDATION_LOCK_EVENTS_CURRENT_COUNT=0
OFFICIAL_LEDGER_SCOPE_CURRENT_COUNT=0
FORMAL_SETTLEMENTS_CURRENT_COUNT=0
SAFETY_COUNTS_BEFORE_AT=2026-07-22T13:53:31Z
SAFETY_COUNTS_AFTER_AT=2026-07-22T14:02:25Z
RECOMMENDATION_LOCK_OFFICIAL_FORMAL_SETTLEMENT_DELTA=0
CANARY_RESULT=REAL_LINEUP_CANARY_DEFERRED
CANARY_PROVIDER_CALLS=0
CANARY_WRITE_DELTA=0
EXACT_HEAD_CI_RUN=29929890310
EXACT_HEAD_CI_STATUS=PASS
FORMAL_DISABLED
LOCK_DISABLED
PRODUCTION_DISABLED
MANUAL_APPROVAL_REQUIRED
```

**完成标准**

```text
PR_370_SCOPE_FROZEN
PR_370_VERIFIED_BASELINE_MERGED_TO_MAIN
PR_370_CLOSED_AFTER_BASELINE_INTEGRATION
REAL_LINEUP_CANARY_DEFERRED_TO_OPS_ACCEPTANCE
P0_ARCHITECTURE_WORK_UNBLOCKED
NO_ARCHITECTURE_SCOPE_ADDED_TO_PR_370
```

---

# 阶段 P0：止血，目标两周内完成

## ARCH-P0-01：删除 API 对不存在 reports 文件的读取

**独立 PR，只处理这一项。**

```text
Status: DONE
Branch: codex/arch-p0-01-remove-report-reads
PR: #375 (MERGED)
Base SHA: 160a67505e2ba725b70250635ee71ce99e11b812
Merge SHA: 1e9e811dc5393eb6b270bbe0bfa1fb8579142b4a
Exact-head CI: 29965523791 (verify, staging-parity, predeploy-e2e passed)
Started at: 2026-07-23T07:08:42+0800
Owner: Codex
Evidence: All 12 production API report targets are absent; tracked reports/ file
  count is 0. Remove every API report read, preserve writer-only audit output,
  return explicit empty/NOT_READY states, and add a static regression guard.
Rollback: Revert this PR. No schema, data, configuration, provider or safety
  switch change is included.
```

- [x] 全量列出 `src/w2/api/repository.py` 及相关生产代码读取的 `reports/*.json`。
- [x] 逐项证明目标文件不存在或生产运行不应依赖。
- [x] 删除所有生产读取路径和静默默认值 fallback。
- [x] 不用新的文件 fallback 替代旧 fallback。
- [x] 缺少数据库事实时返回明确的 `NOT_READY` 或错误状态。
- [x] 新增回归测试：生产 API 不访问 `reports/`。
- [x] 新增静态检查：禁止生产代码重新引用 `reports/*.json`。
- [x] 完整 CI 通过。
- [x] staging 语义对账通过。
- [x] PR 合并。

**验收**

```text
PRODUCTION_REPORT_FILE_READS = 0
NEW_FALLBACKS = 0
```

---

## ARCH-P0-02：赔率读取路径收敛为一个入口

**独立 PR，只收敛“读”，不先重写所有写入。**

```text
Status: DONE
Branch: codex/arch-p0-02-odds-read-authority
PR: #376 (Merged)
Base SHA: 1e9e811dc5393eb6b270bbe0bfa1fb8579142b4a
Implementation-head CI: 29968317105 (verify, staging-parity, predeploy-e2e passed)
Merge SHA: dae21e59f949be4ac70b75bbcf0f96d1d03f8266
Started at: 2026-07-23T07:34:21+0800
Owner: Codex
Authority table: matchday_market_observations
Authority method: ReadModelRepository.future_market_observations_for_fixtures()
Market snapshot source: matchday_market_observations
Scope: Read convergence only; no schema, write-path, provider, configuration or
  safety-switch change.
Rollback: Revert this PR. Historical tables and all existing writers remain.
Inventory: matchday_market_observations is the sole production quote/readiness
  source. future_market_observation and odds_observations remain unchanged but
  are not production read authorities. runtime/stage7e/market_snapshots.json,
  runtime market timelines, normalized frozen snapshots and staging seed files
  cannot fill a production response; offline projectors/writers remain audit-only.
Reconciliation: fixture, bookmaker, market, selection, signed line, odds,
  captured_at and observation_id quote identity matched the canonical row.
Real staging acceptance: host 118.196.30.136; previous SHA
  81b4dd2bd4a23d6ad8f5782abf05f904a88c38a8; accepted code SHA
  655164def0f1044d967809c2f1f0f122bfcfe3a8. Visible upcoming fixture IDs:
  1492141, 1492292, 1492293, 1492296, 1492298.
Real staging reconciliation: fixture, bookmaker, market, selection, signed
  line, odds, captured_at and observation_id hashes remained identical for all
  five fixtures. Authority counts/hashes were respectively 344/37ac4543,
  411/632bc69b, 388/0769d26a, 402/14447a47 and 391/65fb9b03.
Real HTTP proof: 20 complete read cycles, 11 requests per cycle and 220 HTTP
  200 responses total. Every cycle returned five Dashboard fixtures, five
  analysis cards and five stable 256-row odds timelines. Dashboard odds/readiness
  hash remained a15b5fe2e385b6360b4c0832006a37394ed97b2426a99dbff8c6efd33acee1a7.
Real staging zero-write proof: provider_request_logs stayed 162, refresh audits
  stayed 60, matchday_market_observations stayed 44644, recommendation/lock/
  settlement stayed 0, and pg_stat_user_tables INSERT/UPDATE/DELETE counters
  plus aggregate hash stayed 58111/374/0 and 462502a1e012bbc269e906568483fc71.
  MERGE delta was 0 because neither INSERT nor UPDATE changed. Provider calls
  and scheduler flags remained disabled throughout the acceptance window.
Local full validation: W2 all-stage verify PASS; 1450 passed, 4 skipped.
```

- [x] 盘点所有活跃赔率读取表和文件：
  - `future_market_observation` 或当前等价表；
  - `matchday_market_observations`；
  - `odds_observations`；
  - `runtime/stage7e/market_snapshots.json`；
  - 其他 runtime/seed/frozen 读取。
- [x] 指定一套当前阶段的唯一读取仓储方法。
- [x] `market_snapshots()` 不再把数据库与 runtime JSON 相加合并。
- [x] runtime JSON 降级为审计副本，不能影响生产返回值。
- [x] 当前没有数据库赔率时，明确返回无数据，不能用 seed/文件补值。
- [x] 保持所有历史表原样，P0 不 drop 表。
- [x] 增加 old/new 结果对账：
  - fixture；
  - bookmaker；
  - market；
  - selection；
  - signed line；
  - odds；
  - captured_at；
  - quote identity。
- [x] Dashboard 与分析读取均经过唯一仓储入口。
- [x] 完整 CI、staging 对账、20 次只读零写通过。
- [x] PR 合并。

**验收**

```text
PRODUCTION_ODDS_READ_AUTHORITY_COUNT = 1
RUNTIME_JSON_ODDS_AUTHORITY = 0
```

---

## ARCH-P0-03：联赛白名单和 Provider 映射数据库化

**独立 PR，必须复用现有 `league_profile / league_season` 或已确认的等价表。**

```text
Status: DONE
Branch: codex/arch-p0-03-db-competition-authority
PR: #377 (Merged)
Base SHA: dae21e59f949be4ac70b75bbcf0f96d1d03f8266
Final PR head: 1a57272c7e1d7f509430d85a0ef8b6e4baacec73
Final exact-head CI: 29974016905 (verify, staging-parity,
  predeploy-e2e passed)
Merge SHA: 7bd5088b034a36ec12a23a6aa647a53524ecdce8
Final validated implementation head: dd2063b835eb7a0e2097b745e298a22570bd3794
Final implementation-head CI: 29973536625 (verify, staging-parity,
  predeploy-e2e passed)
Owner: Codex
Runtime authority tables: league_profile, league_season
Audit table: league_readiness_audit
Migration head: 0037_seed_competition_runtime_authority
Seed reconciliation: 14 profiles + 14 seasons inserted; 14 audit rows;
  second identical run 14 unchanged; 0 conflicts; staging seed enables the
  five policy-authorized competitions.
Correction: prior implementation/CI/staging acceptance was revoked because the
  seed policy.enabled value remained an independent runtime authority and the
  Registry did not fail closed on a DB/runtime environment mismatch.
Corrected staging acceptance: deployed exact implementation head
  dd2063b835eb7a0e2097b745e298a22570bd3794 over
  78110a5543339cb25066746e44b9a8e8e500ae42; all services became healthy and
  migration remained 0037_seed_competition_runtime_authority. DB and runtime
  environments both resolved to staging.
Corrected same-process toggle/rollback: with allsvenskan initially enabled, one
  Python process (PID 25) observed true -> false -> true for Registry, future
  scheduler, matchday checkpoint scheduler, odds refresh and lineup refresh,
  without restart or deploy between updates. The final audited update restored
  the original true state. league_readiness_audit advanced 16 -> 18.
Corrected zero-side-effect proof: provider_request_logs stayed 162 (delta 0);
  recommendations, recommendation_locks, settlements and
  gate5_recommendation_lock_event all stayed 0.
Removed authorities: competition/policy JSON runtime reads,
  W2_STAGING_ENABLED_COMPETITIONS,
  W2_FUTURE_FIXTURE_REFRESH_COMPETITION_ID(S), and Python league-ID tuples.
Safety boundary: W2_FUTURE_FIXTURE_REFRESH_ENABLED,
  W2_PROVIDER_SCHEDULER_ENABLED, W2_PROVIDER_CALLS_DISABLED, endpoint allowlist,
  quota caps and all recommendation/formal/lock/production switches unchanged.
Local validation: W2 all-stage PASS; ruff PASS; mypy PASS; 1455 passed,
  4 skipped; migration empty-upgrade/downgrade/re-upgrade PASS; web typecheck,
  build and 26 Playwright E2E PASS.
```

- [x] 核实现有 DB 表是否足以承载：
  - competition ID；
  - environment；
  - enabled；
  - provider；
  - provider league ID；
  - provider season；
  - timezone；
  - market scope；
  - fixture/odds/lineup refresh switches；
  - updated_by/updated_at；
  - config hash/version。
- [x] 不新增新表；优先扩展或复用老板指定的现有表。
- [x] 编写一次性、幂等种子脚本：
  - 导入 `config/competitions/*.json`；
  - 导入相关 policy JSON；
  - 导入 enabled/provider_id/season；
  - 输出冲突报告。
- [x] `CompetitionRegistry` 运行时改为读取数据库，并校验 DB environment。
- [x] JSON 降级为首次安装种子，不再是运行时权威。
- [x] 删除 `W2_STAGING_ENABLED_COMPETITIONS` 的业务覆盖机制。
- [x] 删除 `league_whitelist_scope.py` 中联赛硬编码元组。
- [x] 保留 Provider 总熔断等安全环境变量。
- [x] scheduler 从 DB 顶层 enabled 读取启用联赛，policy.enabled 不再独立生效。
- [x] 修改 DB 中 enabled 后无需部署即可令 Registry、future scheduler、matchday scheduler 同步生效。
- [x] 所有修改有审计记录。
- [x] 最新实现 head 完整 CI、staging 同进程变更测试和回滚测试通过。
- [x] PR 合并。

**验收**

```text
DB_COMPETITION_RUNTIME_AUTHORITY = PASS
JSON_RUNTIME_AUTHORITY = REMOVED
STAGING_ENV_WHITELIST_OVERRIDE = REMOVED
```

---

## ARCH-P0-04：P0 总验收

```text
Status: DONE
Branch: codex/arch-p0-04-p0-acceptance
Base/Main SHA: 7bd5088b034a36ec12a23a6aa647a53524ecdce8
PR: #378 (Ready for review)
Merge SHA: d62e335100ebd41856a5b7822938424a511a5fb0
Validated implementation head: b5055f73a3a6503e80e39cab5484d22d61f46a49
Implementation-head CI: 29976169675 (verify, staging-parity,
  predeploy-e2e passed)
Owner: Codex
Static authority proof: production API reports reference files=0;
  production odds read authority count=1
  (matchday_market_observations through
  future_market_observations_for_fixtures); runtime JSON odds authority=0;
  competition runtime JSON authority hits=0.
DB hot-change proof: in one staging process (PID 24), allsvenskan
  true -> false stopped Registry, future scheduler and matchday scheduler;
  false -> true restored all three without build, deploy or restart, and the
  original true state was restored. league_readiness_audit advanced 18 -> 20.
Staging release: main SHA 7bd5088b034a36ec12a23a6aa647a53524ecdce8;
  migration remained 0037_seed_competition_runtime_authority.
Stability observation: 2026-07-23T02:47:32Z ->
  2026-07-23T03:03:20Z; 948 seconds; 31 samples. Every ready/version/meta
  HTTP probe passed; api, worker, scheduler, web, postgres and redis remained
  healthy; every container restart count stayed 0; release SHA never changed.
Post-observation authority proof: 32 current market snapshots all reported
  source=matchday_market_observations; enabled DB competitions remained
  allsvenskan, brasileirao_serie_a, chinese_super_league, eliteserien and
  world_cup_2026.
Post-observation safety proof: provider_request_logs stayed 162;
  matchday_market_observations stayed 44644; recommendations,
  recommendation_locks, settlements and gate5_recommendation_lock_event stayed
  0. Provider calls disabled=true, provider scheduler=false, recommendation,
  candidate, formal recommendation, production release and DeepSeek remained
  false. Formal AH, recommendation lock and production recommendation
  capabilities remained disabled and non-production.
Local validation: W2 all-stage PASS; ruff PASS; mypy PASS; 1458 passed,
  4 skipped. P0 focused authority and safety suite: 36 passed.
```

- [x] 生产 API 不读取不存在的 reports 文件。
- [x] 生产赔率只经过一套读取仓储。
- [x] runtime JSON 不影响当前赔率。
- [x] 联赛启用状态来自数据库。
- [x] 修改联赛配置不需要构建或部署。
- [x] Provider calls、Formal、Lock、Production 安全边界不变。
- [x] P0 staging 连续稳定运行至少一个审核周期。
- [x] 更新本总清单并由人工审核。
- [x] P0 验收 PR 合并。

**完成标准**

```text
P0_ARCHITECTURE_CONVERGENCE_PASS
```

---

# 阶段 P1：收敛，参考 3–4 周

## ARCH-P1-01：数据库僵尸表盘点与直接删除

- [x] 列出全部表及：
  - migration 来源；
  - 当前行数；
  - 最近读写时间；
  - 代码读写调用点；
  - 外键；
  - 报告/脚本依赖。
- [x] 对候选僵尸表逐张给出证据。
- [x] 已证明零读、零写、零任务、零报表、零外键阻塞且无独有数据价值的表，
  在本任务同一 PR 新增 drop migration 并立即删除。
- [x] 重复表如有独有数据，先迁入唯一权威表并完成行数与 hash 对账，
  再在本任务同一 PR drop。
- [x] 同时删除仅服务被删表的 ORM、Repository、脚本、测试、配置和 import。
- [x] 证据不足的表保持名称、schema 和运行状态不变并记录缺失证据；
  不通过 rename、archive、backup、兼容 view 或其他隔离结构延后决策。
- [x] 历史 migration 文件保留；只通过新的可验证 migration 执行正式 drop。
- [ ] migration upgrade/downgrade、完整 CI 和 staging 验收通过。
- [ ] PR 合并。

### ARCH-P1-01 本轮直接证据

基线为 `main@d62e335100ebd41856a5b7822938424a511a5fb0`，staging
为 `7bd5088b034a36ec12a23a6aa647a53524ecdce8`、migration
`0037_seed_competition_runtime_authority`。已对 staging `public` schema 的
144 张表逐表核验精确行数、`pg_stat_user_tables` 读写计数、全部外键，并对
`src/`、`apps/`、`scripts/`、`tests/`、`config/`、`infra/` 和 CI 做 ORM、
SQL、任务及报表引用扫描。

### 144 表逐表矩阵

口径：`row_count` 为 staging 精确 `count(*)`；生产读写来自 `src/` 与
`apps/` 的 ORM/SQL 静态调用点，模型注册、历史 migration、脚本和测试不计为
生产路径；外键按 `出站/入站` 计数。矩阵基于 drop 前 144 表基线，其中
`system_metadata` 的删除证据取自 migration `0038` 前的验收快照。

| table | row_count | 生产读 | 生产写 | 任务 | 报表 | 外键（出/入） | 独有数据价值 | 决定 |
|---|---:|---|---|---|---|---:|---|---|
| `ablation_run` | 0 | 无 | 无 | 无 | 无 | 1/0 | 关系结构待后续收敛 | 保留 |
| `alembic_version` | 1 | 有 | 有 | 无 | 无 | 0/0 | 有（1 行） | 保留 |
| `api_request_audit` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `asof_samples` | 0 | 无 | 无 | 无 | 无 | 2/0 | 关系结构待后续收敛 | 保留 |
| `audit_events` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `backup_run` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `bookmakers` | 0 | 无 | 无 | 无 | 无 | 0/1 | 关系结构待后续收敛 | 保留 |
| `calibration_artifact` | 0 | 无 | 无 | 无 | 无 | 1/0 | 关系结构待后续收敛 | 保留 |
| `canonical_historical_ah_facts` | 0 | 有 | 有 | 无 | 无 | 1/0 | 运行/安全契约 | 保留 |
| `canonical_team_match_history` | 102 | 有 | 有 | 有 | 无 | 3/0 | 有（102 行） | 保留 |
| `canonical_teams` | 16 | 有 | 有 | 无 | 无 | 0/4 | 有（16 行） | 保留 |
| `challenger_model` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `competitions` | 0 | 无 | 无 | 无 | 无 | 0/2 | 关系结构待后续收敛 | 保留 |
| `data_provenance` | 0 | 无 | 无 | 无 | 无 | 1/0 | 关系结构待后续收敛 | 保留 |
| `data_quality_runs` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `dataset_artifacts` | 0 | 无 | 无 | 无 | 无 | 1/0 | 关系结构待后续收敛 | 保留 |
| `dataset_sources` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `dataset_versions` | 0 | 无 | 无 | 无 | 无 | 0/2 | 关系结构待后续收敛 | 保留 |
| `dependency_risk` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `dynamic_prematch_evaluations` | 0 | 有 | 有 | 有 | 无 | 0/2 | 运行/安全契约 | 保留 |
| `dynamic_prematch_supersessions` | 0 | 有 | 有 | 有 | 无 | 2/0 | 运行/安全契约 | 保留 |
| `evaluation_record` | 0 | 无 | 无 | 无 | 无 | 1/0 | 关系结构待后续收敛 | 保留 |
| `feature_snapshots` | 0 | 无 | 无 | 无 | 无 | 1/0 | 关系结构待后续收敛 | 保留 |
| `fixtures` | 0 | 无 | 无 | 无 | 无 | 7/11 | 关系结构待后续收敛 | 保留 |
| `football_data_team_crosswalks` | 0 | 有 | 有 | 无 | 无 | 0/0 | 运行/安全契约 | 保留 |
| `forward_cycle_checkpoint` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `forward_cycle_run` | 0 | 无 | 无 | 无 | 无 | 0/1 | 关系结构待后续收敛 | 保留 |
| `forward_evaluation` | 0 | 无 | 无 | 无 | 无 | 1/0 | 关系结构待后续收敛 | 保留 |
| `forward_gate_audit` | 0 | 无 | 无 | 无 | 无 | 1/0 | 关系结构待后续收敛 | 保留 |
| `forward_holdout_run` | 0 | 无 | 无 | 无 | 无 | 0/1 | 关系结构待后续收敛 | 保留 |
| `forward_market_snapshot` | 0 | 有 | 无 | 无 | 有 | 0/0 | 报表读取契约 | 保留 |
| `forward_operational_alert` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `forward_prediction_lock` | 0 | 无 | 无 | 无 | 无 | 1/1 | 关系结构待后续收敛 | 保留 |
| `forward_result_event` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `forward_scheduler_run` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `forward_state_transition` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `freshness_alerts` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `future_market_observation` | 3840 | 无 | 有 | 有 | 无 | 0/0 | 有（3840 行） | 保留 |
| `future_refresh_checkpoint_audit` | 1 | 无 | 有 | 有 | 无 | 0/0 | 有（1 行） | 保留 |
| `future_refresh_checkpoint_plan` | 0 | 有 | 无 | 有 | 无 | 0/0 | scheduler 运行契约 | 保留 |
| `future_refresh_run_audit` | 60 | 有 | 有 | 有 | 无 | 0/0 | 有（60 行） | 保留 |
| `future_refresh_task_audit` | 55 | 有 | 有 | 有 | 无 | 0/0 | 有（55 行） | 保留 |
| `gate5_recommendation_lock_event` | 0 | 有 | 有 | 无 | 无 | 0/0 | 安全锁账本 | 保留 |
| `historical_market_source_snapshots` | 0 | 有 | 有 | 无 | 无 | 0/1 | 历史权威契约 | 保留 |
| `ingestion_runs` | 0 | 无 | 无 | 无 | 无 | 0/1 | 外键目标 | 保留 |
| `injuries` | 0 | 无 | 无 | 无 | 无 | 2/0 | 关系结构待后续收敛 | 保留 |
| `label_references` | 0 | 无 | 无 | 无 | 无 | 0/1 | 外键目标 | 保留 |
| `league_profile` | 14 | 有 | 有 | 无 | 无 | 0/0 | 有（14 行） | 保留 |
| `league_readiness_audit` | 20 | 有 | 有 | 无 | 无 | 0/0 | 有（20 行） | 保留 |
| `league_season` | 14 | 有 | 有 | 无 | 无 | 0/0 | 有（14 行） | 保留 |
| `league_team_membership` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `lineup_confirmed_events` | 0 | 无 | 有 | 有 | 无 | 0/0 | prematch 运行契约 | 保留 |
| `lineup_source_snapshots` | 0 | 有 | 有 | 有 | 无 | 0/0 | lineup 运行契约 | 保留 |
| `lineups` | 0 | 无 | 无 | 无 | 无 | 3/0 | 关系结构待后续收敛 | 保留 |
| `market_baseline_run` | 0 | 无 | 无 | 无 | 无 | 0/1 | 外键目标 | 保留 |
| `market_consensus` | 0 | 无 | 无 | 无 | 无 | 1/0 | 关系结构待后续收敛 | 保留 |
| `market_fit_diagnostic` | 0 | 无 | 无 | 无 | 无 | 1/0 | 关系结构待后续收敛 | 保留 |
| `market_quality_assessment` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `markets` | 0 | 无 | 无 | 无 | 无 | 1/0 | 关系结构待后续收敛 | 保留 |
| `matchday_checkpoint_plans` | 608 | 有 | 有 | 有 | 无 | 0/1 | 有（608 行） | 保留 |
| `matchday_endpoint_capture_plans` | 0 | 有 | 有 | 有 | 无 | 2/0 | matchday 运行契约 | 保留 |
| `matchday_endpoint_captures` | 231 | 有 | 有 | 有 | 无 | 0/4 | 有（231 行） | 保留 |
| `matchday_evidence_manifests` | 2 | 有 | 有 | 有 | 无 | 0/0 | 有（2 行） | 保留 |
| `matchday_fixture_identities` | 38 | 有 | 有 | 有 | 无 | 1/0 | 有（38 行） | 保留 |
| `matchday_market_observations` | 44644 | 有 | 有 | 有 | 无 | 1/0 | 有（44644 行） | 保留 |
| `migration_dry_run` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `migration_quarantine_record` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `migration_source_asset` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `migration_validation_record` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `model_artifact` | 0 | 无 | 无 | 无 | 无 | 1/0 | 关系结构待后续收敛 | 保留 |
| `model_evaluation` | 0 | 无 | 无 | 无 | 无 | 1/0 | 关系结构待后续收敛 | 保留 |
| `model_experiment` | 0 | 无 | 无 | 无 | 无 | 0/3 | 外键目标 | 保留 |
| `model_gate_decision` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `model_runs` | 0 | 无 | 无 | 无 | 无 | 0/1 | 外键目标 | 保留 |
| `odds_observations` | 0 | 无 | 无 | 无 | 无 | 2/0 | ARCH-P1-02 待对账 | 保留 |
| `operational_alert` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `operational_metric_snapshot` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `operations_check_result` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `operations_cycle` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `player_club_membership_observations` | 0 | 无 | 有 | 无 | 无 | 0/0 | 历史身份写入契约 | 保留 |
| `player_identity_crosswalks` | 0 | 有 | 有 | 无 | 无 | 0/0 | ARCH-P1-03 待对账 | 保留 |
| `player_identity_mappings` | 0 | 有 | 有 | 有 | 无 | 0/1 | lineup 身份契约 | 保留 |
| `player_valuation_observations` | 0 | 有 | 有 | 有 | 无 | 0/0 | 估值运行契约 | 保留 |
| `players` | 0 | 无 | 无 | 无 | 无 | 0/4 | 外键目标 | 保留 |
| `prediction_snapshot` | 0 | 无 | 无 | 无 | 无 | 1/0 | 关系结构待后续收敛 | 保留 |
| `predictions` | 0 | 无 | 无 | 无 | 无 | 2/1 | 关系结构待后续收敛 | 保留 |
| `promotion_relegation_mapping` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `provider_entity_mappings` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `provider_request_logs` | 162 | 有 | 有 | 有 | 无 | 1/0 | 有（162 行） | 保留 |
| `provider_team_identity_crosswalks` | 16 | 有 | 有 | 有 | 无 | 1/0 | 有（16 行） | 保留 |
| `quota_usage` | 9 | 有 | 有 | 有 | 无 | 0/0 | 有（9 行） | 保留 |
| `raw_payload` | 220 | 有 | 有 | 有 | 无 | 0/0 | 有（220 行） | 保留 |
| `raw_payload_references` | 0 | 无 | 无 | 无 | 无 | 0/1 | 外键目标 | 保留 |
| `read_model_checkpoint` | 8 | 有 | 有 | 无 | 有 | 0/0 | 有（8 行） | 保留 |
| `recommendation_locks` | 0 | 有 | 无 | 无 | 有 | 3/2 | 安全锁账本 | 保留 |
| `recommendations` | 0 | 有 | 有 | 无 | 有 | 2/2 | 正式推荐安全账本 | 保留 |
| `referees` | 0 | 无 | 无 | 无 | 无 | 0/1 | 外键目标 | 保留 |
| `registered_roster_snapshots` | 0 | 有 | 有 | 无 | 无 | 0/0 | roster 运行契约 | 保留 |
| `release_audit` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `release_candidate` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `replay_checkpoint` | 0 | 无 | 无 | 无 | 无 | 1/0 | 关系结构待后续收敛 | 保留 |
| `replay_event` | 0 | 无 | 无 | 无 | 无 | 1/0 | 关系结构待后续收敛 | 保留 |
| `replay_run` | 0 | 无 | 无 | 无 | 无 | 0/5 | 外键目标 | 保留 |
| `restore_run` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `results` | 0 | 有 | 无 | 无 | 有 | 1/1 | 结算读取契约 | 保留 |
| `retention_audit` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `season_rollover_plan` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `seasons` | 0 | 无 | 无 | 无 | 无 | 1/3 | 关系结构待后续收敛 | 保留 |
| `security_audit_event` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `settlements` | 0 | 有 | 有 | 无 | 有 | 4/0 | 结算安全账本 | 保留 |
| `shadow_comparison_record` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `shadow_run` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `shadow_strategy_candidate` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `shadow_strategy_evaluation` | 0 | 有 | 无 | 无 | 有 | 0/0 | Dashboard 读取契约 | 保留 |
| `shadow_strategy_event` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `shadow_strategy_lock` | 0 | 有 | 无 | 无 | 有 | 0/0 | 安全锁账本 | 保留 |
| `shadow_strategy_run` | 0 | 有 | 无 | 无 | 有 | 0/0 | Dashboard 读取契约 | 保留 |
| `shadow_strategy_settlement` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `slo_evaluation` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `squads` | 0 | 无 | 无 | 无 | 无 | 3/0 | 关系结构待后续收敛 | 保留 |
| `stage7i_lifecycle_event` | 0 | 有 | 有 | 有 | 无 | 0/0 | supervision 运行契约 | 保留 |
| `stage7i_lifecycle_heartbeat` | 0 | 有 | 有 | 有 | 无 | 0/0 | supervision 运行契约 | 保留 |
| `stage7i_lifecycle_run` | 0 | 有 | 有 | 有 | 无 | 0/0 | supervision 运行契约 | 保留 |
| `stages` | 0 | 无 | 无 | 无 | 无 | 1/1 | 关系结构待后续收敛 | 保留 |
| `structured_lineup_players` | 0 | 有 | 有 | 有 | 无 | 2/0 | lineup 运行契约 | 保留 |
| `structured_lineup_snapshots` | 0 | 有 | 有 | 有 | 无 | 0/1 | lineup 运行契约 | 保留 |
| `suspensions` | 0 | 无 | 无 | 无 | 无 | 2/0 | 关系结构待后续收敛 | 保留 |
| `sync_cursors` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `system_metadata` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0038） |
| `t30_validation_snapshots` | 0 | 有 | 有 | 有 | 无 | 0/0 | prematch 运行契约 | 保留 |
| `team_identity_crosswalks` | 16 | 有 | 有 | 无 | 无 | 0/0 | 有（16 行） | 保留 |
| `team_lineup_baselines` | 0 | 有 | 有 | 有 | 无 | 0/0 | lineup 运行契约 | 保留 |
| `team_rating_snapshots` | 16 | 有 | 有 | 有 | 无 | 1/0 | 有（16 行） | 保留 |
| `team_ratings` | 0 | 无 | 无 | 无 | 无 | 1/0 | 关系结构待后续收敛 | 保留 |
| `team_value_asof_artifacts` | 0 | 有 | 有 | 无 | 无 | 0/0 | FAH 运行契约 | 保留 |
| `team_xg_match` | 104 | 有 | 有 | 有 | 无 | 0/0 | 有（104 行） | 保留 |
| `team_xg_rolling_snapshot` | 28 | 有 | 有 | 有 | 无 | 0/0 | 有（28 行） | 保留 |
| `teams` | 0 | 无 | 无 | 无 | 无 | 0/7 | 外键目标 | 保留 |
| `tournament_operations_plan` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `tournament_profile` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `tournament_readiness_audit` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `transfermarkt_player_references` | 0 | 有 | 有 | 有 | 无 | 0/0 | player identity 运行契约 | 保留 |
| `venues` | 0 | 无 | 无 | 无 | 无 | 0/1 | 外键目标 | 保留 |
| `weather_observations` | 0 | 无 | 无 | 无 | 无 | 1/0 | 关系结构待后续收敛 | 保留 |

**本 PR 直接 drop**

- migration `0038_drop_unused_system_metadata`：`system_metadata`。
- migration `0039_drop_evidence_backed_dead_tables`：
  `api_request_audit`、`audit_events`、`backup_run`、`challenger_model`、
  `data_quality_runs`、`dataset_sources`、`dependency_risk`、
  `forward_cycle_checkpoint`、`forward_operational_alert`、
  `forward_result_event`、`forward_scheduler_run`、
  `forward_state_transition`、`freshness_alerts`、
  `league_team_membership`、`market_quality_assessment`、
  `migration_dry_run`、`migration_quarantine_record`、
  `migration_source_asset`、`migration_validation_record`、
  `model_gate_decision`、`operational_alert`、
  `operational_metric_snapshot`、`operations_check_result`、
  `operations_cycle`、`promotion_relegation_mapping`、
  `provider_entity_mappings`、`release_audit`、`release_candidate`、
  `restore_run`、`retention_audit`、`season_rollover_plan`、
  `security_audit_event`、`shadow_comparison_record`、`shadow_run`、
  `shadow_strategy_candidate`、`shadow_strategy_event`、
  `shadow_strategy_settlement`、`slo_evaluation`、`sync_cursors`、
  `tournament_operations_plan`、`tournament_profile`、
  `tournament_readiness_audit`。
- 上述 43 表均为 0 行、0 入站/出站外键、0 生产读写、0 任务、0 报表，
  不含独有数据；只存在的 ORM 注册、历史脚本或旧测试未作为保留理由。
- 数据迁移行数为 0；每张表的规范化空集 hash 均为 SHA-256
  `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945`。
- 历史 migration 原样保留；`0038`/`0039` downgrade 恢复原列、唯一约束
  和索引，upgrade 再次正式删除。

**迁移后 drop**

- 无。没有非空重复表同时满足唯一权威已确认、字段身份可逆和 hash 对账
  三项直接证据，因此本任务不搬运或删除任何业务数据。

**保持原状并继续调查**

- 赔率身份组：`odds_observations`、`future_market_observation`、
  `matchday_market_observations`。缺少跨表完整 identity/hash 迁移证据，
  由 ARCH-P1-02 处理。
- 球队/球员身份组：`football_data_team_crosswalks`、
  `team_identity_crosswalks`、
  `provider_team_identity_crosswalks`、`player_identity_crosswalks`、
  `player_identity_mappings`。存在实际 Repository 路径、有效数据或
  canonical 对账依赖，由 ARCH-P1-03 处理。
- 其余保留表的逐表理由以矩阵为准：有非空数据、生产读写、任务、报表、
  安全账本或外键中的至少一项直接证据。只有外键/关系结构证据的表继续
  调查，不重命名、不隔离、不提前删除。
- `alembic_version` 是 migration 控制表，不是业务表，不得删除。

**本轮验收回执**

- PR：`#379`；
- implementation head：
  `1a07244747c917afdbcfad4cbcfcde0f64daf831`；
- implementation exact-head CI：run `29978871376`，`verify`、
  `staging-parity`、`predeploy-e2e` 全绿；
- staging release SHA：
  `1a07244747c917afdbcfad4cbcfcde0f64daf831`；
- staging migration：
  `0038_drop_unused_system_metadata`；
- migration 往返：
  `0038 -> 0037 -> 0038` 通过；downgrade 后表存在、0 行且原四列 schema
  恢复，upgrade 后表再次不存在；
- staging 表数：`144 -> 143`，仅删除 `system_metadata`；
- 20 轮真实 HTTP 只读检查全部通过；
- Provider request logs：`162 -> 162`，增量 0；
- staging 全业务表 DML 统计：
  `insert/update/delete = 58158/345/0 -> 58158/345/0`，增量 0；
- `recommendations=0`、`recommendation_locks=0`、
  `gate5_recommendation_lock_event=0`、`settlements=0`、
  `shadow_strategy_lock=0`；
- `W2_PROVIDER_CALLS_DISABLED=true`、
  `W2_PROVIDER_SCHEDULER_ENABLED=false`、
  `W2_RECOMMENDATION_ENABLED=false`、`W2_CANDIDATE_ENABLED=false`、
  `W2_PRODUCTION_RELEASE=false`；
- API、worker、scheduler、web、PostgreSQL、Redis 全部 healthy；
  API/Web release SHA 与 staging release SHA 一致。

**验收**

```text
DEAD_TABLES_EVIDENCE_BACKED_AND_DROPPED
NO_BUSINESS_HISTORY_DELETED
```

---

## ARCH-P1-02：赔率表收敛

- [ ] 从活跃赔率表中选定：
  - 一张唯一 append-only 历史表；
  - 一张当前盘口投影（表或视图）。
- [ ] 不创建第二套历史表。
- [ ] 完成历史数据迁移和 identity/hash 对账。
- [ ] 停止 legacy 写入，禁止新增或保留双写过渡。
- [ ] 所有读路径切到 canonical 历史 + 当前投影。
- [ ] 删除 legacy ORM、Repository、脚本、测试、配置及其全部运行时引用。
- [ ] 在同一 PR 使用新 migration drop 已完成迁移且证据充分的旧表；
  不创建 archive、backup、兼容 view 或替代 fallback。
- [ ] 证据不足的表保持原状并继续调查，不重命名隔离。
- [ ] migration upgrade/downgrade、行数/hash 对账、完整 CI 和 staging 验收通过。
- [ ] PR 合并。

**验收**

```text
CANONICAL_ODDS_HISTORY_AUTHORITY_COUNT = 1
CURRENT_MARKET_PROJECTION_AUTHORITY_COUNT = 1
```

---

## ARCH-P1-03：球队身份 Crosswalk 收敛

- [ ] 盘点全部球队身份和 provider crosswalk 表。
- [ ] 指定 canonical team 体系为唯一权威。
- [ ] 迁移有效映射及 review provenance。
- [ ] 其他 crosswalk 在有效映射迁移及对账完成后停止写入，并在同一 PR
  删除代码引用与正式 drop；证据不足的表保持原状继续调查。
- [ ] provider IDs 仅作 provenance，不再作为模型主身份。
- [ ] 完成 fixture、history、rating、lineup 读取对账。
- [ ] PR 合并。

**验收**

```text
CANONICAL_TEAM_IDENTITY_AUTHORITY_COUNT = 1
```

---

## ARCH-P1-04：Dashboard 单一 Read Model

老板已决定使用现有 `read_model_checkpoint` 作为唯一页面投影。

- [ ] 审计 `read_model_checkpoint` 的 schema、写入者和当前覆盖。
- [ ] 确保它可以承载 Boss Console 当前所需全部字段。
- [ ] 所有 Dashboard 生产端点只读该投影。
- [ ] 删除：
  - seed fallback；
  - legacy fallback；
  - runtime JSON fallback；
  - reports fallback；
  - live/frozen 自动选择；
  - 前端市场概率重算。
- [ ] frozen artifact 仅保留内部审计/canary。
- [ ] API 返回 projection version/hash、source event、last projected time。
- [ ] old/new 全部当前比赛语义对账。
- [ ] 15/30 场 Dashboard 行为和视觉不退化。
- [ ] PR 合并。

**验收**

```text
DASHBOARD_READ_AUTHORITY = READ_MODEL_CHECKPOINT_ONLY
PRODUCTION_FALLBACK_COUNT = 0
```

---

## ARCH-P1-05：部署改为 CI 构建、服务器拉镜像

- [ ] 合并 4 个 Python Dockerfile 为 1 个多 target 或单镜像多 command 文件。
- [ ] API、Worker、Scheduler、Migration 共用同一 Python 镜像。
- [ ] Web 保留独立镜像。
- [ ] CI：
  - 测试；
  - 构建镜像；
  - 使用 BuildKit cache；
  - 推送 GHCR；
  - 记录 SHA tag 和 digest；
  - 执行镜像 smoke test。
- [ ] staging Compose 从 `build:` 改为不可变 digest `image:`。
- [ ] 服务器部署只执行：
  - `docker compose pull`；
  - migration job；
  - restart affected services；
  - health/readiness；
  - release record。
- [ ] 删除服务器上传源码、安装依赖、构建五个镜像的正式流程。
- [ ] 回滚使用上一版本 digest，不允许回滚时重建。
- [ ] 验证部署时间：
  - Web-only ≤ 3 分钟；
  - Python change ≤ 5 分钟；
  - rollback ≤ 2 分钟。
- [ ] PR 合并。

**验收**

```text
CI_IMAGE_BUILD_AUTHORITY = PASS
SERVER_BUILD_COUNT = 0
SERVER_DEPENDENCY_INSTALL_COUNT = 0
```

---

## ARCH-P1-06：Compose 环境变量去重

- [ ] 将 api/worker/scheduler 重复环境变量提取为 `x-common-env` anchor。
- [ ] 保留服务级差异。
- [ ] 生成展开后环境变量对账。
- [ ] 安全开关值不得变化。
- [ ] Compose config、CI、staging smoke 通过。
- [ ] PR 合并。

---

## ARCH-P1-08：P1 总验收

- [ ] 一套赔率历史。
- [ ] 一套当前盘口投影。
- [ ] 一套 canonical team identity。
- [ ] Dashboard 单一 read model。
- [ ] CI 镜像发布。
- [ ] 服务器 pull-only。
- [ ] 无生产 fallback。
- [ ] P1 完整 CI 与 staging 验收通过。
- [ ] 人工验收。

**完成标准**

```text
P1_ARCHITECTURE_CONVERGENCE_PASS
```

---

# 阶段 P2：卫生治理，可穿插但不得抢占 P0/P1

## ARCH-P2-01：Scripts 整理

- [ ] 生成脚本使用清单。
- [ ] 保留实际被 CI、部署、运维和当前功能调用的脚本。
- [ ] 历史 stage 脚本移入 `scripts/archive/`。
- [ ] archive 脚本不能进入正式运行路径。
- [ ] 更新脚本索引。
- [ ] PR 合并。

---

## ARCH-P2-02：Docs 整理

- [ ] 日期型一次性证据移入 `docs/archive/`。
- [ ] 同一审计只保留最新权威版本。
- [ ] 旧文档添加 `SUPERSEDED_BY`。
- [ ] 不删除仍有审计价值的历史证据。
- [ ] PR 合并。

---

## ARCH-P2-03：本地垃圾清理

此任务只清理开发机器，不进入业务代码 PR：

- [ ] 清理 `.worktrees/`。
- [ ] 清理过期 `.local/` 历史数据库。
- [ ] 清理不再使用的 `runtime/` stage 目录。
- [ ] 清理已确认无用的本地分支。
- [ ] 保留当前工作和审计备份。
- [ ] 记录释放空间。

---

## ARCH-P2-04：项目状态记录收敛

- [ ] `PROJECT_STATE.yaml` 作为唯一机器可读状态。
- [ ] `PROJECT_LEDGER.md` 只记录人工决定、批准和拒绝。
- [ ] `NEXT_ACTION.md` 停止重复记录 SHA/CI/状态，改为链接总清单，或在迁移完成后删除。
- [ ] GitHub 可查询的 SHA、CI 不再在多份文档重复维护。
- [ ] PR 合并。

---

## ARCH-P2-05：最终架构收敛验收

- [ ] P0 全部完成。
- [ ] P1 全部完成。
- [ ] P2 全部完成。
- [ ] 无竞争运行时权威。
- [ ] 无生产 fallback。
- [ ] 无服务器源码构建。
- [ ] 所有表 drop 均有零依赖或迁移后 hash 对账的直接证据。
- [ ] 完整 CI 与 staging 验收通过。
- [ ] 老板最终验收。

**最终状态**

```text
W2_ARCHITECTURE_CONVERGENCE_COMPLETE
```

---

## 四、每个任务的 GitHub 更新格式

每个 PR 开始时，在对应任务下追加：

```text
Status: IN_PROGRESS
Branch:
PR:
Base SHA:
Started at:
Owner:
```

发生阻塞时：

```text
Status: BLOCKED
Blocker:
Evidence:
Next required decision:
```

完成但尚未合并时：

```text
Status: IMPLEMENTED_PENDING_ACCEPTANCE
Implementation SHA:
CI run:
Staging SHA:
Evidence:
Rollback:
```

只有合并和验收后：

```text
Status: DONE
Merged PR:
Merge SHA:
CI run:
Staging acceptance:
Completed at:
```

然后才把：

```markdown
- [ ]
```

改为：

```markdown
- [x]
```

---

## 五、每个 PR 的强制说明

每个架构收敛 PR 必须在描述中回答：

```text
1. 本 PR 删除了哪个事实来源、fallback 或重复路径？
2. 本 PR 是否新增数据库表？若是，违反红线，必须停止。
3. 本 PR 是否新增配置文件？若是，必须说明为什么不是新运行权威。
4. 本 PR 的唯一业务范围是什么？
5. 如何回滚？
6. old/new 如何对账？
7. Provider/Formal/Lock/Production 开关是否保持不变？
8. 完整 CI 与 staging 证据在哪里？
```

---

## 六、立即停止条件

出现任一情况立即停止当前任务：

```text
继续往 PR #370 添加架构代码
一个 PR 同时处理两个以上清单任务
新增竞争性的表、配置或 fallback
删除仍有读写的数据
未备份就 drop 表
放宽安全开关
修改模型数学
CI 未通过
staging 对账失败
历史数据 hash/count 异常
Dashboard 语义发生未批准变化
```

停止后在本文件记录 `BLOCKED`，不得自行绕过。

---

# Codex 首次执行指令

```text
W2 ARCHITECTURE CONVERGENCE — INITIALIZATION ONLY

Boss decision is final.

Do not modify production code yet.

1. Resolve the latest repository main SHA, PR #370 head, staging SHA and
   migration head.

2. Create a new docs-only branch and Draft PR.

3. Add exactly one master tracking file:

docs/operations/architecture_convergence/
W2_ARCHITECTURE_CONVERGENCE_MASTER_CHECKLIST.md

Use the complete supplied checklist verbatim.

4. Record the verified baseline in that file.

5. Record FEATURE_DEVELOPMENT_FREEZE and all red lines.

6. Do not create any other dated architecture context document.

7. Do not modify PR #370.

8. Run complete CI.

9. Return:

branch
PR
implementation SHA
CI run
changed files
confirmation that production behavior did not change

Final state for this first task may only be:

MASTER_CHECKLIST_COMMITTED
FEATURE_DEVELOPMENT_FREEZE_RECORDED
READY_FOR_PR370_SCOPE_CLOSURE

Always preserve:

FORMAL_DISABLED
LOCK_DISABLED
PRODUCTION_DISABLED
MANUAL_APPROVAL_REQUIRED
```

完成 ARCH-00 并合并后，才执行 ARCH-01。之后严格按清单顺序逐项执行。

---

## 七、ARCH-00 执行记录

```text
Status: DONE
Branch: codex/w2-architecture-convergence-master-checklist
PR: #371 (Merged)
Base SHA: a80bccaadc68f8bd691b45b46f25c10539473c0c
Started at: 2026-07-22T21:30:56+0800
Owner: Codex
Merged PR: #371
Merge SHA: 09ca14a969b835314c93c122b80c3cfa1bbf9c6c
CI run: 29924431421
Staging acceptance: DOCS_ONLY_BASELINE_READ_ONLY_VERIFIED
Completed at: 2026-07-22T13:40:14Z
```

### 已核验基线

| 基线 | 已核验值 | 核验说明 |
| --- | --- | --- |
| GitHub `main` SHA | `a80bccaadc68f8bd691b45b46f25c10539473c0c` | 2026-07-22 从 `github-w2/main` fetch 后核验 |
| PR #370 exact head | `e6329a2a9059133a82fdc62bd703fad2893f2e1f` | GitHub PR API；Draft、OPEN，head `codex/w2-factor-model-remediation-master`，base `codex/w2-analysis-recommendation-closure` |
| staging SHA | `81b4dd2bd4a23d6ad8f5782abf05f904a88c38a8` | 只读 SSH 核验 `/opt/w2/current` 与 `/opt/w2/shared/release.env` 一致 |
| `main` migration head | `0023_create_checkpoint_refresh_schedule` | 在上述 `main` SHA 独立工作树执行 `alembic heads` |
| PR #370 migration head | `0036_require_reviewed_player_identity` | 在 PR #370 exact head 工作树执行 `alembic heads` |
| staging migration current | `0036_require_reviewed_player_identity` | 只读查询 staging PostgreSQL `alembic_version`；与 PR #370 migration head 一致 |

基线核验时间：`2026-07-22`（Asia/Shanghai）。本记录明确保留 `main` 与 PR #370/staging 的迁移差异，不将尚未合并的 PR #370 revision 误记为 `main` migration head。

### 冻结与红线记录

```text
FEATURE_DEVELOPMENT_FREEZE=RECORDED
RED_LINES_RECORDED=14/14
PR_370_ARCHITECTURE_SCOPE_CHANGE=0
PRODUCTION_CODE_CHANGED=0
FORMAL_DISABLED
LOCK_DISABLED
PRODUCTION_DISABLED
MANUAL_APPROVAL_REQUIRED
```

staging 只读核验同时确认：`W2_FORMAL_RECOMMENDATION_ENABLED=false`、`W2_RECOMMENDATION_ENABLED=false`、`W2_PRODUCTION_RELEASE=false`、`W2_PROVIDER_CALLS_DISABLED=true`、`W2_PROVIDER_SCHEDULER_ENABLED=false`。本 PR 不修改这些安全边界。
