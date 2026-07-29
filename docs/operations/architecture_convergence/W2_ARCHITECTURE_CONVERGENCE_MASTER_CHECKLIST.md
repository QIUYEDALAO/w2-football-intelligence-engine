# W2 架构收敛与 EVAL 能力建设总清单（v3）

> `PROJECT_STATE.yaml` 是 W2 **唯一当前机器可读状态快照**。
> 本文件是 W2 **唯一任务顺序、任务规格和已合并完成回执权威**。
> 旧版清单（v2 及更早）已整体废止，
> 其完整内容保留在本文件之前的 git 历史中，审计坐标见第二节台账。
> 老板 2026-07-24 决定：任务清单只保留本版本，不再维护旧清单文本。
>
> 维护规则：
> - 只有完整 CI 通过、必要的 staging 验收完成并合并后，才允许把 `[ ]` 改为 `[x]`。
> - 每个任务状态流转与 PR 强制说明格式见第七节。
> - 本文件的任何结构性修改（增删任务、改顺序、改红线）必须走 docs PR 并由老板合并。

---

## 一、基线（2026-07-24 核验）

- `github-w2/main` 顶端：`75e4993`（PR #388，ARCH-P1-04B 收尾）
- migration head：`0041_converge_odds_history_and_projection`
- 生产读取权威：`read_model_checkpoint`（API 纯投影读取，fail-closed）
- 赔率权威：`matchday_market_observations`（唯一历史）+ 当前盘口投影视图
- 竞赛配置权威：`league_profile` / `league_season`（DB 热切换）
- 安全开关：Formal / Lock / Production 关闭；`W2_PROVIDER_CALLS_DISABLED=true` 等熔断保持

---

## 二、已完成任务台账（审计坐标；实施细节见各 Merge SHA 的 git 历史与 PR）

| 任务 | PR | Merge SHA | 一句话结论 |
|---|---|---|---|
| ARCH-00 总清单建立 | #371 | `09ca14a9` | 清单与功能冻结红线入库 |
| ARCH-01 PR#370 收口 | #374 | `160a6750` | 已验证基线并入 main，PR #370 关闭 |
| ARCH-P0-01 报表读取删除 | #375 | `1e9e811d` | 生产 API 报表文件读取 = 0，静态守卫落地 |
| ARCH-P0-02 赔率读取收敛 | #376 | `dae21e59` | 唯一读取入口 `matchday_market_observations` |
| ARCH-P0-03 联赛白名单入库 | #377 | `7bd5088b` | DB 竞赛权威 + 热切换，JSON/env 业务覆盖删除 |
| ARCH-P0-04 P0 总验收 | #378 | `d62e3351` | P0_ARCHITECTURE_CONVERGENCE_PASS |
| ARCH-P1-01 僵尸表删除 | #379 | `76201af8` | 144→66 表，78 张僵尸表证据化删除（0038–0040） |
| P1-01 收口 + 清单修订 | #380 | `8af05ddb` | P1 顺序调整获批（04 拆分、03 后移、新增 07） |
| ARCH-P1-02 赔率表收敛 | #381 | `f53b073f` | 唯一 append-only 历史 + 投影视图（0041，断言式 drop） |
| HYGIENE 清单顺序修正 | #382 | `db3fd12f` | 清单序列一致性修正 |
| ARCH-HYGIENE-01 | #383 | `748b50e5` | 生成审计产物退出 Git |
| ARCH-HYGIENE-02 | #384 | `1e252d73` | Scripts 权威盘点与证据化删除（取代 P2-01） |
| ARCH-P1-04A 评估持久化 | #385 | `aa59b61d` | 事件驱动写侧投影管线（收口 #386 `46aa8d36`） |
| ARCH-P1-04B Dashboard 读切换 | #387 | `7ffdc0fe` | API 降为 988 行纯投影读取，生产 fallback = 0（收口 #388 `75e49932`） |

---

## 三、执行红线

### 永久红线（不随任何阶段解除）

1. 每个 PR 只解决一个清单任务，必须可独立回滚；不得自行并行化或跨任务顺手重构。
2. 不新增竞争性的事实表、配置文件或 fallback；每类事实只有一个权威。
3. 删除或 drop 前必须证明零读、零写、零任务、零报表、零外键阻塞；历史业务数据不删除。
4. drop migration 的 upgrade 必须先断言（count / 覆盖检查）再删除（0041 模式）。
5. Formal、Lock、Production 开关保持关闭；开放它们是独立的产品决定，不在本清单任何授权范围内。
6. Provider 熔断等安全环境变量不动。
7. 模型数学只允许在 EVAL-02B 门禁通过的解冻点上变化，其余一律不动。
8. 不以本地测试或 Markdown 报告代替 GitHub CI 和 staging 证据；不用 `[skip ci]` 作最终验收提交。
9. 当前机器状态只更新 `PROJECT_STATE.yaml`；任务顺序、规格和已合并完成回执只更新本文件；
   不再创建重复的日期型上下文文档。
10. 修改 decision contract 结构时，必须同步 `src/w2/domain/decision_contract.py` 校验器、
    `tests/contract/test_api_projection_read_authority.py` 守卫及全部合同测试。
11. 每个任务必须附**资产账本**：新增了哪些表/文件/配置（目标 0），删除了哪些。

### 冻结解除边界（老板 2026-07-24 全权授权，固化执行）

ARCH-P1-08 通过后，功能冻结部分解除：**仅允许本清单阶段 B 的任务（B1~B7、OPS-01）**，
逐字按各任务"范围/不做"执行。清单外的任何功能想法记入本文件末尾"待议区"，不实施。

### 已授权决策基准（到点直接执行，判定过程写入本文件，无需请示）

**（a）EVAL-01A 建表判定**：复用优先。先逐一核对 `results`、`settlements` 及 P1-08 裁决后的
`shadow_strategy_*`；只有（一）现有表无法承载 append-only 语义、（二）复用造成列语义扭曲、
（三）文件记录无法无损映射——三条**全部**成立时，才新建唯一一张 `outcome_ledger`。
建表须同 PR 完成迁移对账并删除文件路径，migration 带 downgrade，三条判定证据写入本文件。

**（b）EVAL-02 预注册参数（初值固化；修改只能通过新的预注册条目，禁止回溯调整）**：
- 分歧成因分类器：`movement_ev_share > 0.5` → `MOVEMENT_CREATED_DIVERGENCE`；
  `divergence_age_ratio ≥ 0.6` 且非 MOVED → `STABLE_DIVERGENCE`；其余 → `INDETERMINATE`（按 MOVED 保守处理）。
- δ 溢价：初始 0（只标注不拦截）。ADVISORY 层 canonical 已结算样本 ≥50 场后自动标定：
  δ = max(0, STRICT 与 ADVISORY 层 CLV 均值差的 80% bootstrap 置信下界)，加到 ADVISORY 的
  EV 准入门槛；每新增 50 场或每 90 天重标定。扣除 δ 后滚动 CLV ≤ 0 → 该层自动降为只出 WATCH。
- 首发增量门禁：每联赛×每市场配对样本 ≥120 场；门禁 = 配对 log loss 改善的
  95% bootstrap（10,000 次重采样）置信下界 > 0；严格时间顺序切分。通过即解冻，
  报告写入本文件生效；每 90 天或每新增 60 场滚动复验，置信区间包含 0 即自动回冻为 0。

---

## 四、执行顺序与任务规格（唯一有效任务列表）

任务必须严格按此顺序执行。每任务开工：`git fetch github-w2 main` 拉新分支，
本文件写 `Status: IN_PROGRESS`；完成 = 完整 CI + staging 验收 + 合并 + 状态翻 DONE。

### 阶段 A：架构收尾

---

#### A1. ARCH-GOVERNANCE-01：合并前就绪 + 合并后清单一致性双门禁

```text
Status: DONE
PR: #393
Merge SHA: 35fcac0d99573556c5e9f7a41822e153783efa73
Current required check: CI_REQUIRED
```

PR #393 是该历史任务的实际实施坐标；此前 PRE/POST 专用门禁已在后续获授权精简中退役，
不是当前 required checks 或运行权威。当前分支保护只保留 `CI_REQUIRED`。

- [x] 历史实施 PR #393 曾落地双门禁；后续获授权退役，不再作为当前 required checks。
- [x] 历史实施完整 CI 通过并合并；当前 required check 为 `CI_REQUIRED`。

---

#### A2. ARCH-P1-04C：合同层与死代码清理

```text
Status: DONE
PR: #395
Merge SHA: 6eeb411747a1cef624ff4780dbad87d4cec4b26d
```

**目标**：删除全部新旧合同并存代码与 04B 后确认的死代码；每处删除附零引用证据。

**范围（逐项处理，允许 ≤3 个提交但同一 PR）**：
- [ ] `src/w2/domain/legacy_decision_shim.py` 整文件删除（113 行）。
- [ ] `src/w2/domain/decision_adapter.py`（986 行）中 legacy→V3 转换路径删除；V3 构造保留；
      凡只被 shim/旧测试引用的函数一并删。
- [ ] `src/w2/prematch/analysis_calculator.py` 中 pre-LMM frozen artifact 兼容分支
      （注释 "Backward compatibility for immutable pre-LMM frozen artifacts" 及
      `_public_market_is_legacy_pick` 调用链）。
- [ ] `src/w2/dashboard/day_view.py`：`_scoreline_simulations` 的 `pricing_shadow` 兼容读
      （保留 `simulation` 主路径）；死函数 `_is_decision_tier`。
- [ ] **旧 F10 首发因子废弃**：`src/w2/features/live_factors.py` 中 `F10_LINEUPS` 相关函数
      （专家评审确认未接入主 `FeatureInputs`）；并在 `src/w2/domain/factor_registry.py`
      登记 LMM 链为唯一首发因子来源。此项是 EVAL-02B 的硬前置。
- [ ] 删除后全库死代码复核，剩余疑似项只记录到待议区，不顺手删。

**不做**：不动 analysis_calculator 计算语义；不动 API；不动表。
**验收**：`LEGACY_DECISION_CONTRACT_CODE = 0`；`F10_LINEUPS` 全库零引用；全量测试与 04B 守卫绿。
**资产账本**：新增 0；删除 ≥1,100 行合同转换 + F10 死代码。
- [ ] PR 合并。

---

#### A3. ARCH-P1-03：球队身份 Crosswalk 收敛

```text
Status: DONE
PR: #419
Merge SHA: 5026919fe1b1bbe2d5c6dfd67a2f70b6b0f59768
```

待收敛组：`football_data_team_crosswalks`、`team_identity_crosswalks`、
`provider_team_identity_crosswalks`、`player_identity_crosswalks`、`player_identity_mappings`。

历史实施记录（仅属于 A3，不是顶层任务）：ARCH-P1-03A、ARCH-P1-03B、
ARCH-P1-03C、ARCH-P1-03B-R1。

- [ ] 盘点全部球队/球员身份与 provider crosswalk 表。
- [ ] canonical team / player 体系为唯一权威；迁移有效映射及 review provenance。
- [ ] 其余表停止写入，零引用证明后同 PR 断言式 drop；证据不足的保持原状继续调查。
- [ ] provider IDs 仅作 provenance，不再作为模型主身份。
- [ ] fixture、history、rating、lineup 读取对账。
- [ ] **追加**：用 3 场真实比赛演示 canonical player ↔ provider lineup 球员唯一联接查询
      （EVAL-02B"缺阵分钟占比"的前置能力）。
- [ ] PR 合并。

**验收**：`CANONICAL_TEAM_IDENTITY_AUTHORITY_COUNT = 1`。
**资产账本**：目标净减 ≥3 张表。

---

#### A4. ARCH-P1-05：部署改为 CI 构建镜像、服务器 pull-only

