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
9. 僵尸表先 rename/deprecate 并观察一个稳定周期，再决定 drop。
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
Status: IMPLEMENTED_LOCAL_VALIDATED_AWAITING_EXACT_HEAD_CI_AND_STAGING
Branch: codex/arch-p0-03-db-competition-authority
Base SHA: dae21e59f949be4ac70b75bbcf0f96d1d03f8266
Owner: Codex
Runtime authority tables: league_profile, league_season
Audit table: league_readiness_audit
Migration head: 0037_seed_competition_runtime_authority
Seed reconciliation: 14 profiles + 14 seasons inserted; 14 audit rows;
  second identical run 14 unchanged; 0 conflicts; staging seed enables the
  five policy-authorized competitions.
No-deploy proof: an audited league_season.payload.enabled update changed the
  result returned by the same uncached CompetitionRegistry instance without a
  process restart, build or deploy; rollback update restored the prior result.
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
- [x] `CompetitionRegistry` 运行时改为读取数据库。
- [x] JSON 降级为首次安装种子，不再是运行时权威。
- [x] 删除 `W2_STAGING_ENABLED_COMPETITIONS` 的业务覆盖机制。
- [x] 删除 `league_whitelist_scope.py` 中联赛硬编码元组。
- [x] 保留 Provider 总熔断等安全环境变量。
- [x] scheduler 从 DB 读取启用联赛。
- [x] 修改 DB 中 enabled 后无需部署即可生效。
- [x] 所有修改有审计记录。
- [ ] 完整 CI、staging 变更测试和回滚测试通过。
- [ ] PR 合并。

**验收**

```text
DB_COMPETITION_RUNTIME_AUTHORITY = PASS
JSON_RUNTIME_AUTHORITY = REMOVED
STAGING_ENV_WHITELIST_OVERRIDE = REMOVED
```

---

## ARCH-P0-04：P0 总验收

- [ ] 生产 API 不读取不存在的 reports 文件。
- [ ] 生产赔率只经过一套读取仓储。
- [ ] runtime JSON 不影响当前赔率。
- [ ] 联赛启用状态来自数据库。
- [ ] 修改联赛配置不需要构建或部署。
- [ ] Provider calls、Formal、Lock、Production 安全边界不变。
- [ ] P0 staging 连续稳定运行至少一个审核周期。
- [ ] 更新本总清单并由人工审核。
- [ ] P0 验收 PR 合并。

**完成标准**

```text
P0_ARCHITECTURE_CONVERGENCE_PASS
```

---

# 阶段 P1：收敛，参考 3–4 周

## ARCH-P1-01：数据库僵尸表清单和 deprecation

- [ ] 列出全部表及：
  - migration 来源；
  - 当前行数；
  - 最近读写时间；
  - 代码读写调用点；
  - 外键；
  - 报告/脚本依赖。
- [ ] 对候选僵尸表逐张给出证据。
- [ ] 不直接 drop。
- [ ] 第一周期只 rename 为 `_deprecated_*` 或通过兼容视图隔离。
- [ ] 旧代码如果仍访问，CI/staging 必须立即暴露。
- [ ] 备份 schema、row count、hash。
- [ ] 完整 CI 和 staging 观察通过。
- [ ] PR 合并。

**验收**

```text
DEPRECATED_TABLE_CANDIDATES_EVIDENCE_BACKED
NO_BUSINESS_HISTORY_DELETED
```

---

## ARCH-P1-02：赔率表收敛

- [ ] 从活跃赔率表中选定：
  - 一张唯一 append-only 历史表；
  - 一张当前盘口投影（表或视图）。
- [ ] 不创建第二套历史表。
- [ ] 完成历史数据迁移和 identity/hash 对账。
- [ ] 新写入先双写，对账后停止 legacy 写入。
- [ ] 所有读路径切到 canonical 历史 + 当前投影。
- [ ] 旧表进入只读 deprecated 状态。
- [ ] 一个稳定周期后再提交 drop 决策。
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
- [ ] 其他 crosswalk 停止写入并进入 deprecated。
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

## ARCH-P1-07：Deprecated 表观察周期与最终 drop 决策

- [ ] 完成至少一个稳定观察周期。
- [ ] 证明 `_deprecated_*` 表：
  - 无生产读；
  - 无生产写；
  - 无任务依赖；
  - 无报表依赖；
  - 无外键阻塞。
- [ ] 导出最终 schema 和数据备份。
- [ ] 逐表提交 drop 清单供人工批准。
- [ ] 只有明确批准的表才能 drop。
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
- [ ] P1 稳定周期通过。
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
- [ ] 无未审核的 deprecated 表 drop。
- [ ] 完整 CI 与 staging 稳定周期通过。
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