```text
Status: DONE
PR: #420
Merge SHA: ba8f10e1809c491a112c13eec28303ceb67d7f74
```

- [x] 4 个 Python Dockerfile 合并为 1 个多 target/多 command；Web 独立镜像保留。
- [x] CI：测试 → BuildKit cache 构建 → 推 GHCR → 记录 SHA tag 与 digest → 镜像 smoke test。
- [x] staging Compose 从 `build:` 改为不可变 digest `image:`。
- [x] 服务器部署只执行 pull → migration job → restart → health → release record。
- [x] 删除服务器上传源码、安装依赖、构建镜像的正式流程；回滚用上一 digest。
- [x] 部署时间验证已执行：Web warm 11 秒、full-stack warm 20 秒、rollback 10 秒；
  cold pull end-to-end 实测 423 秒，BLOCKED_BY_NETWORK，未宣称 Python ≤5 分钟 SLO 通过。
- [x] PR 合并。

**验收**：`CI_IMAGE_BUILD_AUTHORITY = PASS`；`SERVER_BUILD_COUNT = 0`。

---

#### A5. ARCH-P1-06：Compose 环境变量去重

```text
Status: DONE
PR: #421
Merge SHA: 5fb6ea5172f92633c609dd9c5cc1287b9a231e70
```

- [x] api/worker/scheduler 重复环境变量提取为 `x-common-env` anchor；服务级差异保留。
- [x] 展开后环境变量对账；安全开关值不得变化。
- [x] Compose config、CI、staging smoke 通过；PR 合并。

---

#### A6. ARCH-P1-07：竞赛域读路径修正

```text
Status: DONE
PR: #422
Merge SHA: e2f0d5ca895f08e1d4e9ef20ccc8db89a8045e64
```

- [x] `src/w2/competitions/league_whitelist_scope.py` 模块级常量（`TOP_FIVE_COMPETITIONS` 等）
      改为函数调用，消除 import 时查库与热切换失效。
- [x] 核查 audit/backtest 导入链上的其他 import-time 副作用。
- [x] PR 合并。

---

#### A7. ARCH-P1-08：P1 总验收 + 终态重复盘点

```text
Status: DONE
PR: #423
Merge SHA: a607d65b0b71afbc0caa50c44a6e162cf397e4e4
CI: 30339386348
```

- [x] 一套赔率历史 + 一套当前盘口投影 + 一套 canonical identity + Dashboard 单一 read model。
- [x] CI 镜像发布；服务器 pull-only；无生产 fallback。
- [x] **追加三条**：API 层无特征/定价/模拟 import（守卫常绿）；读路径 fail-closed
      （无隐式空数据 fallback）；legacy 决策合同代码为零。
- [x] **终态盘点**：按 P1-01 矩阵方法对全部剩余表、runtime 目录、配置、账本终态盘点，
      每类事实指认唯一权威，矩阵写入本文件；发现双权威 = 不通过。
- [x] **`shadow_strategy_*` 裁决**：零读零写零任务则按证据法独立 PR drop；
      EVAL-01A 要复用则明确登记。
- [x] P1 完整 CI 与 staging 验收；人工验收；PR 合并。

##### A7 Database authority matrix

2026-07-28 在 staging 对 `public` schema 全量读取：62 tables、1 view、0 materialized
views。以下矩阵覆盖全部 63 个观测资产；`0044` 删除 3 个零行 shadow 表后终态为
59 tables、1 view。行数是 migration 前只读实测；ORM/migration 与 reader/writer
均按 exact-head 生产 import graph 和 SQL 引用全量核对。所有外键均已纳入
`information_schema` 入站/出站对账，shadow 三表入站/出站均为 0。

| asset | asset_type | fact_class | row_or_file_count | producer | consumer | scheduled_task | canonical_authority | duplicate_or_fallback | decision | evidence |
|---|---|---|---:|---|---|---|---|---|---|---|
| `alembic_version` | table | migration metadata | 1 | Alembic | Alembic | migration job | yes | no | retain | PostgreSQL catalog + `migrations/` |
| `canonical_teams`; `provider_team_identity_crosswalks`; `player_identity_mappings`; `transfermarkt_player_references`; `player_club_membership_observations` | 5 tables | identity | 16; 32; 110; 50149; 0 | identity materializers/import | lineup, valuation, projection | worker/manual import | first four are scoped canonical/provenance authorities; observations are source facts | no legacy crosswalk fallback | retain | persistence models; migrations `0001`, `0032`, `0042`; A3 guards |
| `competitions`; `seasons`; `league_profile`; `league_season`; `league_readiness_audit`; `teams`; `canonical_team_match_history`; `venues`; `referees` | 9 tables | competition/team history | 0; 0; 14; 14; 20; 0; 102; 0; 0 | registry/audit/history materializers | runtime scope, model inputs | worker/manual audit | DB competition registry + canonical history | JSON competition files are bootstrap metadata, not runtime scope authority | retain | ORM/migrations + A6 single-query guards |
| `fixtures`; `raw_payload`; `provider_request_logs`; `ingestion_runs`; `stages`; `quota_usage` | 6 tables | ingestion/provenance | 0; 370; 312; 0; 0; 13 | ingestion | workers/audit | worker (scheduler disabled) | raw capture/request provenance | no runtime provider fallback | retain | persistence models; provider delta guard |
| `matchday_market_observations`; `current_market_projection`; `historical_market_source_snapshots`; `forward_market_snapshot`; `canonical_historical_ah_facts` | 4 tables + 1 view | odds/history/projection | 44644; 10648; 0; 0; 0 | matchday intake; deterministic SQL view | projection/worker | worker | history=`matchday_market_observations`; current=`current_market_projection` | other three are empty scoped source/model artifacts, not competing writers | retain | `market_projection_view.py`; migration `0041`; no API provider access |
| `matchday_checkpoint_plans`; `matchday_endpoint_capture_plans`; `matchday_endpoint_captures`; `matchday_evidence_manifests`; `matchday_fixture_identities` | 5 tables | matchday capture | 608; 0; 231; 2; 38 | matchday intake | materializers/audit | worker | DB capture chain | no runtime card fallback | retain | matchday persistence models/migrations |
| `future_refresh_checkpoint_audit`; `future_refresh_checkpoint_plan`; `future_refresh_run_audit`; `future_refresh_task_audit` | 4 tables | refresh audit | 1; 0; 60; 55 | future refresh | ops/audit | worker (scheduler disabled) | DB audit trail | no duplicate writable store | retain | future-refresh repository/migrations |
| `lineup_confirmed_events`; `lineup_source_snapshots`; `registered_roster_snapshots`; `structured_lineup_players`; `structured_lineup_snapshots`; `team_lineup_baselines` | 6 tables | lineup/roster | 0; 1; 0; 200; 10; 0 | lineup materialization | projection/model | worker | structured DB lineup + canonical identity | no name/fuzzy/file fallback | retain | lineup models; A3 fail-closed contracts |
| `model_runs`; `predictions`; `team_rating_snapshots`; `team_xg_match`; `team_xg_rolling_snapshot`; `t30_validation_snapshots` | 6 tables | model facts | 0; 0; 16; 104; 28; 0 | offline/model materializers | write-side projection only | manual/worker | DB model inputs/results | API import graph cannot reach calculators | retain | model persistence + API transitive guard |
| `player_valuation_observations`; `team_value_asof_artifacts` | 2 tables | valuation | 31507; 0 | valuation materializer | team-value projection | manual/worker | DB valuation history | no crosswalk/file fallback | retain | valuation models; A3 contracts |
| `read_model_checkpoint` | table | public read model | 8 | write-side projection | API/Dashboard/operations | worker | **sole public read authority** | runtime/provider/recompute fallback count 0 | retain | `api/repository.py`; 20-round read guard |
| `dynamic_prematch_evaluations`; `dynamic_prematch_supersessions`; `gate5_recommendation_lock_event`; `recommendation_locks`; `recommendations` | 5 tables | decision/lock | 0; 0; 0; 0; 0 | write-side decision pipeline | write-side/audit | disabled | canonical v3 contract when populated | no legacy endpoint/schema/bypass | retain empty schema for defined current capabilities | decision-contract static guards |
| `results`; `settlements` | 2 tables | result/settlement | 0; 0 | EVAL-01A not started | none in current production read authority | none | not active yet; runtime forward ledger remains current historical authority | no dual writer | retain for B1 activation only | catalog + runtime writer scan |
| `stage7i_lifecycle_event`; `stage7i_lifecycle_heartbeat`; `stage7i_lifecycle_run` | 3 tables | lifecycle audit | 0; 0; 0 | observer tooling | ops tooling | none | scoped DB lifecycle audit | no public read fallback | retain | stage7i persistence/migrations |
| `shadow_strategy_run`; `shadow_strategy_lock`; `shadow_strategy_evaluation` | 3 tables | retired shadow strategy | 0; 0; 0 | none | none after #423 | none | no | no historical rows; EVAL-01A schema is lossy | **DROP in `0044`** | staging count/FK=0; production read/write/task/API scan=0 |

##### A7 Runtime authority matrix

有效 staging 根 `/opt/w2/shared/runtime` 全量为 132 files / 271748876 bytes。
Compose 仅挂载该根（API/worker）和 `reports/public`（Web）；历史业务数据不删除。

| asset | asset_type | fact_class | row_or_file_count | producer | consumer | scheduled_task | canonical_authority | duplicate_or_fallback | decision | evidence |
|---|---|---|---:|---|---|---|---|---|---|---|
| `backups/` | runtime dir | recovery | 1 / 27782 B | recovery tooling | operator | none | no | not live authority | retain historical recovery | full `find`/size inventory |
| `forward_outcome_ledger/` | runtime dir | forward result/settlement | 25 / 148670580 B | forward outcome ledger | performance/formal tracking | manual/worker | **yes until EVAL-01A** | DB `results`/`settlements` have zero writers/rows | retain; B1 migration input | Compose mount + writer/reader scan |
| `imports/` | runtime dir | historical/raw cache | 43 / 108226927 B | historical imports | offline/recovery | none | source provenance only | not public fallback | retain historical business data | full file inventory (jsonl/ledger/lock) |
| `independent_signal_backfill/` | runtime dir | offline cache | 0 / 0 B | offline tool | offline tool | none | no | no production reader | retain empty mount-compatible root | full file inventory |
| `market_timeline_snapshots/` | runtime dir | market cache | 0 / 0 B | write-side tool | offline/tooling | none | no; DB odds history is authority | production fallback count 0 | retain expected writer root | Compose/path scan |
| `reports/` (including `reports/public`) | runtime dir | public materialized reports | 62 / 14823585 B | report projector | Web/static ops | worker/manual | display artifacts only; DB read model is authority | API does not read files | retain | Web Compose mount + full file inventory |
| `watchdog/` | runtime dir | liveness | 1 / 2 B | watchdog | health tooling | watchdog | no | no business fact | retain | full file inventory |

##### A7 Configuration authority matrix

Tracked structured config contains 43 files after deleting the one unused shadow policy. Entries
with identical readers and authority semantics are grouped, but every file is covered by its exact
directory glob. Deployment authority adds 7 explicitly named surfaces, for 50 inventoried assets.

| asset | asset_type | fact_class | row_or_file_count | producer | consumer | scheduled_task | canonical_authority | duplicate_or_fallback | decision | evidence |
|---|---|---|---:|---|---|---|---|---|---|---|
| `config/approvals/*.json`; `config/capabilities/*.json`; `config/factors/*.json` | config | current decision capability | 1 + 1 + 1 | reviewed source | domain adapter/write side | none | yes for scoped policy | DB stores projected outcome, not duplicate config | retain | exact file list + reader import scan |
| `config/competitions/**/*.json` | config | competition bootstrap/profile | 14 | reviewed source | loaders/offline/predeploy | none | bootstrap metadata only; runtime enabled scope is DB | no runtime hard-coded fallback | retain | all 14 files enumerated by `find`; A6 guards |
| `config/environments/*` | config | environment defaults | 4 | operator | settings | service startup | yes per environment | Compose explicit overrides are deployment inputs | retain | local/production/staging/test YAML |
| `config/evaluations/*`; `config/readiness/*`; `config/team_ratings/*`; `config/team_values/*` | config | offline evaluation/readiness/bootstrap | 2 + 1 + 1 + 1 | reviewed/offline | offline/predeploy | none | scoped offline/bootstrap only | not API authority | retain | exact five-file inventory + readers |
| `config/policies/*` excluding deleted `shadow_strategy.v1.json` | config | operational/model policy | 17 | reviewed source | named loaders/tools | worker/manual | yes per scoped policy; DB facts remain separate | no duplicate dynamic authority | retain | exact 17-file inventory + path/reference scan |
| `.github/workflows/ci.yml`; `Dockerfile.python`; `Dockerfile.web`; `infra/compose/compose.staging.yml`; `scripts/deploy_stage7h_staging.sh`; `scripts/recover_staging_runtime.sh`; `scripts/watch_staging_runtime.sh` | workflow/deploy config | immutable deployment | 7 | repository/CI | GHCR/staging | CI/operator/watchdog | **sole deployment authority chain** | server build/source install/mutable image count 0 | retain | workflow, Compose and shell static contracts |

##### A7 Ledger/contract authority matrix

| asset | asset_type | fact_class | row_or_file_count | producer | consumer | scheduled_task | canonical_authority | duplicate_or_fallback | decision | evidence |
|---|---|---|---:|---|---|---|---|---|---|---|
| `matchday_market_observations` | table | odds history | 44644 | matchday intake | current view/projector | worker | yes (count 1) | no JSON odds fallback | retain | migration `0041` + import graph |
| `current_market_projection` | view | current odds | 10648 | deterministic SQL view | write-side projection | query-time SQL | yes (count 1) | no provider/runtime fallback | retain | view definition |
| canonical identity tables (player/team rows above) | tables | player/team identity | 110 / 16+32 | reviewed identity materializers | lineup/valuation/projection | none/worker | player=1; team=1 | legacy crosswalk/name/fuzzy bypass 0 | retain | A3 guards + production scan |
| `read_model_checkpoint` | table | Dashboard/API projection | 8 | projector | all public reads | worker | yes (count 1) | API compute/runtime fallback 0 | retain | direct/transitive import graph |
| `forward_outcome_ledger/` | runtime ledger | forward result/settlement history | 25 files | forward tracking | performance/formal tracking | manual/worker | yes until B1 | `results`/`settlements` dormant, not writable competitors | retain until EVAL-01A | runtime writer/reader scan |
| `recommendation_locks`; `gate5_recommendation_lock_event` | tables | current decision lock | 0 / 0 | current v3 pipeline when enabled | audit | disabled | current schema | production switches remain disabled | retain | schema/router scan |
| `*_snapshots`, `*_history`, `*_evaluation` DB assets listed in Database matrix | tables | scoped source/model/audit facts | counts above | scoped materializers | write-side/offline | worker/manual | each scoped by fact class | not public/ledger fallback | retain | zero omitted DB assets |
| historical `imports/` ledgers/locks and `backups/` | runtime files | recovery/provenance | 44 files | historical tooling | offline recovery | none | no | production readers 0 | retain, never promote to live authority | runtime full inventory |

```text
DATABASE_ASSET_COUNT = 60
RUNTIME_ASSET_COUNT = 7
CONFIG_ASSET_COUNT = 50
LEDGER_ASSET_COUNT = 8

UNMAPPED_ASSET_COUNT = 0
DUAL_WRITABLE_AUTHORITY_COUNT = 0
PRODUCTION_FALLBACK_COUNT = 0

ODDS_HISTORY_AUTHORITY_COUNT = 1
CURRENT_ODDS_PROJECTION_AUTHORITY_COUNT = 1
CANONICAL_PLAYER_IDENTITY_AUTHORITY_COUNT = 1
CANONICAL_TEAM_IDENTITY_AUTHORITY_COUNT = 1
DASHBOARD_READ_AUTHORITY_COUNT = 1
API_COMPUTE_IMPORT_COUNT = 0
IMPLICIT_EMPTY_DATA_FALLBACK_COUNT = 0
LEGACY_DECISION_RUNTIME_REFERENCE_COUNT = 0
LEGACY_DECISION_SCHEMA_COUNT = 0
LEGACY_DECISION_ENDPOINT_COUNT = 0
DECISION_CONTRACT_BYPASS_COUNT = 0
READ_PATH_FAIL_CLOSED = PASS
CI_IMAGE_BUILD_AUTHORITY = PASS
SERVER_BUILD_COUNT = 0
COMPOSE_BUILD_COUNT = 0
MUTABLE_IMAGE_REFERENCE_COUNT = 0
SERVER_SOURCE_INSTALL_COUNT = 0
SHADOW_STRATEGY_DECISION = DROP
P1_ARCHITECTURE_CONVERGENCE_PASS = PASS
```

**完成标准**：`P1_ARCHITECTURE_CONVERGENCE_PASS`

---

#### A8. 阶段 P2：卫生治理（可与阶段 B 穿插，不得抢占 EVAL-01 序列）

```text
Status: IN_PROGRESS
```

**ARCH-P2-02 Docs 整理**
```text
Status: DONE
PR: #426
Merge SHA: 49c75521325af46551699b27241c0ef4c6bbb7a0
CI: 30422145661
Conclusion: 133 份冻结历史文件归档；活动资产、当前权威和 Runbook 保持在现行路径。
```

- [x] 日期型一次性证据移入 `docs/archive/`；同一审计只留最新权威版；旧文档标 `SUPERSEDED_BY`。
- [x] PR 合并。

**ARCH-P2-03 本地垃圾清理**（只清开发机，不进业务 PR）
```text
Status: DONE
Conclusion: PASS；释放 1853664 KiB（1.77 GiB），活动 worktree、开放 PR 分支及历史数据保持可用。
```

- [x] `.worktrees/`、过期 `.local/`、废弃 `runtime/` stage 目录、无用本地分支；记录释放空间。

**ARCH-P2-04 项目状态记录收敛**
```text
Status: DONE
PR: #427
Merge SHA: bf21ddcc495b0c8d041c956734d278c1d611f24e
CI: 30425831606
Conclusion: 当前机器状态、任务规格/完成回执和人工决定已分离为单一职责权威。
```

- [x] `PROJECT_STATE.yaml` 唯一机器可读状态；`PROJECT_LEDGER.md` 只记人工决定。
- [x] `NEXT_ACTION.md` 改为链接本清单或删除；SHA/CI 不再多文档重复维护。
- [x] 本清单任务回执压缩为 CI run 号 + merge SHA + 一行结论。
- [x] PR 合并。

**ARCH-P2-06 `src/w2` 一级包角色与依赖矩阵**
```text
Status: DONE
PR: #428
Merge SHA: 1a46a9e47a478072d37e4ec4c7a44d914e1a127b
CI: 30432075563
Conclusion: 40 个一级包全量映射；删除 0；22 包 SCC 与 schemas 待调查项如实保留。
```

- [x] 逐包矩阵（package/callers/依赖/循环/镜像包含/role/decision/evidence），全包覆盖不抽样。
- [x] `replay`、`data_assets`、`migration`、`audit_export` 已按实际入口审查，均有保留依据。
- [x] 仅完整满足九项零引用标准才允许 `DELETE`；本轮没有包达到该标准，未删除源码。
- [x] PR 合并。

分析口径：Python 依赖使用 AST 解析 `import`、`from`、相对导入、package child import，
以及参数为常量的 `importlib.import_module` / `__import__`；直接调用方覆盖 `apps/`、
`scripts/`、migrations、tests 和 `pyproject.toml` console entrypoints。运行可达性从
Compose/Docker/workflow 声明的 API、worker、scheduler 入口出发计算传递闭包；另行扫描
Dockerfile、Compose、workflow、Runbook 和历史/恢复入口，避免把离线能力误判为 DEAD。
`direct_callers` 固定按 `apps;scripts;migrations;tests` 记直接 AST 调用文件数；
`reverse_callers` 是其他 `src/w2` 一级包的直接反向依赖。

<!-- SRC_W2_PACKAGE_MATRIX_START -->
```text
TOP_LEVEL_PACKAGE_COUNT = 40
MAPPED_PACKAGE_COUNT = 40
UNMAPPED_PACKAGE_COUNT = 0
DEPENDENCY_EDGE_COUNT = 124
CYCLE_COUNT = 1
RUNTIME_REACHABLE_PACKAGE_COUNT = 27
OFFLINE_ONLY_PACKAGE_COUNT = 13
DEAD_PACKAGE_COUNT = 0
DELETED_PACKAGE_COUNT = 0
```

| package | python_file_count | direct_callers | reverse_callers | internal_dependencies | cycle_membership | entrypoints | scheduler_or_worker_reachability | api_or_web_reachability | docker_image_inclusion | role | decision | evidence |
|---|---:|---|---|---|---|---|---|---|---|---|---|---|
| `analysis` | 2 | apps:0;scripts:0;migrations:0;tests:2 | prematch | ingestion | SCC-1 | - | YES | YES | PYTHON_IMAGE | RUNTIME_LIBRARY | KEEP | RUNTIME_REACHABLE;AST_DEPENDENCY_GRAPH |
| `api` | 6 | apps:2;scripts:2;migrations:0;tests:11 | - | competitions,dashboard,domain,infrastructure,matchday,models,monitoring,operations,prematch,providers | - | - | YES | YES | PYTHON_IMAGE | PUBLIC_READ | KEEP | RUNTIME_REACHABLE;AST_DEPENDENCY_GRAPH |
| `audit_export` | 2 | apps:0;scripts:2;migrations:0;tests:1 | - | domain,infrastructure,reporting,tracking | - | - | NO | NO | PYTHON_IMAGE | AUDIT_EXPORT | KEEP_AUDIT | SCRIPT_ENTRY;AUDIT_EXPORT_DEPENDENCIES |
| `backtest` | 10 | apps:0;scripts:7;migrations:0;tests:10 | - | competitions,domain,ingestion,markets,models,providers | - | - | NO | NO | PYTHON_IMAGE | OFFLINE_TOOL | KEEP_OFFLINE | 7_SCRIPT_ENTRIES;HISTORICAL_RAW_CONSUMER |
| `competitions` | 8 | apps:1;scripts:11;migrations:1;tests:21 | api,backtest,features,ingestion,matchday,monitoring,operations,prematch,strategy | infrastructure,providers | SCC-1 | - | YES | YES | PYTHON_IMAGE | RUNTIME_LIBRARY | KEEP | RUNTIME_REACHABLE;AST_DEPENDENCY_GRAPH |
| `dashboard` | 16 | apps:1;scripts:2;migrations:0;tests:16 | api,matchday,prematch | domain,prematch,settlement,strategy | SCC-1 | - | YES | YES | PYTHON_IMAGE | PUBLIC_READ | KEEP | RUNTIME_REACHABLE;AST_DEPENDENCY_GRAPH |
| `data_assets` | 2 | apps:0;scripts:1;migrations:0;tests:1 | - | - | - | - | NO | NO | PYTHON_IMAGE | OFFLINE_TOOL | KEEP_OFFLINE | SCRIPT_ENTRY;ASSET_REGISTRY |
| `domain` | 14 | apps:0;scripts:2;migrations:0;tests:21 | api,audit_export,backtest,dashboard,features,historical,ingestion,markets,matchday,migration,models,normalization,operations,prematch,pricing,readiness,recovery,replay,reporting,schemas,settlement,strategy,tracking | readiness | SCC-1 | - | YES | YES | PYTHON_IMAGE | RUNTIME_LIBRARY | KEEP | RUNTIME_REACHABLE;AST_DEPENDENCY_GRAPH |
| `factor_model` | 2 | apps:0;scripts:1;migrations:0;tests:1 | - | features,identity,infrastructure,ingestion,matchday,providers,ratings | - | - | NO | NO | PYTHON_IMAGE | OFFLINE_TOOL | KEEP_OFFLINE | SCRIPT_ENTRY;OFFLINE_REMEDIATION |
| `features` | 8 | apps:0;scripts:0;migrations:0;tests:7 | factor_model,ingestion,prematch,ratings,strategy | competitions,domain,markets | SCC-1 | - | YES | YES | PYTHON_IMAGE | RUNTIME_LIBRARY | KEEP | RUNTIME_REACHABLE;AST_DEPENDENCY_GRAPH |
| `formal` | 2 | apps:0;scripts:1;migrations:0;tests:2 | strategy | - | - | - | YES | YES | PYTHON_IMAGE | RUNTIME_LIBRARY | KEEP | RUNTIME_REACHABLE;AST_DEPENDENCY_GRAPH |
| `gates` | 2 | apps:0;scripts:0;migrations:0;tests:0 | - | strategy | - | w2-gate5-preflight | NO | NO | PYTHON_IMAGE | OFFLINE_TOOL | KEEP_OFFLINE | CONSOLE_ENTRYPOINT |
| `historical` | 12 | apps:0;scripts:9;migrations:0;tests:4 | lineups | domain,identity,infrastructure | SCC-1 | - | YES | YES | PYTHON_IMAGE | RUNTIME_LIBRARY | KEEP | RUNTIME_REACHABLE;AST_DEPENDENCY_GRAPH |
| `identity` | 2 | apps:0;scripts:1;migrations:0;tests:2 | factor_model,historical,ingestion,lineups | infrastructure | - | - | YES | YES | PYTHON_IMAGE | RUNTIME_LIBRARY | KEEP | RUNTIME_REACHABLE;AST_DEPENDENCY_GRAPH |
| `infrastructure` | 18 | apps:0;scripts:13;migrations:17;tests:31 | api,audit_export,competitions,factor_model,historical,identity,ingestion,matchday,monitoring,operations,prematch,providers,settlement,strategy,tracking | - | - | - | YES | YES | PYTHON_IMAGE | RUNTIME_LIBRARY | KEEP | RUNTIME_REACHABLE;AST_DEPENDENCY_GRAPH |
| `ingestion` | 16 | apps:2;scripts:13;migrations:0;tests:16 | analysis,backtest,factor_model,prematch,providers,tracking | competitions,domain,features,identity,infrastructure,lineups,markets,matchday,normalization,prematch,providers | SCC-1 | - | YES | YES | PYTHON_IMAGE | WRITE_SIDE_PROJECTION | KEEP | RUNTIME_REACHABLE;AST_DEPENDENCY_GRAPH |
| `lineups` | 5 | apps:0;scripts:6;migrations:0;tests:5 | ingestion,prematch | historical,identity | SCC-1 | - | YES | YES | PYTHON_IMAGE | RUNTIME_LIBRARY | KEEP | RUNTIME_REACHABLE;AST_DEPENDENCY_GRAPH |
| `markets` | 17 | apps:0;scripts:3;migrations:0;tests:15 | backtest,features,ingestion,prematch,readiness,strategy,tracking | domain,strategy | SCC-1 | - | YES | YES | PYTHON_IMAGE | RUNTIME_LIBRARY | KEEP | RUNTIME_REACHABLE;AST_DEPENDENCY_GRAPH |
| `matchday` | 11 | apps:1;scripts:3;migrations:2;tests:9 | api,factor_model,ingestion,prematch,refresh | competitions,dashboard,domain,infrastructure,providers,readiness,refresh,strategy | SCC-1 | w2-matchday | YES | YES | PYTHON_IMAGE | RUNTIME_ENTRYPOINT | KEEP | RUNTIME_REACHABLE;AST_DEPENDENCY_GRAPH |
| `migration` | 3 | apps:0;scripts:2;migrations:0;tests:1 | - | domain | - | - | NO | NO | PYTHON_IMAGE | MIGRATION_ONLY | KEEP_MIGRATION | 2_SCRIPT_ENTRIES;MIGRATION_RECOVERY |
| `models` | 12 | apps:0;scripts:2;migrations:0;tests:8 | api,backtest,operations,recovery,strategy | domain | SCC-1 | - | YES | YES | PYTHON_IMAGE | RUNTIME_LIBRARY | KEEP | RUNTIME_REACHABLE;AST_DEPENDENCY_GRAPH |
| `monitoring` | 5 | apps:1;scripts:3;migrations:0;tests:4 | api | competitions,infrastructure,providers | - | - | YES | YES | PYTHON_IMAGE | RUNTIME_LIBRARY | KEEP | RUNTIME_REACHABLE;AST_DEPENDENCY_GRAPH |
| `normalization` | 2 | apps:0;scripts:2;migrations:0;tests:1 | ingestion | domain | SCC-1 | - | YES | YES | PYTHON_IMAGE | RUNTIME_LIBRARY | KEEP | RUNTIME_REACHABLE;AST_DEPENDENCY_GRAPH |
| `observability` | 2 | apps:0;scripts:0;migrations:0;tests:0 | - | - | - | w2-stage7i-observer | NO | NO | PYTHON_IMAGE | OFFLINE_TOOL | KEEP_OFFLINE | CONSOLE_ENTRYPOINT |
| `operations` | 11 | apps:1;scripts:7;migrations:0;tests:9 | api,prematch,providers,security | competitions,domain,infrastructure,models | SCC-1 | - | YES | YES | PYTHON_IMAGE | RUNTIME_LIBRARY | KEEP | RUNTIME_REACHABLE;AST_DEPENDENCY_GRAPH |
| `prematch` | 7 | apps:1;scripts:6;migrations:0;tests:29 | api,dashboard,ingestion,tracking | analysis,competitions,dashboard,domain,features,infrastructure,ingestion,lineups,markets,matchday,operations,pricing,providers,ratings,strategy,tracking | SCC-1 | - | YES | YES | PYTHON_IMAGE | WRITE_SIDE_PROJECTION | KEEP | RUNTIME_REACHABLE;AST_DEPENDENCY_GRAPH |
| `pricing` | 6 | apps:0;scripts:0;migrations:0;tests:3 | prematch | domain,strategy | SCC-1 | - | YES | YES | PYTHON_IMAGE | RUNTIME_LIBRARY | KEEP | RUNTIME_REACHABLE;AST_DEPENDENCY_GRAPH |
| `providers` | 5 | apps:2;scripts:7;migrations:0;tests:11 | api,backtest,competitions,factor_model,ingestion,matchday,monitoring,prematch,tracking | infrastructure,ingestion,operations | SCC-1 | - | YES | YES | PYTHON_IMAGE | RUNTIME_LIBRARY | KEEP | RUNTIME_REACHABLE;AST_DEPENDENCY_GRAPH |
| `ratings` | 2 | apps:0;scripts:0;migrations:0;tests:0 | factor_model,prematch | features | SCC-1 | - | YES | YES | PYTHON_IMAGE | RUNTIME_LIBRARY | KEEP | RUNTIME_REACHABLE;AST_DEPENDENCY_GRAPH |
| `readiness` | 2 | apps:0;scripts:0;migrations:0;tests:1 | domain,matchday | domain,markets | SCC-1 | - | YES | YES | PYTHON_IMAGE | RUNTIME_LIBRARY | KEEP | RUNTIME_REACHABLE;AST_DEPENDENCY_GRAPH |
| `recovery` | 2 | apps:0;scripts:1;migrations:0;tests:1 | - | domain,models | - | - | NO | NO | PYTHON_IMAGE | OFFLINE_TOOL | KEEP_OFFLINE | SCRIPT_ENTRY;BACKUP_RESTORE |
| `refresh` | 2 | apps:0;scripts:1;migrations:0;tests:5 | matchday | matchday | SCC-1 | - | YES | YES | PYTHON_IMAGE | WRITE_SIDE_PROJECTION | KEEP | RUNTIME_REACHABLE;AST_DEPENDENCY_GRAPH |
| `replay` | 2 | apps:0;scripts:2;migrations:0;tests:2 | - | domain | - | - | NO | NO | PYTHON_IMAGE | OFFLINE_TOOL | KEEP_OFFLINE | 2_SCRIPT_ENTRIES;HISTORICAL_REPLAY |
| `reporting` | 4 | apps:0;scripts:4;migrations:0;tests:4 | audit_export | domain | - | - | NO | NO | PYTHON_IMAGE | OFFLINE_TOOL | KEEP_OFFLINE | 4_SCRIPT_ENTRIES;REPORT_READER |
| `schemas` | 2 | apps:0;scripts:0;migrations:0;tests:1 | - | domain | - | - | NO | NO | PYTHON_IMAGE | OFFLINE_TOOL | KEEP_OFFLINE | INVESTIGATION_REQUIRED;TEST_ONLY_CALLER;HISTORICAL_DEPENDENCY_UNPROVEN |
| `security` | 2 | apps:0;scripts:1;migrations:0;tests:1 | - | operations | - | - | NO | NO | PYTHON_IMAGE | OFFLINE_TOOL | KEEP_OFFLINE | SCRIPT_ENTRY;BACKUP_SECURITY_BASELINE |
| `settlement` | 3 | apps:0;scripts:2;migrations:0;tests:2 | dashboard,tracking | domain,infrastructure | SCC-1 | - | YES | YES | PYTHON_IMAGE | WRITE_SIDE_PROJECTION | KEEP | RUNTIME_REACHABLE;AST_DEPENDENCY_GRAPH |
| `shadow` | 2 | apps:0;scripts:0;migrations:0;tests:0 | - | strategy | - | w2-shadow-comparison-import | NO | NO | PYTHON_IMAGE | OFFLINE_TOOL | KEEP_OFFLINE | CONSOLE_ENTRYPOINT;COMPARISON_IMPORT |
| `strategy` | 13 | apps:0;scripts:3;migrations:0;tests:15 | dashboard,gates,markets,matchday,prematch,pricing,shadow | competitions,domain,features,formal,infrastructure,markets,models | SCC-1 | - | YES | YES | PYTHON_IMAGE | RUNTIME_LIBRARY | KEEP | RUNTIME_REACHABLE;AST_DEPENDENCY_GRAPH |
| `tracking` | 7 | apps:1;scripts:5;migrations:0;tests:11 | audit_export,prematch | domain,infrastructure,ingestion,markets,prematch,providers,settlement | SCC-1 | - | YES | YES | PYTHON_IMAGE | WRITE_SIDE_PROJECTION | KEEP | RUNTIME_REACHABLE;AST_DEPENDENCY_GRAPH |

```text
ROLE_COUNTS = RUNTIME_ENTRYPOINT:1;RUNTIME_LIBRARY:19;WRITE_SIDE_PROJECTION:5;PUBLIC_READ:2;OFFLINE_TOOL:11;MIGRATION_ONLY:1;AUDIT_EXPORT:1;DEAD:0
DECISION_COUNTS = KEEP:27;KEEP_OFFLINE:11;KEEP_MIGRATION:1;KEEP_AUDIT:1;DELETE:0
CYCLE_1_MEMBERS = analysis,competitions,dashboard,domain,features,historical,ingestion,lineups,markets,matchday,models,normalization,operations,prematch,pricing,providers,ratings,readiness,refresh,settlement,strategy,tracking
DEAD_PACKAGES = NONE
DELETED_PACKAGES = NONE
INVESTIGATION_REQUIRED_PACKAGES = schemas
```
<!-- SRC_W2_PACKAGE_MATRIX_END -->

**ARCH-P2-05 最终架构收敛验收**
```text
Status: IMPLEMENTED_PENDING_ACCEPTANCE
Branch: codex/arch-p2-05-final-architecture-acceptance
PR: #429
Base Main: 1a46a9e47a478072d37e4ec4c7a44d914e1a127b
Base Main CI: 30432075563
```

- [x] P0 与 P1 的历史台账、A1–A7 实施 PR 和 merge SHA 已逐项对 Git/GitHub 核对；
      原台账 #380、#382、#388 的三个错误短 SHA 已改为真实前缀。
- [x] P2-02、P2-03、P2-04、P2-06 的完成坐标/本地结论完整；P2-05 不提前标 DONE。
- [x] `PROJECT_STATE.yaml` 仍是唯一当前机器状态；本清单仍是唯一任务顺序、规格和已合并回执权威。
- [x] 唯一事实权威计数均为 1；API 计算 import、隐式空数据 fallback、legacy runtime 引用均为 0；
      现有 fail-closed 与生产零引用合同继续执行。
- [x] 正式部署保持 CI build/push/smoke → immutable digest → server pull-only；
      `SERVER_BUILD_COUNT = 0`、`SERVER_SOURCE_INSTALL_COUNT = 0`、Compose `build:` = 0。
- [x] P1 删除账本与断言式 drop 证据仍在；scripts 矩阵的 8 个 `DELETE` 路径均已不存在且保留 D1/D2；
      `0044` shadow 三表 drop 仍先断言表存在、零行与零依赖。
- [x] 已知保留项如实登记：当前 1 个 22 包 SCC 未重构；`schemas` 保持
      `KEEP_OFFLINE / INVESTIGATION_REQUIRED`，未虚假宣称问题消失。
- [x] 本 PR 仅修改清单、机器状态和合同测试；`STAGING_NOT_REQUIRED = PASS`，
      Provider calls = 0，Business DB writes = 0。
- [ ] exact-head FULL CI、外部验收与 PR 合并。

```text
P0_ARCHITECTURE_CONVERGENCE_PASS = PASS
P1_ARCHITECTURE_CONVERGENCE_PASS = PASS
P2_ARCHITECTURE_FINAL_ACCEPTANCE = IMPLEMENTED_PENDING_ACCEPTANCE
CURRENT_AUTHORITY_CONFLICT_COUNT = 0
PRODUCTION_FALLBACK_REFERENCE_COUNT = 0
SERVER_BUILD_COUNT = 0
SERVER_SOURCE_INSTALL_COUNT = 0
COMPOSE_BUILD_COUNT = 0
SCRIPT_DELETE_EVIDENCE_COUNT = 8
PACKAGE_CYCLE_COUNT = 1
CYCLIC_PACKAGE_COUNT = 22
SCHEMAS_DECISION = KEEP_OFFLINE
SCHEMAS_EVIDENCE = INVESTIGATION_REQUIRED
STAGING_NOT_REQUIRED = PASS
```

**最终状态（P2-05 合并后才允许）**：`W2_ARCHITECTURE_CONVERGENCE_COMPLETE`

---

### 阶段 B：EVAL 能力建设（ARCH-P1-08 通过后启动）

> 总目标：闭合"赛果→表现→反馈"回边，每场比赛（而非每次推荐）都产生可信度量；
> 首发因子两面处理：有首发的联赛验增量，无首发的联赛防逆向选择。

```text
Status: NOT_STARTED
```

---

#### B1. EVAL-01A：赛果与结算账本数据库化

```text
Status: BLOCKED
Blockers: EXACT_HEAD_IMAGE_TRANSFER_BLOCKED; BASE_DIVERGENCE_MERGE_CONFLICT
```

PR #424 必须先对齐届时最新 main、解决状态文件冲突、重跑 exact-head CI 与外部 Review，
再执行 exact-head staging；本任务不在 ARCH-P2-04 中处理。

**目标**：赛果获得 DB 唯一权威；runtime 文件账本（最后一块文件飞地）迁入 DB 并删除。

- [ ] **赛果权威 = 现有 `results` 表**（不新建）。新增 worker 任务：FINISHED 后从**已采集**的
      provider fixture 数据（`raw_payload` / matchday 采集链的 FT 状态与比分）提取
      `MatchResult` 写入 `results`。**不新增任何 provider 调用**；缺比分场次记
      `RESULT_SOURCE_MISSING`，不补采。
- [ ] **runtime 账本迁移**：`runtime/forward_outcome_ledger/*` 与
      `src/w2/tracking/formal_results.py` 的文件读写（11、26 处）迁入 DB；
      建表与否按第三节授权基准 (a) 执行，判定证据写入本文件。
      迁移行数+hash 对账后**同一 PR** 删除文件读写路径，`runtime/` 不再有账本目录。
- [ ] `src/w2/settlement/settle.py` 消费 DB `results`；`forward_ledger_performance`
      记录来源改为 DB 查询（调用方 `analysis_calculator.py` 语义不动）。

**不做**：不改 CLV/命中率计算逻辑；不动 canonical 样本定义；不做 Dashboard。
**验收**：`RESULTS_DB_AUTHORITY_COUNT = 1`；`RUNTIME_LEDGER_FILE_IO = 0`（静态守卫，
模式同 `test_production_report_reads.py`）；迁移对账一致；老板可见的历史表现数字不漂移。
**资产账本**：新增 ≤1 表（按基准判定）；删除 runtime 账本目录 + 文件 IO 代码。
- [ ] PR 合并。

---

#### B2. EVAL-01B：全量校准评分投影

```text
Status: NOT_STARTED
```

**目标**：每场 FINISHED 比赛自动产生"模型 vs 市场"评分——不管推没推荐。

- [ ] 触发：EVAL-01A 赛果写入事件（复用 04A 事件→投影模式，不建新管线框架）。
- [ ] 输入：该 fixture 开赛前**最后一次** `dynamic_prematch_evaluations` 评估
      （`model_probabilities` + `market_probabilities`）+ `results` + picks 的 CLV
      （复用 `forward_ledger_performance.py` 的 `CLV_METHOD` 与 `_log_loss`，禁止重写公式）。
- [ ] 输出（全部落 `read_model_checkpoint`，不建新表）：
      `performance:fixture:{id}`（双方 log loss/Brier/RPS、CLV、联赛、STRICT/ADVISORY 分层标签）；
      `performance:cohort:{scope}`（按联赛/分层/7-30-90 天窗口滚动聚合，含样本计数）。
- [ ] 幂等：同一 fixture 重算 hash 一致；投影带 projection_version/source_event。

**不做**：不做 UI；不做任何"评分→参数"自动反馈（那是 EVAL-02B 门禁的事）。
**验收**：staging 全部已完结且有评估记录的比赛 100% 产生 `performance:fixture:*`；
抽 5 场人工复算一致；API 守卫不变绿（评分在写侧）。
**资产账本**：新增 0；删除 0。
- [ ] PR 合并。

---

#### B3. EVAL-01C：Dashboard 表现视图（CLV 第一 KPI）

```text
Status: NOT_STARTED
```

- [ ] API/Web 只读表现页，仅读 `performance:*` 投影：
      ① CLV 第一位（canonical picks 分布、均值与置信区间、正 CLV 占比）；
      ② 全量校准（model vs market 滚动 log loss 差、校准曲线）；
      ③ STRICT vs ADVISORY 分层表（命中率、CLV、样本数并列）；
      ④ 样本进度条（对照预注册目标；未达标时命中率旁强制"样本不足"标注）。
- [ ] 前端不做任何概率/指标重算（04B 守卫覆盖 `apps/web/src`，保持绿）。

**验收**：页面数字与投影逐项一致；20 轮只读零写；15/30 场视觉验收。
**资产账本**：新增 0；删除 0。
- [ ] PR 合并。

---

#### B4. EVAL-02A：首发盲区防护（防守面，先于增量验证）

```text
Status: NOT_STARTED
```

**目标**：ADVISORY 联赛（无赛前首发）的 pick 不再裸奔；盲区里"模型大幅打赢市场"按逆向选择风险处理。

- [ ] **分歧成因分类器**（写侧 `analysis_calculator`）：用 `matchday_market_observations`
      timeline 计算 `divergence_age_ratio` 与 `movement_ev_share`，按第三节授权基准 (b)
      固化阈值输出三态标签。
- [ ] **降级规则**：ADVISORY + `MOVEMENT_CREATED_DIVERGENCE` → 强制 `WATCH`，
      reason `MARKET_MOVED_AGAINST_BLIND_SPOT`。
- [ ] **风险披露**：decision contract reason 结构新增 `LINEUP_UNOBSERVABLE`
      （ADVISORY 联赛所有卡携带）；按永久红线 10 同步校验器与守卫；
      新增字段不是语义变更，pick/non-pick 互斥不动。
- [ ] **轮换先验**：用赛后阵容记录为 ADVISORY 联赛建基线与球队轮换率
      （复用 `build_team_baseline`）；高轮换球队盲区比赛追加 `HIGH_ROTATION_PRIOR`。
- [ ] **赛后归因**：`performance:fixture:*` 追加赛后首发相对基线偏离度，
      "输给轮换"与"输给运气"分开统计。
- [ ] **δ 溢价**：本任务 δ=0 只标注；标定与生效按第三节授权基准 (b) 自动执行，
      结果写入本文件即生效。

**不做**：不动 STRICT 联赛逻辑；不改 EV 公式；不解冻任何数值调整。
**验收**：ADVISORY 卡 100% 携带 `LINEUP_UNOBSERVABLE`；重放一场"移动产生分歧"样例
验证降级 WATCH；合同守卫全绿；分层统计出现盲区归因字段。
**资产账本**：新增 0；删除 0。
- [ ] PR 合并。

---

#### B5. EVAL-02B：首发增量门禁验证（进攻面，样本驱动）

```text
Status: NOT_STARTED
前置：A2（F10 已删）、A3（球员身份可联接）、B2（评分基建）、
      每联赛 LINEUP_CONFIRMED 配对评估历史 ≥120 场
```

- [ ] **Tier-1 特征集（仅这四个，禁止顺手加特征）**：缺阵球员上季+本季出场分钟占比；
      按位置组（GK/DEF/MID/FWD）缺阵价值占比；XI 连续性计数（最近 5 场首发过的人数）；
      阵型变化标志。全部从 `structured_lineup_players`、`team_lineup_baselines`、
      Transfermarkt 估值链计算。
- [ ] **配对样本**：同一 fixture 的 `LINEUP_CONFIRMED` 前后两次持久化评估（04A 天然产生）。
- [ ] **门禁**：现有 `lineups/evaluation.py::evaluate_market_adjustment`（禁止重写框架），
      按联赛×市场跑，参数按第三节授权基准 (b)。
- [ ] **解冻**：仅通过门禁的联赛×市场，把 `analysis_calculator.py` / `prematch/repository.py`
      中 `lineup_ah_adjustment / lineup_totals_adjustment` 的硬编码 0 替换为计算值；
      报告写入本文件即生效；滚动复验含 0 自动回冻。
- [ ] 预注册文档先于实验提交。

**资产账本**：新增 0；删除 0。
- [ ] PR 合并（可多个 PR：预注册 → 门禁报告 → 解冻，各自独立回滚）。

---

#### B6. OPS-01：联赛扩容 Runbook（A3 后随时可执行，与 B 序列并行）

```text
Status: DONE
Branch: codex/ops-01-league-expansion-runbook
Owner: Codex
PR: #425
Merge SHA: 6aba4ca6e1232d490b0b3c5d5fa40fc09749b3f8
FULL CI: 30412412188
Main CI: 30414946283
```

- [x] 固定流程 runbook 存 `docs/runbooks/`：seed 导入 profile/season → crosswalk 身份
      建立与 review → `league_readiness_audit` 核验 → `--set-enabled true` →
      观察 7 天数据完整性 → 归入 ADVISORY 或 STRICT 分层。
- [x] 配额约束：启用前用 `quota_usage` 现值测算新增请求量，超预算联赛排队。
- [x] 每联赛执行记录追加到本文件。

**OPS-01 执行记录**：本 PR 只建立标准流程，未实际启用联赛；暂无执行记录。

```text
GENERIC_LEAGUE_READINESS_PRODUCER = MISSING
REAL_LEAGUE_ENABLEMENT_READY = false
```

当前没有可生成完整 reviewed DB readiness audit 的通用 producer，任何真实新联赛在
Phase 4 都必须 fail-closed。补齐该能力需要后续单独授权；operator 不得用 direct SQL
伪造 audit。

---

#### B7. EVAL-03：OU 正式链路泛化（Market Candidate Contract）

```text
Status: NOT_STARTED
```

- [ ] `strategy/formal_recommendation.py` 从只读 `canonical_ah_market` 泛化为市场无关
      candidate 接口，AH/OU 同构（报价身份、新鲜度、概率、EV、不确定性、结算契约同一套）。
- [ ] Formal 总开关保持关闭——只消除结构不对称，不开放任何推荐（永久红线 5）。
- [ ] AH/OU 走同一 candidate 校验路径的单元与合同测试；开关值不变的静态断言；
      影子模式下 OU candidate 可走到被开关拦截前的最后一步。
- [ ] PR 合并。

---

### 模型升级（EVAL-03 之后，另行立项，不在本清单）

Dixon-Coles、市场混合权重校准等，必须过 EVAL-01 门禁（时间切分+预注册+全量校准对比）。

---

## 五、闭环论证（全部完成后的链路）

```text
采集(scheduler→worker→DB)
→ 事件(ODDS_CHANGED / LINEUP_CONFIRMED)          [04A，已闭合]
→ 评估+持久化(analysis_calculator→evaluations)    [04A，已闭合]
→ 投影(read_model_checkpoint)                     [04A/04B，已闭合]
→ 展示(API/Web 只读, fail-closed)                 [04B，已闭合]
→ 赛果(results 表 DB 权威)                        [EVAL-01A 闭合]
→ 评分(performance:* 全量 log loss/Brier/CLV)     [EVAL-01B 闭合]
→ 展示回望(CLV KPI/分层/进度)                     [EVAL-01C 闭合]
→ 反馈(门禁裁决→参数解冻/溢价标定/联赛准入)       [EVAL-02A/02B/OPS-01 闭合]
→ (改进后的评估进入下一轮采集评估)                 [环路回到顶部]
```

## 六、资产账本总表

| 方向 | 内容 |
|---|---|
| 新增表 | 目标 0；唯一例外 EVAL-01A `outcome_ledger`（三条判定基准全满足才建） |
| 新增文件权威 | 0（永久红线 2） |
| 删除 | legacy shim/adapter（A2）、F10 死代码（A2）、≥3 张 crosswalk（A3）、runtime 账本目录（B1）、`shadow_strategy_*` 僵尸表（A7 裁决后） |
| 防回流 | 每任务静态守卫测试；A7 终态盘点矩阵；GOVERNANCE-01 双门禁；PR 8 问模板 |

## 七、任务状态与 PR 强制说明格式

`PROJECT_STATE.yaml` 保存当前机器状态流转：

```text
开工:   Status: IN_PROGRESS / Branch / PR / Base SHA / Started at / Owner
阻塞:   Status: BLOCKED / Blocker / Evidence / Next required decision
待验收: Status: IMPLEMENTED_PENDING_ACCEPTANCE / Implementation SHA / CI run / Staging SHA / Evidence / Rollback
```

本文件维护任务顺序、规格和已合并完成回执；只在任务合并后追加：

```text
完成: Status: DONE / Merged PR / Merge SHA / CI run / 一行结论
```

每个 PR 描述必须回答：

```text
1. 本 PR 删除了哪个事实来源、fallback 或重复路径？
2. 是否新增数据库表？（除 EVAL-01A 授权基准情形外，是=违反红线，停止）
3. 是否新增配置文件？若是，说明为什么不是新运行权威。
4. 唯一业务范围是什么？
5. 如何回滚？
6. old/new 如何对账？
7. Provider/Formal/Lock/Production 开关是否不变？
8. 完整 CI 与 staging 证据在哪里？
```

立即停止条件：一个 PR 跨两个任务；新增竞争权威；删除仍有读写的数据；未断言就 drop；
放宽安全开关；清单外修改模型数学；CI 未过；staging 对账失败；历史数据 hash/count 异常。
停止后在 `PROJECT_STATE.yaml` 记 `BLOCKED`，不得自行绕过。

## 八、待议区（记录不实施）

- A2 死代码复核中"证据不足"的疑似项（记录后由后续 P2-06 矩阵裁决）。

---

## 九、机器合同附录：Scripts 权威矩阵

> 本附录是 ARCH-HYGIENE-02 已验收的机器可读合同，不是当前状态副本。
> 当前机器状态只由 `PROJECT_STATE.yaml` 维护；任务顺序、规格和已合并完成回执只由本文件维护。

<!-- SCRIPT_AUTHORITY_MATRIX_START -->
| path | 唯一分类 | 直接调用方 | 传递调用链 | 运行环境 | 部署引用 | 运维文档 | 决定 | 证据 |
|---|---|---|---|---|---|---|---|---|
| `apps/api/main.py` | `RUNTIME_ENTRYPOINT` | Dockerfile.python / Compose Uvicorn | config → process | runtime | 是 | 无 | `KEEP` | E3/E5/E6 |
| `apps/scheduler/main.py` | `RUNTIME_ENTRYPOINT` | Dockerfile.python / Compose `python -m` | config → process | runtime | 是 | 无 | `KEEP` | E3/E5/E6 |
| `apps/web/scripts/write-meta.mjs` | `DEPLOYMENT` | package.json predev/prebuild | npm → script | build | 是 | 无 | `KEEP` | E3 |
| `apps/worker/celery_app.py` | `RUNTIME_ENTRYPOINT` | Dockerfile.python / Compose Celery | config → process | runtime | 是 | 无 | `KEEP` | E3/E5/E6 |
| `migrations/env.py` | `MIGRATION_ONLY` | alembic.ini / Alembic CLI | Alembic → env | migration | 否 | 无 | `KEEP` | E5/E6 |
| `scripts/audit_football_data_co_uk.py` | `MANUAL_OPS` | 人工 CLI | operator → script | offline | 否 | 无 | `KEEP` | E1/E4 |
| `scripts/audit_formal_ah_historical_sources.py` | `MANUAL_OPS` | 人工 CLI | operator → script | offline | 否 | 无 | `KEEP` | E1/E4 |
| `scripts/audit_market_mainline_ladder.py` | `MANUAL_OPS` | 人工 CLI | operator → script | offline | 否 | 无 | `KEEP` | E1/E4 |
| `scripts/audit_pr370_totals_quarter_ev.py` | `ONE_TIME_RECOVERY` | 人工审核后重算 | operator → script | offline | 否 | 无 | `KEEP` | E7 |
| `scripts/audit_transfermarkt_asset.py` | `MANUAL_OPS` | 人工 CLI | operator → script | offline | 否 | 无 | `KEEP` | E1/E4 |
| `scripts/audit_w2_runtime_authorities.py` | `MANUAL_OPS` | 人工审计生成；unit test 验证 | operator → script | offline | 否 | 无 | `KEEP` | E4/E5 |
| `scripts/build_canonical_historical_ah_facts.py` | `ONE_TIME_RECOVERY` | 人工历史重建 | operator → script | offline | 否 | 无 | `KEEP` | E7 |
| `scripts/build_fah_approval_package.py` | `MANUAL_OPS` | 人工 CLI | operator → script | offline | 否 | 无 | `KEEP` | E1/E4 |
| `scripts/build_stage5_demo_datasets.py` | `ONE_TIME_RECOVERY` | 人工历史数据重建 | operator → script | offline | 否 | 无 | `KEEP` | E7 |
| `scripts/build_stage7i_final_evidence.py` | `MANUAL_OPS` | 人工 CLI | operator → script | offline | 否 | 无 | `KEEP` | E1/E4 |
| `scripts/build_stage7i_successor_candidates.py` | `MANUAL_OPS` | 人工 CLI；unit test 验证 | operator → script | offline | 否 | 无 | `KEEP` | E4/E5 |
| `scripts/capture_runtime_release_evidence.py` | `DEPLOYMENT` | 发布证据人工 CLI | operator → script | staging | 否 | 无 | `KEEP` | E3 |
| `scripts/capture_stage7i_fixture_lifecycle.py` | `MANUAL_OPS` | 人工 CLI | operator → script | offline | 否 | 无 | `KEEP` | E1/E4 |
| `scripts/check_boss_console_baseline.py` | `CI_DIRECT` | ci.yml | GitHub CI → script | CI | 是 | 无 | `KEEP` | E2/E3 |
| `scripts/check_compose_staging_ports.py` | `DEPLOYMENT` | deploy_stage7h / predeploy smoke | operator/CI → script | staging/CI | 是 | STAGE7H_VPS_STAGING | `KEEP` | E3/E4/E5 |
| `scripts/check_dashboard_v2_baseline.py` | `DEAD` | 无 | 无 | none | 否 | 无 | `DELETE` | D1/D2 |
| `scripts/check_public_ingress.py` | `CI_TRANSITIVE` | test_public_ingress_cli.py | CI → Pytest → script | CI | 否 | 无 | `KEEP` | E2/E5 |
| `scripts/check_team_values_mapping.py` | `MANUAL_OPS` | W2_TEAM_VALUES_MAPPING | operator → script | offline | 否 | W2_TEAM_VALUES_MAPPING | `KEEP` | E4/E5 |
| `scripts/check_tracked_outputs.py` | `CI_DIRECT` | ci.yml | GitHub CI → script | CI | 是 | W2_ACCEPTANCE_RUNBOOK | `KEEP` | E2/E3/E4/E5 |
| `scripts/check_w2_acceptance.py` | `MANUAL_OPS` | W2_ACCEPTANCE_RUNBOOK | operator → script | local | 否 | W2_ACCEPTANCE_RUNBOOK | `KEEP` | E4/E5 |
| `scripts/check_w2_all.py` | `CI_DIRECT` | ci.yml | GitHub CI → script | CI | 是 | W2_ACCEPTANCE_RUNBOOK | `KEEP` | E2/E3/E4 |
| `scripts/check_w2_analysis_governance.py` | `CI_TRANSITIVE` | test_analysis_governance.py | CI → Pytest → script | CI | 否 | 无 | `KEEP` | E2/E5 |
| `scripts/check_w2_formal_tracking.py` | `MANUAL_OPS` | W2_FORMAL_TRACKING | operator → script | ops | 是 | W2_FORMAL_TRACKING | `KEEP` | E3/E4/E5 |
| `scripts/check_w2_future_refresh_staging_contract.py` | `CI_DIRECT` | ci.yml | GitHub CI → script | CI | 是 | 无 | `KEEP` | E2/E3/E5 |
| `scripts/check_w2_gate5_preflight.py` | `MANUAL_OPS` | STAGE9B_SHADOW_OPERATIONS | operator → script | offline | 否 | STAGE9B_SHADOW_OPERATIONS | `KEEP` | E4 |
| `scripts/check_w2_league_remediation_readiness.py` | `MANUAL_OPS` | league remediation doc | operator → script | offline | 否 | league remediation doc | `KEEP` | E4/E5 |
| `scripts/check_w2_market_timeline.py` | `MANUAL_OPS` | market timeline runbook | operator → script | ops | 是 | W2_MARKET_TIMELINE_LOCK_SNAPSHOTS | `KEEP` | E3/E4/E5 |
| `scripts/check_w2_production_readiness.py` | `MANUAL_OPS` | API image / packaging test | operator → script | ops | 是 | 无 | `KEEP` | E3/E4/E5 |
| `scripts/check_w2_s2_readiness.py` | `CI_TRANSITIVE` | test_w2_handicap_walkforward_cli.py | CI → Pytest → script | CI | 否 | 无 | `KEEP` | E2/E5 |
| `scripts/check_w2_stage10a.py` | `CI_TRANSITIVE` | check_w2_all.py | CI → all → script | CI | 否 | 无 | `KEEP` | E2 |
| `scripts/check_w2_stage10b.py` | `DEAD` | 无 | 无 | none | 否 | 无 | `DELETE` | D1/D2 |
| `scripts/check_w2_stage10c.py` | `MANUAL_OPS` | STAGE10C_DAILY_OPERATIONS | operator → script | ops | 否 | STAGE10C_DAILY_OPERATIONS | `KEEP` | E4 |
| `scripts/check_w2_stage10d.py` | `DEAD` | 无 | 无 | none | 否 | 无 | `DELETE` | D1/D2 |
| `scripts/check_w2_stage11a.py` | `CI_TRANSITIVE` | check_w2_all.py | CI → all → script | CI | 否 | 无 | `KEEP` | E2 |
| `scripts/check_w2_stage12a.py` | `CI_TRANSITIVE` | check_w2_all.py | CI → all → script | CI | 否 | 无 | `KEEP` | E2 |
| `scripts/check_w2_stage12b.py` | `DEAD` | 无 | 无 | none | 否 | 无 | `DELETE` | D1/D2 |
| `scripts/check_w2_stage13a.py` | `CI_TRANSITIVE` | check_w2_all.py | CI → all → script | CI | 否 | WORLD_CUP_DRY_RUN | `KEEP` | E2/E4 |
| `scripts/check_w2_stage14a.py` | `CI_TRANSITIVE` | check_w2_all.py | CI → all → script | CI | 否 | 无 | `KEEP` | E2 |
| `scripts/check_w2_stage15a.py` | `CI_TRANSITIVE` | check_w2_all.py | CI → all → script | CI | 否 | LONG_TERM_OPERATIONS | `KEEP` | E2/E4 |
| `scripts/check_w2_stage1_contracts.py` | `CI_DIRECT` | ci.yml / check_w2_all | CI → script | CI | 是 | LOCAL_DEVELOPMENT | `KEEP` | E2/E3/E4/E5 |
| `scripts/check_w2_stage3_data_model.py` | `CI_TRANSITIVE` | check_w2_all.py | CI → all → script | CI | 否 | README | `KEEP` | E2/E4/E5 |
| `scripts/check_w2_stage4_ingestion.py` | `CI_TRANSITIVE` | check_w2_all.py | CI → all → script | CI | 否 | 无 | `KEEP` | E2/E5 |
| `scripts/check_w2_stage4b_live_smoke.py` | `CI_TRANSITIVE` | check_w2_all.py | CI → all → script | CI | 否 | LIVE_INGESTION_VERIFIED | `KEEP` | E2/E4 |
| `scripts/check_w2_stage5_asof.py` | `CI_TRANSITIVE` | check_w2_all.py | CI → all → script | CI | 否 | 无 | `KEEP` | E2 |
| `scripts/check_w2_stage5b.py` | `CI_TRANSITIVE` | check_w2_all.py | CI → all → script | CI | 否 | 无 | `KEEP` | E2 |
| `scripts/check_w2_stage6_market.py` | `CI_TRANSITIVE` | check_w2_all.py | CI → all → script | CI | 否 | 无 | `KEEP` | E2 |
| `scripts/check_w2_stage6b.py` | `DEAD` | 无 | 无 | none | 否 | 无 | `DELETE` | D1/D2 |
| `scripts/check_w2_stage7_models.py` | `CI_TRANSITIVE` | check_w2_all.py | CI → all → script | CI | 否 | 无 | `KEEP` | E2 |
| `scripts/check_w2_stage7b.py` | `CI_TRANSITIVE` | check_w2_all.py | CI → all → script | CI | 否 | 无 | `KEEP` | E2 |
| `scripts/check_w2_stage7c.py` | `CI_TRANSITIVE` | check_w2_all.py | CI → all → script | CI | 否 | FORWARD_HOLDOUT_CYCLE | `KEEP` | E2/E4 |
| `scripts/check_w2_stage7d.py` | `CI_TRANSITIVE` | check_w2_all.py | CI → all → script | CI | 否 | FORWARD_HOLDOUT_AUTOMATION | `KEEP` | E2/E4 |
| `scripts/check_w2_stage7e.py` | `CI_TRANSITIVE` | check_w2_all.py | CI → all → script | CI | 否 | STAGE7E_AUTORUN_OPERATIONS | `KEEP` | E2/E4 |
| `scripts/check_w2_stage7f.py` | `DEAD` | 无 | 无 | none | 否 | 无 | `DELETE` | D1/D2 |
| `scripts/check_w2_stage7g.py` | `DEAD` | 无 | 无 | none | 否 | 无 | `DELETE` | D1/D2 |
| `scripts/check_w2_stage7h.py` | `DEPLOYMENT` | deploy_stage7h_staging.sh | operator → deploy → script | staging | 是 | STAGE7H_VPS_STAGING | `KEEP` | E3/E4/E5 |
| `scripts/check_w2_stage7i.py` | `MANUAL_OPS` | 人工 CLI；integration tests 验证 | operator → script | offline | 否 | 无 | `KEEP` | E4/E5 |
| `scripts/check_w2_stage8_replay.py` | `CI_TRANSITIVE` | check_w2_all.py | CI → all → script | CI | 否 | 无 | `KEEP` | E2 |
| `scripts/check_w2_stage9a.py` | `MANUAL_OPS` | STAGE9A_SHADOW_OPERATIONS | operator → script | offline | 否 | STAGE9A_SHADOW_OPERATIONS | `KEEP` | E4 |
| `scripts/check_w2_stage9b.py` | `DEAD` | 无 | 无 | none | 否 | 无 | `DELETE` | D1/D2 |
| `scripts/debug_w2_formal_market.py` | `MANUAL_OPS` | 人工 CLI | operator → script | offline | 否 | 无 | `KEEP` | E1/E4 |
| `scripts/debug_w2_formal_recommendations.py` | `CI_TRANSITIVE` | test_formal_explainability_audit.py | CI → Pytest → script | CI | 否 | 无 | `KEEP` | E2/E5 |
| `scripts/debug_w2_modeling_sanity.py` | `MANUAL_OPS` | API image / tests | operator → script | ops | 是 | 无 | `KEEP` | E3/E4/E5 |
| `scripts/debug_w2_s2_calibration_validation.py` | `MANUAL_OPS` | API image / tests | operator → script | ops | 是 | 无 | `KEEP` | E3/E4/E5 |
| `scripts/deploy_stage7h_staging.sh` | `DEPLOYMENT` | staging runbooks | operator → script | staging | 否 | STAGE7H_VPS_STAGING / HARDENING | `KEEP` | E3/E4/E5 |
| `scripts/diagnose_staging_runtime.sh` | `DEPLOYMENT` | STAGING_RUNTIME_HARDENING | operator → script | staging | 否 | STAGING_RUNTIME_HARDENING | `KEEP` | E3/E4/E5 |
| `scripts/export_w2_audit_tables.py` | `MANUAL_OPS` | audit export runbook | operator → script | ops | 是 | w2_audit_table_export | `KEEP` | E3/E4/E5 |
| `scripts/export_w2_world_cup_team_ids.py` | `MANUAL_OPS` | W2_TEAM_VALUES_MAPPING | operator → script | offline | 否 | W2_TEAM_VALUES_MAPPING | `KEEP` | E4/E5 |
| `scripts/generate_release_gate_manifest.py` | `MANUAL_OPS` | 人工 CLI | operator → script | offline | 否 | 无 | `KEEP` | E1/E4 |
| `scripts/generate_w2_report.py` | `MANUAL_OPS` | HTML dashboard acceptance doc | operator → script | offline | 否 | W2_HTML_DASHBOARD_V3_ACCEPTANCE | `KEEP` | E4/E5 |
| `scripts/import_stage5b_historical_data.py` | `ONE_TIME_RECOVERY` | 人工历史导入 | operator → script | offline | 否 | 无 | `KEEP` | E7 |
| `scripts/import_team_identity_crosswalk.py` | `ONE_TIME_RECOVERY` | 人工 crosswalk 导入 | operator → script | offline | 否 | 无 | `KEEP` | E7 |
| `scripts/ingest_football_data_co_uk.py` | `MANUAL_OPS` | FOOTBALL_DATA_INGEST_TEMPLATE | operator → script | offline | 否 | FOOTBALL_DATA_INGEST_TEMPLATE | `KEEP` | E4 |
| `scripts/inventory_existing_football_data.py` | `MANUAL_OPS` | 人工 CLI | operator → script | offline | 否 | 无 | `KEEP` | E1/E4 |
| `scripts/lmm_coverage_audit.py` | `MANUAL_OPS` | 人工 CLI | operator → script | offline | 否 | 无 | `KEEP` | E1/E4 |
| `scripts/lmm_materialize_stored_lineups.py` | `MANUAL_OPS` | API image / tests | operator → script | ops | 是 | 无 | `KEEP` | E3/E4/E5 |
| `scripts/lmm_transfermarkt_snapshot.py` | `MANUAL_OPS` | API image / tests | operator → script | ops | 是 | 无 | `KEEP` | E3/E4/E5 |
| `scripts/materialize_analysis_card_canary.py` | `MANUAL_OPS` | API image / tests | operator → script | ops | 是 | 无 | `KEEP` | E3/E4/E5 |
| `scripts/materialize_captured_matchday_odds.py` | `ONE_TIME_RECOVERY` | 人工 odds 恢复 | operator → script | staging manual | 否 | PR370 closure report | `KEEP` | E4/E7 |
| `scripts/materialize_team_value_asof.py` | `MANUAL_OPS` | 人工 CLI | operator → script | offline | 否 | 无 | `KEEP` | E1/E4 |
| `scripts/preflight_runtime_writable.py` | `DEPLOYMENT` | staging parity tests | CI/operator → script | staging/CI | 否 | 无 | `KEEP` | E3/E5 |
| `scripts/probe_analysis_chain.py` | `MANUAL_OPS` | PR370 acceptance docs | operator → script | staging read-only | 否 | PR370 acceptance docs | `KEEP` | E4 |
| `scripts/project_stage10b_live_snapshot.py` | `MANUAL_OPS` | STAGE10B_DASHBOARD_LIVE_WIRING | operator → script | offline | 否 | STAGE10B_DASHBOARD_LIVE_WIRING | `KEEP` | E4 |
| `scripts/project_stage10c_matchday_read_model.py` | `CI_TRANSITIVE` | test_stage10c_matchday.py | CI → Pytest → script | CI | 否 | 无 | `KEEP` | E2/E5 |
| `scripts/publish_w2_static_report.py` | `MANUAL_OPS` | `docs/runbooks/STAGE7H_VPS_STAGING.md` | operator → script | ops | 是 | `docs/runbooks/STAGE7H_VPS_STAGING.md` | `KEEP` | E3/E4/E5 |
| `scripts/reconcile_pr370_validation_ledger.py` | `ONE_TIME_RECOVERY` | 人工 ledger 恢复 | operator → script | staging manual | 否 | 无 | `KEEP` | E7 |
| `scripts/recover_staging_runtime.sh` | `DEPLOYMENT` | STAGING_RUNTIME_HARDENING | operator → script | staging | 否 | STAGING_RUNTIME_HARDENING | `KEEP` | E3/E4/E5 |
| `scripts/render_ai_card_text.py` | `MANUAL_OPS` | README / stage1 contract | operator → script | local | 否 | README | `KEEP` | E4/E5 |
| `scripts/replay_provider_fixture.py` | `MANUAL_OPS` | INGESTION_OFFLINE_REPLAY | operator → script | offline | 否 | INGESTION_OFFLINE_REPLAY | `KEEP` | E4/E5 |
| `scripts/run_fah_master_pipeline.py` | `MANUAL_OPS` | FAH data handoff | operator → script | offline | 否 | W2_FAH_PRIVATE_DATA_HANDOFF | `KEEP` | E4 |
| `scripts/run_predeploy_e2e_smoke.sh` | `CI_DIRECT` | ci.yml | GitHub CI → script | CI | 是 | PR370 deployment context | `KEEP` | E2/E3/E4 |
| `scripts/run_prematch_refresh.py` | `CI_TRANSITIVE` | test_prematch_refresh_cli.py | CI → Pytest → script | CI | 否 | 无 | `KEEP` | E2/E5 |
| `scripts/run_readiness_fault_injection.sh` | `DEPLOYMENT` | hardening test harness | operator/test → script | staging | 否 | 无 | `KEEP` | E3/E5 |
| `scripts/run_stage10c_daily_cycle.py` | `MANUAL_OPS` | STAGE10C_DAILY_OPERATIONS | operator → script | ops | 否 | STAGE10C_DAILY_OPERATIONS | `KEEP` | E4 |
| `scripts/run_stage11a_backup_restore_drill.py` | `MANUAL_OPS` | 人工 CLI / stage11 checker reads | operator → script | offline | 否 | 无 | `KEEP` | E1/E4 |
| `scripts/run_stage12a_migration_dry_run.py` | `MIGRATION_ONLY` | check_w2_stage12a | CI checker → script contract | migration | 否 | 无 | `KEEP` | E6 |
| `scripts/run_stage12a_shadow_dry_run.py` | `MANUAL_OPS` | 人工 CLI / stage12 checker reads | operator → script | offline | 否 | 无 | `KEEP` | E1/E4 |
| `scripts/run_stage12b_shadow_comparison.py` | `MANUAL_OPS` | STAGE9B_SHADOW_OPERATIONS | operator → script | offline | 否 | STAGE9B_SHADOW_OPERATIONS | `KEEP` | E4 |
| `scripts/run_stage13a_world_cup_dry_run.py` | `MANUAL_OPS` | WORLD_CUP_DRY_RUN | operator → script | offline | 否 | WORLD_CUP_DRY_RUN | `KEEP` | E4 |
| `scripts/run_stage14a_league_audit.py` | `MANUAL_OPS` | whitelist workorder | operator → script | offline | 否 | W2_WHITELIST_TECH_WORKORDER | `KEEP` | E4/E5 |
| `scripts/run_stage15a_operations_dry_run.py` | `MANUAL_OPS` | LONG_TERM_OPERATIONS | operator → script | offline | 否 | LONG_TERM_OPERATIONS | `KEEP` | E4 |
| `scripts/run_stage4b_live_smoke.py` | `MANUAL_OPS` | LIVE_INGESTION_VERIFIED | operator → script | ops | 否 | LIVE_INGESTION_VERIFIED | `KEEP` | E4 |
| `scripts/run_stage6_market_backtest.py` | `MANUAL_OPS` | stage6 checker reads / 人工 CLI | operator → script | offline | 否 | 无 | `KEEP` | E1/E4 |
| `scripts/run_stage7i_observer.py` | `MANUAL_OPS` | 人工 CLI；unit tests | operator → script | offline | 否 | 无 | `KEEP` | E4/E5 |
| `scripts/run_stage8_replay.py` | `MANUAL_OPS` | stage8 checker reads / 人工 CLI | operator → script | offline | 否 | 无 | `KEEP` | E1/E4 |
| `scripts/run_stage9a_shadow_replay.py` | `MANUAL_OPS` | STAGE9A_SHADOW_OPERATIONS | operator → script | offline | 否 | STAGE9A_SHADOW_OPERATIONS | `KEEP` | E4/E5 |
| `scripts/run_stage9b_shadow_cycle.py` | `MANUAL_OPS` | STAGE9B_SHADOW_OPERATIONS | operator → script | offline | 否 | STAGE9B_SHADOW_OPERATIONS | `KEEP` | E4 |
| `scripts/run_w2_ah_formal_evidence.py` | `CI_TRANSITIVE` | test_w2_ah_formal_evidence_cli.py | CI → Pytest → script | CI | 否 | 无 | `KEEP` | E2/E5 |
| `scripts/run_w2_factor_model_remediation.py` | `ONE_TIME_RECOVERY` | 人工 remediation 恢复 | operator → script | staging manual | 否 | 无 | `KEEP` | E7 |
| `scripts/run_w2_formal_tracking.py` | `MANUAL_OPS` | W2_FORMAL_TRACKING | operator → script | ops | 是 | W2_FORMAL_TRACKING | `KEEP` | E3/E4/E5 |
| `scripts/run_w2_forward_outcome_ledger.py` | `MANUAL_OPS` | API image / tests | operator → script | ops | 是 | 无 | `KEEP` | E3/E4/E5 |
| `scripts/run_w2_free_tier_2024_backtest.py` | `MANUAL_OPS` | league evaluation docs | operator → script | offline | 否 | PL/Understat evaluation docs | `KEEP` | E4 |
| `scripts/run_w2_handicap_walkforward.py` | `MANUAL_OPS` | market timeline runbook | operator → script | ops | 是 | W2_MARKET_TIMELINE_LOCK_SNAPSHOTS | `KEEP` | E3/E4/E5 |
| `scripts/run_w2_independent_signal_backfill.py` | `ONE_TIME_RECOVERY` | 人工 backfill | operator → script | staging manual | 是 | 无 | `KEEP` | E3/E5/E7 |
| `scripts/run_w2_league_whitelist_audit.py` | `MANUAL_OPS` | competition README / tests | operator → script | offline | 否 | competition README | `KEEP` | E4/E5 |
| `scripts/run_w2_market_baseline_eval.py` | `MANUAL_OPS` | architecture review docs | operator → script | offline | 否 | W2_MARKET_BASELINE_EVAL | `KEEP` | E4 |
| `scripts/run_w2_market_timeline_refresh.py` | `MANUAL_OPS` | market timeline runbook | operator → script | ops | 是 | W2_MARKET_TIMELINE_LOCK_SNAPSHOTS | `KEEP` | E3/E4/E5 |
| `scripts/run_w2_matchday_refresh_plan.py` | `CI_TRANSITIVE` | test_matchday_refresh_plan_cli.py | CI → Pytest → script | CI | 否 | 无 | `KEEP` | E2/E5 |
| `scripts/run_w2_outcome_result_refresh.py` | `MANUAL_OPS` | 人工 CLI | operator → script | ops | 否 | 无 | `KEEP` | E1/E4 |
| `scripts/run_w2_pro_day1_sprint.py` | `MANUAL_OPS` | S13 odds probe doc | operator → script | offline | 否 | W2_S13_ODDS_PROBE | `KEEP` | E4 |
| `scripts/run_w2_r2_offline_evaluation.py` | `MANUAL_OPS` | 人工 CLI | operator → script | offline | 否 | 无 | `KEEP` | E1/E4 |
| `scripts/run_w2_replay_frontdoor.py` | `CI_TRANSITIVE` | test_replay_frontdoor_cli.py | CI → Pytest → script | CI | 否 | 无 | `KEEP` | E2/E5 |
| `scripts/run_w2_report_runner.py` | `MANUAL_OPS` | API image / tests | operator → script | ops | 是 | 无 | `KEEP` | E3/E4/E5 |
| `scripts/run_w2_settlement_history.py` | `MANUAL_OPS` | API image / tests | operator → script | ops | 是 | 无 | `KEEP` | E3/E4/E5 |
| `scripts/run_xg_history_backfill.py` | `ONE_TIME_RECOVERY` | 人工历史 xG 回填 CLI | operator → script | offline recovery | 否 | 无 | `KEEP` | E7 |
| `scripts/seed_competition_runtime_authority.py` | `MANUAL_OPS` | 人工 competition authority CLI（production 默认值 / `--set-enabled`） | operator → script | ops | 否 | 无 | `KEEP` | E4/E5 |
| `scripts/seed_staging_dashboard.py` | `ONE_TIME_RECOVERY` | 人工 staging 恢复 | operator → script | staging manual | 否 | W2_RELEASE_SYNC | `KEEP` | E4/E7 |
| `scripts/select_stage7i_successor.py` | `MANUAL_OPS` | 人工 CLI；unit tests | operator → script | offline | 否 | 无 | `KEEP` | E4/E5 |
| `scripts/smoke.py` | `MANUAL_OPS` | Makefile | operator → make → script | local | 否 | 无 | `KEEP` | E1/E4 |
| `scripts/summarize_w2_league_audit_diagnosis.py` | `CI_TRANSITIVE` | league evidence tests | CI → Pytest → script | CI | 否 | 无 | `KEEP` | E2/E5 |
| `scripts/summarize_w2_league_provider_usage.py` | `MANUAL_OPS` | provider usage doc | operator → script | offline | 否 | W2_PROVIDER_USAGE_RECONCILIATION | `KEEP` | E4/E5 |
| `scripts/summarize_w2_league_whitelist_scope.py` | `CI_TRANSITIVE` | test_league_whitelist_full_scope.py | CI → Pytest → script | CI | 否 | 无 | `KEEP` | E2/E5 |
| `scripts/verify_release_sync.py` | `DEPLOYMENT` | W2_RELEASE_SYNC | operator → script | staging | 否 | W2_RELEASE_SYNC | `KEEP` | E3/E4 |
| `scripts/w2_data_asset_registry.py` | `MANUAL_OPS` | 人工 CLI | operator → script | offline | 否 | 无 | `KEEP` | E1/E4 |
| `scripts/watch_staging_runtime.sh` | `DEPLOYMENT` | w2-staging-watchdog.service | systemd → script | staging | 是 | 无 | `KEEP` | E3/E5 |
| `src/w2/gates/gate5_preflight_cli.py` | `RUNTIME_ENTRYPOINT` | pyproject `w2-gate5-preflight` | console → module | runtime CLI | 否 | 无 | `KEEP` | E3/E6 |
| `src/w2/matchday/cli.py` | `RUNTIME_ENTRYPOINT` | pyproject `w2-matchday` | console → module | runtime CLI | 否 | 无 | `KEEP` | E3/E6 |
| `src/w2/observability/stage7i_observer_cli.py` | `RUNTIME_ENTRYPOINT` | pyproject `w2-stage7i-observer` | console → module | runtime CLI | 否 | 无 | `KEEP` | E3/E6 |
| `src/w2/shadow/comparison_import_cli.py` | `RUNTIME_ENTRYPOINT` | pyproject comparison import | console → module | runtime CLI | 否 | 无 | `KEEP` | E3/E6 |
| `src/w2/strategy/shadow_cycle_cli.py` | `RUNTIME_ENTRYPOINT` | pyproject `w2-shadow-cycle` | console → module | runtime CLI | 否 | 无 | `KEEP` | E3/E6 |
| `tests/secret_scan.py` | `CI_DIRECT` | ci.yml | GitHub CI → script | CI | 是 | W2_ACCEPTANCE_RUNBOOK | `KEEP` | E2/E3/E4/E5 |
<!-- SCRIPT_AUTHORITY_MATRIX_END -->
