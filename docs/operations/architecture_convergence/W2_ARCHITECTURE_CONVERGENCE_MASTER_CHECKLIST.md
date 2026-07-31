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
- [x] `src/w2/domain/legacy_decision_shim.py` 整文件删除（113 行）。
- [x] `src/w2/domain/decision_adapter.py`（986 行）中 legacy→V3 转换路径删除；V3 构造保留；
      凡只被 shim/旧测试引用的函数一并删。
- [x] `src/w2/prematch/analysis_calculator.py` 中 pre-LMM frozen artifact 兼容分支
      （注释 "Backward compatibility for immutable pre-LMM frozen artifacts" 及
      `_public_market_is_legacy_pick` 调用链）。
- [x] `src/w2/dashboard/day_view.py`：`_scoreline_simulations` 的 `pricing_shadow` 兼容读
      （保留 `simulation` 主路径）；死函数 `_is_decision_tier`。
- [x] **旧 F10 首发因子废弃**：`src/w2/features/live_factors.py` 中 `F10_LINEUPS` 相关函数
      （专家评审确认未接入主 `FeatureInputs`）；并在 `src/w2/domain/factor_registry.py`
      登记 LMM 链为唯一首发因子来源。此项是 EVAL-02B 的硬前置。
- [x] 删除后全库死代码复核，剩余疑似项只记录到待议区，不顺手删。

**不做**：不动 analysis_calculator 计算语义；不动 API；不动表。
**验收**：`LEGACY_DECISION_CONTRACT_CODE = 0`；`F10_LINEUPS` 全库零引用；全量测试与 04B 守卫绿。
**资产账本**：新增 0；删除 ≥1,100 行合同转换 + F10 死代码。
- [x] PR 合并。

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

- [x] 盘点全部球队/球员身份与 provider crosswalk 表。
- [x] canonical team / player 体系为唯一权威；迁移有效映射及 review provenance。
- [x] 其余表停止写入，零引用证明后同 PR 断言式 drop；证据不足的保持原状继续调查。
- [x] provider IDs 仅作 provenance，不再作为模型主身份。
- [x] fixture、history、rating、lineup 读取对账。
- [x] **追加**：用 3 场真实比赛演示 canonical player ↔ provider lineup 球员唯一联接查询
      （EVAL-02B"缺阵分钟占比"的前置能力）。
- [x] PR 合并。

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
Status: DONE
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
DEPENDENCY_EDGE_COUNT = 128
CYCLE_COUNT = 1
RUNTIME_REACHABLE_PACKAGE_COUNT = 27
OFFLINE_ONLY_PACKAGE_COUNT = 13
DEAD_PACKAGE_COUNT = 0
DELETED_PACKAGE_COUNT = 0
```

| package | python_file_count | direct_callers | reverse_callers | internal_dependencies | cycle_membership | entrypoints | scheduler_or_worker_reachability | api_or_web_reachability | docker_image_inclusion | role | decision | evidence |
|---|---:|---|---|---|---|---|---|---|---|---|---|---|
| `analysis` | 2 | apps:0;scripts:0;migrations:0;tests:3 | prematch | domain,ingestion,markets | SCC-1 | - | YES | YES | PYTHON_IMAGE | RUNTIME_LIBRARY | KEEP | RUNTIME_REACHABLE;AST_DEPENDENCY_GRAPH |
| `api` | 6 | apps:2;scripts:2;migrations:0;tests:12 | - | competitions,dashboard,domain,infrastructure,lineups,matchday,models,monitoring,operations,prematch,providers | - | - | YES | YES | PYTHON_IMAGE | PUBLIC_READ | KEEP | RUNTIME_REACHABLE;AST_DEPENDENCY_GRAPH |
| `audit_export` | 2 | apps:0;scripts:2;migrations:0;tests:1 | - | domain,infrastructure,reporting,tracking | - | - | NO | NO | PYTHON_IMAGE | AUDIT_EXPORT | KEEP_AUDIT | SCRIPT_ENTRY;AUDIT_EXPORT_DEPENDENCIES |
| `backtest` | 10 | apps:0;scripts:7;migrations:0;tests:10 | - | competitions,domain,ingestion,markets,models,providers | - | - | NO | NO | PYTHON_IMAGE | OFFLINE_TOOL | KEEP_OFFLINE | 7_SCRIPT_ENTRIES;HISTORICAL_RAW_CONSUMER |
| `competitions` | 8 | apps:1;scripts:11;migrations:1;tests:21 | api,backtest,features,ingestion,matchday,monitoring,operations,prematch,strategy | infrastructure,providers | SCC-1 | - | YES | YES | PYTHON_IMAGE | RUNTIME_LIBRARY | KEEP | RUNTIME_REACHABLE;AST_DEPENDENCY_GRAPH |
| `dashboard` | 16 | apps:1;scripts:2;migrations:0;tests:16 | api,matchday,prematch | domain,prematch,settlement,strategy | SCC-1 | - | YES | YES | PYTHON_IMAGE | PUBLIC_READ | KEEP | RUNTIME_REACHABLE;AST_DEPENDENCY_GRAPH |
| `data_assets` | 2 | apps:0;scripts:1;migrations:0;tests:1 | - | - | - | - | NO | NO | PYTHON_IMAGE | OFFLINE_TOOL | KEEP_OFFLINE | SCRIPT_ENTRY;ASSET_REGISTRY |
| `domain` | 14 | apps:0;scripts:2;migrations:0;tests:21 | analysis,api,audit_export,backtest,dashboard,features,historical,ingestion,markets,matchday,migration,models,normalization,operations,prematch,pricing,readiness,recovery,replay,reporting,schemas,settlement,strategy,tracking | lineups,readiness,tracking | SCC-1 | - | YES | YES | PYTHON_IMAGE | RUNTIME_LIBRARY | KEEP | RUNTIME_REACHABLE;AST_DEPENDENCY_GRAPH |
| `factor_model` | 2 | apps:0;scripts:1;migrations:0;tests:1 | - | features,identity,infrastructure,ingestion,matchday,providers,ratings | - | - | NO | NO | PYTHON_IMAGE | OFFLINE_TOOL | KEEP_OFFLINE | SCRIPT_ENTRY;OFFLINE_REMEDIATION |
| `features` | 8 | apps:0;scripts:0;migrations:0;tests:7 | factor_model,ingestion,prematch,ratings,strategy | competitions,domain,markets | SCC-1 | - | YES | YES | PYTHON_IMAGE | RUNTIME_LIBRARY | KEEP | RUNTIME_REACHABLE;AST_DEPENDENCY_GRAPH |
| `formal` | 2 | apps:0;scripts:1;migrations:0;tests:2 | strategy | - | - | - | YES | YES | PYTHON_IMAGE | RUNTIME_LIBRARY | KEEP | RUNTIME_REACHABLE;AST_DEPENDENCY_GRAPH |
| `gates` | 2 | apps:0;scripts:0;migrations:0;tests:0 | - | strategy | - | w2-gate5-preflight | NO | NO | PYTHON_IMAGE | OFFLINE_TOOL | KEEP_OFFLINE | CONSOLE_ENTRYPOINT |
| `historical` | 12 | apps:0;scripts:9;migrations:0;tests:4 | lineups | domain,identity,infrastructure | SCC-1 | - | YES | YES | PYTHON_IMAGE | RUNTIME_LIBRARY | KEEP | RUNTIME_REACHABLE;AST_DEPENDENCY_GRAPH |
| `identity` | 2 | apps:0;scripts:1;migrations:0;tests:2 | factor_model,historical,ingestion,lineups | infrastructure | - | - | YES | YES | PYTHON_IMAGE | RUNTIME_LIBRARY | KEEP | RUNTIME_REACHABLE;AST_DEPENDENCY_GRAPH |
| `infrastructure` | 19 | apps:0;scripts:12;migrations:17;tests:39 | api,audit_export,competitions,factor_model,historical,identity,ingestion,matchday,monitoring,operations,prematch,providers,settlement,strategy,tracking | - | - | - | YES | YES | PYTHON_IMAGE | RUNTIME_LIBRARY | KEEP | RUNTIME_REACHABLE;AST_DEPENDENCY_GRAPH |
| `ingestion` | 16 | apps:2;scripts:13;migrations:0;tests:16 | analysis,backtest,factor_model,prematch,providers,tracking | competitions,domain,features,identity,infrastructure,lineups,markets,matchday,normalization,prematch,providers | SCC-1 | - | YES | YES | PYTHON_IMAGE | WRITE_SIDE_PROJECTION | KEEP | RUNTIME_REACHABLE;AST_DEPENDENCY_GRAPH |
| `lineups` | 5 | apps:0;scripts:6;migrations:0;tests:6 | api,domain,ingestion,prematch | historical,identity | SCC-1 | - | YES | YES | PYTHON_IMAGE | RUNTIME_LIBRARY | KEEP | RUNTIME_REACHABLE;AST_DEPENDENCY_GRAPH |
| `markets` | 17 | apps:0;scripts:3;migrations:0;tests:16 | analysis,backtest,features,ingestion,prematch,readiness,strategy,tracking | domain,strategy | SCC-1 | - | YES | YES | PYTHON_IMAGE | RUNTIME_LIBRARY | KEEP | RUNTIME_REACHABLE;AST_DEPENDENCY_GRAPH |
| `matchday` | 11 | apps:1;scripts:3;migrations:2;tests:9 | api,factor_model,ingestion,prematch,refresh | competitions,dashboard,domain,infrastructure,providers,readiness,refresh,strategy | SCC-1 | w2-matchday | YES | YES | PYTHON_IMAGE | RUNTIME_ENTRYPOINT | KEEP | RUNTIME_REACHABLE;AST_DEPENDENCY_GRAPH |
| `migration` | 3 | apps:0;scripts:2;migrations:0;tests:1 | - | domain | - | - | NO | NO | PYTHON_IMAGE | MIGRATION_ONLY | KEEP_MIGRATION | 2_SCRIPT_ENTRIES;MIGRATION_RECOVERY |
| `models` | 12 | apps:0;scripts:2;migrations:0;tests:8 | api,backtest,operations,recovery,strategy | domain | SCC-1 | - | YES | YES | PYTHON_IMAGE | RUNTIME_LIBRARY | KEEP | RUNTIME_REACHABLE;AST_DEPENDENCY_GRAPH |
| `monitoring` | 5 | apps:1;scripts:3;migrations:0;tests:4 | api | competitions,infrastructure,providers | - | - | YES | YES | PYTHON_IMAGE | RUNTIME_LIBRARY | KEEP | RUNTIME_REACHABLE;AST_DEPENDENCY_GRAPH |
| `normalization` | 2 | apps:0;scripts:2;migrations:0;tests:1 | ingestion | domain | SCC-1 | - | YES | YES | PYTHON_IMAGE | RUNTIME_LIBRARY | KEEP | RUNTIME_REACHABLE;AST_DEPENDENCY_GRAPH |
| `observability` | 2 | apps:0;scripts:0;migrations:0;tests:0 | - | - | - | w2-stage7i-observer | NO | NO | PYTHON_IMAGE | OFFLINE_TOOL | KEEP_OFFLINE | CONSOLE_ENTRYPOINT |
| `operations` | 11 | apps:1;scripts:7;migrations:0;tests:9 | api,prematch,providers,security | competitions,domain,infrastructure,models | SCC-1 | - | YES | YES | PYTHON_IMAGE | RUNTIME_LIBRARY | KEEP | RUNTIME_REACHABLE;AST_DEPENDENCY_GRAPH |
| `prematch` | 7 | apps:1;scripts:6;migrations:0;tests:29 | api,dashboard,ingestion,tracking | analysis,competitions,dashboard,domain,features,infrastructure,ingestion,lineups,markets,matchday,operations,pricing,providers,ratings,strategy,tracking | SCC-1 | - | YES | YES | PYTHON_IMAGE | WRITE_SIDE_PROJECTION | KEEP | RUNTIME_REACHABLE;AST_DEPENDENCY_GRAPH |
| `pricing` | 6 | apps:0;scripts:0;migrations:0;tests:3 | prematch | domain,strategy | SCC-1 | - | YES | YES | PYTHON_IMAGE | RUNTIME_LIBRARY | KEEP | RUNTIME_REACHABLE;AST_DEPENDENCY_GRAPH |
| `providers` | 5 | apps:2;scripts:6;migrations:0;tests:11 | api,backtest,competitions,factor_model,ingestion,matchday,monitoring,prematch | infrastructure,ingestion,operations | SCC-1 | - | YES | YES | PYTHON_IMAGE | RUNTIME_LIBRARY | KEEP | RUNTIME_REACHABLE;AST_DEPENDENCY_GRAPH |
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
| `tracking` | 12 | apps:1;scripts:5;migrations:0;tests:16 | audit_export,domain,prematch | domain,infrastructure,ingestion,markets,prematch,settlement | SCC-1 | w2-finished-match-scoring | YES | YES | PYTHON_IMAGE | WRITE_SIDE_PROJECTION | KEEP | RUNTIME_REACHABLE;AST_DEPENDENCY_GRAPH |

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
Status: DONE
PR: #429
Merge SHA: 86a66ff5c07438b0543d2790165d406d452daedb
CI: 30435005222
Conclusion: P0/P1/P2 最终架构收敛验收通过；22 包 SCC 与 schemas 待调查项如实保留。
```

- [x] P0 与 P1 的历史台账、A1–A7 实施 PR 和 merge SHA 已逐项对 Git/GitHub 核对；
      原台账 #380、#382、#388 的三个错误短 SHA 已改为真实前缀。
- [x] P2-02、P2-03、P2-04、P2-06 的完成坐标/本地结论完整；P2-05 仅在 PR #429 合并后标 DONE。
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
- [x] exact-head FULL CI、外部验收与 PR 合并。

```text
P0_ARCHITECTURE_CONVERGENCE_PASS = PASS
P1_ARCHITECTURE_CONVERGENCE_PASS = PASS
P2_ARCHITECTURE_FINAL_ACCEPTANCE = PASS
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

**最终状态**：`W2_ARCHITECTURE_CONVERGENCE_COMPLETE = PASS`

---

### 阶段 B：EVAL 能力建设（ARCH-P1-08 通过后启动）

> 总目标：闭合"赛果→表现→反馈"回边，每场比赛（而非每次推荐）都产生可信度量；
> 首发因子两面处理：有首发的联赛验增量，无首发的联赛防逆向选择。

```text
Status: IN_PROGRESS
```

---

#### B1. EVAL-01A：赛果与结算账本数据库化

```text
Status: DONE
Branch: codex/eval-01a-results-outcome-ledger-db
PR: #424
Merge SHA: dc1a665655add801c4fe5cd7a0f39211d836e916
Main CI: 30441901340
```

PR #424 已完成 exact-head FULL CI、外部 Review、staging 验收并合并。

**目标**：赛果获得 DB 唯一权威；runtime 文件账本（最后一块文件飞地）迁入 DB 并删除。

- [x] **赛果权威 = 现有 `results` 表**（不新建）。新增 worker 任务：FINISHED 后从**已采集**的
      provider fixture 数据（`raw_payload` / matchday 采集链的 FT 状态与比分）提取
      `MatchResult` 写入 `results`。**不新增任何 provider 调用**；缺比分场次记
      `RESULT_SOURCE_MISSING`，不补采。
- [x] **runtime 账本迁移**：`runtime/forward_outcome_ledger/*` 与
      `src/w2/tracking/formal_results.py` 的文件读写（11、26 处）迁入 DB；
      建表与否按第三节授权基准 (a) 执行，判定证据写入本文件。
      迁移行数+hash 对账后**同一 PR** 删除文件读写路径，`runtime/` 不再有账本目录。
- [x] `src/w2/settlement/settle.py` 消费 DB `results`；`forward_ledger_performance`
      记录来源改为 DB 查询（调用方 `analysis_calculator.py` 语义不动）。

**不做**：不改 CLV/命中率计算逻辑；不动 canonical 样本定义；不做 Dashboard。
**验收**：`RESULTS_DB_AUTHORITY_COUNT = 1`；`RUNTIME_LEDGER_FILE_IO = 0`（静态守卫，
模式同 `test_production_report_reads.py`）；迁移对账一致；老板可见的历史表现数字不漂移。
**资产账本**：新增 ≤1 表（按基准判定）；删除 runtime 账本目录 + 文件 IO 代码。

**建表授权判定**：`OUTCOME_LEDGER_DECISION = CREATE_ONE_TABLE`

1. `results` 每场只保存一个终场比分，无法承载 capture、outcome、supersession、报价时间线和非正式验证事件。
2. `settlements` 强绑定 `recommendation_id` 与 `result_id`；承载 validation/shadow/capture 会伪造正式推荐身份并扭曲列语义。
3. 历史 JSONL 的 fixture/recommendation scope、pick/shadow pick、quote/artifact/probability provenance、
   capture/decision/supersession identity 与 settlement evidence 无法无损映射到现有两表。

- [x] PR 合并。

---

#### B2. EVAL-01B：全量校准评分投影

```text
Status: DONE
Branch: codex/eval-01b-finished-match-scoring-projection
PR: #430
Source head: dbd70161823c45a1a8e38b68be7de646db2d2a33
Merge SHA: 5c2bd6f2e5c23196a25495335da72599e076c8ae
Main CI: 30477611652
Staging acceptance: PASS
Conclusion: 全量 finished-match scoring projection、legacy parity、cohort、幂等和 fail-closed staging 验收通过。
```

**目标**：每场 FINISHED 比赛自动产生"模型 vs 市场"评分——不管推没推荐。

```text
B2_RESULT_AUTHORITY = results
B2_1X2_PROBABILITY_AUTHORITY = outcome_ledger.capture.probability_identity
B2_DYNAMIC_EVALUATION_ROLE = AH_OU_LIFECYCLE_METADATA_ONLY
B2_SCORING_TABLE_COUNT = 0
```

输入权威：终场比分来自 `results`；评分概率来自 `outcome_ledger` 中该
fixture 开赛前最后一条完整、未 supersede 的
`capture.probability_identity`。CLV 复用
`forward_ledger_performance.py` 的既有语义。`dynamic_prematch_evaluations`
只补充 checkpoint、lineup 与 AH/OU 生命周期元数据，且仅允许精确身份连接。

- [x] 触发：EVAL-01A 赛果提交后调用同一个写侧投影；不建新管线框架。
- [x] 输入：权威赛果 + 最后一条完整未 supersede 的赛前 1X2 概率 capture；
      无 pick/WATCH/SKIP 仍评分，冲突 fail-closed。
- [x] 输出（全部落 `read_model_checkpoint`，不建新表）：
      `performance:fixture:{id}`（双方 log loss/Brier/RPS、CLV、联赛、STRICT/ADVISORY 分层标签）；
      `performance:cohort:{scope}`（按联赛/分层/7-30-90 天窗口滚动聚合，含样本计数）。
- [x] 幂等：同一 fixture 重算 hash 一致且零写；投影带
      projection_version/source_event；同源不同 payload fail-closed。
- [x] 运维回填：显式 CLI 默认 dry-run，写入要求双重确认；文本/JSON
      输出分离，provider calls 固定为 0。

**不做**：不做 UI；不做任何"评分→参数"自动反馈（那是 EVAL-02B 门禁的事）。
**验收**：staging 全部已完结且有评估记录的比赛 100% 产生 `performance:fixture:*`；
抽 5 场人工复算一致；API 守卫不变绿（评分在写侧）。
**资产账本**：新增 0；删除 0。
- [x] PR 合并。

---

#### B3. EVAL-01C：Dashboard 表现视图（CLV 第一 KPI）

```text
Status: DONE
PR: #432
Source head: f136bd9c11c67defeed9de39095130f7848aee64
Merge SHA: 10ace8f67bb3ecfa8481be4f9906c485d20b2d16
Main CI: 30517146657
Staging acceptance: PASS
Conclusion: CLV 第一 KPI、全量校准、STRICT/ADVISORY 分层、canonical 命中率、
样本进度及 projection-only API/Web 均完成 exact-head staging 验收。
```

- [x] API/Web 只读表现页，仅读 `performance:*` 投影：
      ① CLV 第一位（canonical picks 分布、均值与置信区间、正 CLV 占比）；
      ② 全量校准（model vs market 滚动 log loss 差、校准曲线）；
      ③ STRICT vs ADVISORY 分层表（命中率、CLV、样本数并列）；
      ④ 样本进度条（对照预注册目标；未达标时命中率旁强制"样本不足"标注）。
- [x] 前端不做任何概率/指标重算（04B 守卫覆盖 `apps/web/src`，保持绿）。

**验收**：页面数字与投影逐项一致；20 轮只读零写；15/30 场视觉验收。
**资产账本**：新增 0；删除 0。
- [x] PR 合并。

---

#### B4. EVAL-02A：首发盲区防护（防守面，先于增量验证）

```text
Status: DONE
Branch: codex/eval-02a-lineup-blind-spot-defense
PR: #434
Source head: 43a9e5aae1da6821edfc88d048c680b52ff870fb
Merge SHA: 427cb2203d943304582e5aa3f6b55e5d6b8adce0
Main CI: 30556679131
Staging acceptance: PASS
```

**完成结论**：exact-head staging 与合并后 main required CI 均通过，EVAL-02A 闭合。

**目标**：ADVISORY 联赛（无赛前首发）的 pick 不再裸奔；盲区里"模型大幅打赢市场"按逆向选择风险处理。

**预注册参数（本任务冻结，不随测试结果调整）**：

```text
MARKET_TIMELINE_AUTHORITY = matchday_market_observations
LINEUP_HISTORY_AUTHORITY = structured_lineup_snapshots + structured_lineup_players
TEAM_BASELINE_AUTHORITY = team_lineup_baselines
PERFORMANCE_AUTHORITY = performance:fixture:* + performance:cohort:*
POLICY_CHECKPOINT = performance:policy:advisory-blind-spot
NEW_TABLE_COUNT = 0
NEW_MIGRATION_COUNT = 0
NEW_PROVIDER_PATH_COUNT = 0
NEW_CONFIG_AUTHORITY_COUNT = 0

DIVERGENCE_SCHEMA_VERSION = w2.divergence_origin.v1
DIVERGENCE_FORMULA_VERSION = eval-02a.v1
FROZEN_EV_DISTRIBUTION =
  当前 selected candidate 的完整五态结算分布：
  WIN / HALF_WIN / PUSH / HALF_LOSS / LOSS
opening_ev =
  expected_value(opening_decimal_odds, FROZEN_EV_DISTRIBUTION)
current_ev =
  expected_value(current_decimal_odds, FROZEN_EV_DISTRIBUTION)
opening 与 current 必须复用同一五态分布；只替换 decimal odds。
model_probability 仅为审计字段，不得替代 settlement-distribution EV。
movement_created_ev = max(current_ev - max(opening_ev, 0), 0)
movement_ev_share = clamp(movement_created_ev / max(current_ev, 1e-12), 0, 1)
divergence_age_ratio = clamp(max(min(opening_ev, current_ev), 0) / max(current_ev, 1e-12), 0, 1)
movement_ev_share > 0.5 = MOVEMENT_CREATED_DIVERGENCE
movement_ev_share == 0.5 = not MOVEMENT_CREATED_DIVERGENCE
non-moved and divergence_age_ratio >= 0.6 = STABLE_DIVERGENCE
otherwise = INDETERMINATE
effective risk: MOVEMENT_CREATED_DIVERGENCE -> MOVED
effective risk: INDETERMINATE -> MOVED_CONSERVATIVE
effective risk: STABLE_DIVERGENCE -> STABLE

ROTATION_PRIOR_SCHEMA_VERSION = w2.team_rotation_prior.v1
confirmed pre-kickoff complete XI only; latest snapshot per fixture; latest 6 matches
turnover_i = (11 - starter_overlap_i) / 11
rotation_rate = arithmetic mean of latest 5 turnovers
transition_count >= 4 = READY
rotation_rate >= 4 / 11 = HIGH_ROTATION

ADVISORY_DELTA_SCHEMA_VERSION = w2.advisory_blind_spot_policy.v2
initial delta = 0.0
window = 90d
minimum advisory canonical settled = 50
bootstrap iterations = 10000
bootstrap seed = deterministic source hash
lower_bound_80 = q10(STRICT mean CLV - ADVISORY mean CLV bootstrap distribution)
delta = max(0, lower_bound_80)
recalibrate after 50 new ADVISORY canonical settled or 90 days
effective_advisory_ev_threshold = existing_threshold + delta
ADVISORY rolling CLV mean - delta <= 0 = watch_only

PERFORMANCE_SCHEMA_VERSION = w2.performance_projection.v3
PERFORMANCE_PROJECTION_VERSION = eval-02a.v1
lineup_deviation = 1 - starter_continuity
canonical MISS and selected deviation >= 4/11 or high rotation = ROTATION_ASSOCIATED
canonical MISS with complete lower deviation evidence = NON_ROTATION_RESIDUAL
canonical MISS with incomplete evidence = INSUFFICIENT_EVIDENCE
non-MISS = NOT_LOSS
STRICT = NOT_APPLICABLE_STRICT
causal_claim = false
```

- [x] **分歧成因分类器**（写侧 `analysis_calculator`）：用 `matchday_market_observations`
      timeline 计算 `divergence_age_ratio` 与 `movement_ev_share`，按第三节授权基准 (b)
      固化阈值输出三态标签。
- [x] **降级规则**：ADVISORY + `MOVEMENT_CREATED_DIVERGENCE` → 强制 `WATCH`，
      reason `MARKET_MOVED_AGAINST_BLIND_SPOT`。
- [x] **风险披露**：decision contract reason 结构新增 `LINEUP_UNOBSERVABLE`
      （ADVISORY 联赛所有卡携带）；按永久红线 10 同步校验器与守卫；
      新增字段不是语义变更，pick/non-pick 互斥不动。
- [x] **轮换先验**：用赛后阵容记录为 ADVISORY 联赛建基线与球队轮换率
      （复用 `build_team_baseline`）；高轮换球队盲区比赛追加 `HIGH_ROTATION_PRIOR`。
- [x] **赛后归因**：`performance:fixture:*` 追加赛后首发相对基线偏离度，
      仅统计 `ROTATION_ASSOCIATED` 与 `NON_ROTATION_RESIDUAL`，不作因果声明。
- [x] **δ 溢价**：本任务 δ=0 只标注；标定与生效按第三节授权基准 (b) 自动执行，
      结果写入本文件即生效。

**不做**：不动 STRICT 联赛逻辑；不改 EV 公式；不解冻任何数值调整。
**验收**：ADVISORY 卡 100% 携带 `LINEUP_UNOBSERVABLE`；重放一场"移动产生分歧"样例
验证降级 WATCH；合同守卫全绿；分层统计出现盲区归因字段。
**资产账本**：新增 0；删除 0。
- [x] PR 合并。

---

#### B5. EVAL-02B：首发增量门禁验证（进攻面，样本驱动）

```text
Status: BLOCKED
前置：A2（F10 已删）、A3（球员身份可联接）、B2（评分基建）、
      每联赛 LINEUP_CONFIRMED 配对评估历史 ≥120 场
EVAL_02B_START_AUTHORIZED = false
START_QUALIFICATION_AUDIT_AS_OF = 2026-07-30T16:06:59.736350Z
START_QUALIFICATION_AUDIT_SHA256 = c4099f973f46514c3105911eee9bf87accd20f98b2430998868716d8ae13e70d
AUDIT_AS_OF = 2026-07-30T17:31:23.303986Z
AUDIT_SHA256 = 8871fa588091b2daa8c72bd36837e044f462c194f9bc7804bcde27015d063ad0
EXACT_UNIQUE_CANDIDATE_COUNT = 0
UNRESOLVED_RESULT_COUNT = 35

DATA_BLOCKER =
dynamic_prematch_evaluations 0
lineup_confirmed_events 0
exact pre/post pairs 0
35 results 缺唯一 canonical competition/season identity

CONTRACT_AUTHORITY = FROZEN
DATA_ACQUISITION_PLAN = AUTHORIZED
RUNTIME_COLLECTION_AUTHORIZED = false
IDENTITY_REMEDIATION_DESIGN = BLOCKED
IDENTITY_REMEDIATION_EXECUTION_AUTHORIZED = false
IDENTITY_PROVENANCE_GAP_DECISION =
LEGACY_35_RESULTS_EXCLUDED_FROM_EVAL_02B
LEGACY_RESULT_FACTS_RETAINED = true
LEGACY_RESULT_FACTS_MUTATED = false
LEGACY_RESULT_EVAL_ELIGIBILITY = false
LEGACY_IDENTITY_REMEDIATION_CLOSED = true
FUTURE_ONLY_PAIR_COLLECTION_REQUIRED = true
WRITE_SIDE_IMPLEMENTATION_01 = DONE
WRITE_SIDE_IMPLEMENTATION_01_PR = 441
WRITE_SIDE_IMPLEMENTATION_01_MERGE_SHA =
5c52a40a6f0b3afb8589c251bea0b7ba611012f5
WRITE_SIDE_IMPLEMENTATION_01_MAIN_CI = 30583359805
WRITE_SIDE_IMPLEMENTATION_AUTHORIZED = false
WRITE_SIDE_EXECUTION_TRANCHE = COMPLETED
WRITE_SIDE_IMPLEMENTATION_02 = DONE
WRITE_SIDE_IMPLEMENTATION_02_PR = 443
WRITE_SIDE_IMPLEMENTATION_02_HEAD =
8eaf04699414a1ebe65077e419651f567910c45d
WRITE_SIDE_IMPLEMENTATION_02_MERGE_SHA =
532e58c44fe388d7053d8c0b3c3b7d5fa934cacb
WRITE_SIDE_IMPLEMENTATION_02_MAIN_CI = 30598884065
WRITE_SIDE_IMPLEMENTATION_03 = DONE
WRITE_SIDE_IMPLEMENTATION_03_PR = 444
WRITE_SIDE_IMPLEMENTATION_03_HEAD =
b959e4a3a406fcc9898695643a17fac9c069281f
WRITE_SIDE_IMPLEMENTATION_03_MERGE_SHA =
882f69650d4773757529999e3f8292e8689231a2
WRITE_SIDE_IMPLEMENTATION_03_MAIN_CI = 30599432182
WRITE_SIDE_IMPLEMENTATION_04 = DONE
WRITE_SIDE_IMPLEMENTATION_04_PR = 445
WRITE_SIDE_IMPLEMENTATION_04_HEAD =
05b55b5e1fc6583abbdee705a6b39bd263da4372
WRITE_SIDE_IMPLEMENTATION_04_MERGE_SHA =
308e1edc9ed1748a18cd64c9325521e54a5777ba
WRITE_SIDE_IMPLEMENTATION_04_MAIN_CI = 30599981432
PROVIDER_CALLS_AUTHORIZED = false
SCHEDULER_START_AUTHORIZED = false
WRITE_SIDE_READINESS_DESIGN = FROZEN
WRITE_SIDE_READY = true
NEW_TABLE_COUNT = 0
NEW_MIGRATION_COUNT = 0
LINEUP_EVENT_PRODUCTION_CALLER = IMPLEMENTED
CANONICAL_LINEUP_EVENT_ATOMIC_WRITE = IMPLEMENTED
POST_LINEUP_REFRESH_PLAN_PRODUCTION_CALLER = IMPLEMENTED
DYNAMIC_EVALUATION_V2 = IMPLEMENTED
FIVE_STATE_SNAPSHOT = IMPLEMENTED
EXACT_PAIR_PROJECTOR = IMPLEMENTED
PAIR_EVIDENCE_AUTHORITY =
IMMUTABLE_ORIGINAL_EVALUATION
LIFECYCLE_SUPERSESSION_EFFECT =
DIAGNOSTIC_ONLY
PRE_POST_ELIGIBILITY_REQUIRES_NOT_SUPERSEDED = false
FORWARD_COLLECTION_ACTIVATION_REVIEW = FROZEN
FORWARD_COLLECTION_ACTIVATION_READY = false
COMPOSE_FAIL_CLOSED_DEFAULTS = VERIFIED
PROVIDER_CODE_DEFAULT_FAIL_CLOSED = MISSING
RUNTIME_AUTHORITY_ENFORCEMENT = MISSING
BOUNDED_SUPERVISED_ONE_SHOT = MISSING
ACTIVATION_BLOCKER =
SUPERVISED_FORWARD_COLLECTION_GUARD_REQUIRED
FORWARD_COLLECTION_GUARD_IMPLEMENTATION_AUTHORIZED = true
SUPERVISED_ONE_SHOT_AUTHORIZED = false
PERSISTENT_SCHEDULER_AUTHORIZED = false
SCORING_IMPLEMENTATION = BLOCKED
NEXT_REQUIRED_ACTION =
SUPERVISED_FORWARD_COLLECTION_GUARD_IMPLEMENTATION
```

**预注册门禁合同（已冻结）**：

```text
PAIR_SCOPE = PER_COMPETITION_X_MARKET
PAIR_GRAIN = ONE_CANONICAL_FIXTURE_PAIR
MINIMUM_ELIGIBLE_TOTAL_PAIRS = 120
TIME_SPLIT = STRICT_CHRONOLOGICAL_70_30
MINIMUM_VALIDATION_PAIRS = 36
BOOTSTRAP_ITERATIONS = 10000
BOOTSTRAP_UNIT = PAIRED_VALIDATION_FIXTURE
MINIMUM_COMPETITIONS = NOT_APPLICABLE
```

`MINIMUM_ELIGIBLE_TOTAL_PAIRS = 120` 是严格时间切分前、每个 competition×market
的合格总配对数；不得解释为 500 个验证样本。

**评分合同（已冻结，实施仍阻塞）**：

```text
SETTLEMENT_STATE_ORDER =
WIN, HALF_WIN, PUSH, HALF_LOSS, LOSS

BASELINE_DISTRIBUTION =
baseline_probability_by_settlement_state

CANDIDATE_DISTRIBUTION =
candidate_probability_by_settlement_state

DISTRIBUTIONS_SHARE_IDENTICAL_STATE_SPACE = true
DISTRIBUTION_VALUES_MAY_DIFFER = true
PROBABILITY_VALUES = FINITE_AND_NON_NEGATIVE
PROBABILITY_SUM_TOLERANCE = 1e-9
LOG_LOSS_EPSILON = 1e-9
OBSERVED_SETTLEMENT_STATE = REQUIRED
MISSING_OR_INVALID_DISTRIBUTION = FAIL_CLOSED

LL(distribution, observed_state) =
-ln(max(distribution[observed_state], LOG_LOSS_EPSILON))

paired_log_loss_improvement =
LL(baseline_distribution, observed_state)
-
LL(candidate_distribution, observed_state)

GATE_PASS =
log_loss_improvement_ci_low > 0

SCORING_IMPLEMENTATION = BLOCKED
SCORING_IMPLEMENTATION_BLOCKER =
COMPLETE_PERSISTED_BASELINE_AND_CANDIDATE_FIVE_STATE_DISTRIBUTIONS_UNAVAILABLE
```

Baseline 与 candidate 是两套独立概率向量；两者使用相同、有序的五态空间，但不要求
概率值相等。每个概率必须 finite 且非负，概率和与 1 的差不得超过 `1e-9`，observed
settlement state 必须属于冻结五态；任一分布缺失或非法均 fail-closed。整数盘、半盘和
四分之一盘统一使用上述合同，不得把 PUSH、HALF_WIN 或 HALF_LOSS 转成二元 outcome。
现有持久化证据不能提供完整的 baseline/candidate 五态分布，因此不得发明新公式，
EVAL-02B 继续 fail-closed。

```text
CONTRACT_VERSION = w2.eval_02b_gate.v1

ORDER_BY =
kickoff_at ASC, canonical_fixture_id ASC

VALIDATION_START_INDEX =
floor(total_eligible_pairs * 0.70)

VALIDATION_SET =
ordered_pairs[VALIDATION_START_INDEX:]

PAIR_IDENTITY_SERIALIZATION =
UTF8_CANONICAL_JSON_SORTED_KEYS_COMPACT

PAIR_IDENTITY_HASH =
SHA256(PAIR_IDENTITY_SERIALIZATION)

BOOTSTRAP_SEED_PAYLOAD =
canonical_json({
  contract_version,
  validation_pair_identity_hashes:
    sorted(validation_pair_identity_hashes)
})

BOOTSTRAP_SEED_HASH =
SHA256(BOOTSTRAP_SEED_PAYLOAD)

BOOTSTRAP_SEED =
UNSIGNED_BIG_ENDIAN_UINT64(
  FIRST_8_BYTES(BOOTSTRAP_SEED_HASH)
)
```

Bootstrap 只重采样 validation fixture pairs；95% 区间固定取 2.5% 与 97.5% 分位数。
Canonical JSON 禁止 NaN/Infinity，key 必须排序并使用 compact separators。相同
validation pair 集合必须产生完全相同的整数 seed；相同输入必须产生相同的 split、
seed 和 bootstrap 区间。

```text
RPS_ROLE = DIAGNOSTIC_ONLY
COVERAGE_ROLE = DIAGNOSTIC_ONLY
REVALIDATE_AFTER_DAYS = 90
REVALIDATE_AFTER_NEW_PAIRS = 60
CI_CONTAINS_ZERO = FREEZE_ADJUSTMENT_TO_ZERO
```

RPS 与 coverage 必须输出，但在新的预注册授权前不得作为 blocker。

**配对身份（已冻结）**：

- Pre/Post 必须属于同一 canonical fixture、competition、season、market、selection
  和 exact line。
- Pre 是首发确认前最后一个合格持久化评估；Post 是首发确认后第一个使用 fresh
  exact quote 的合格评估。
- 必须满足 `pre.capture_at < lineup_confirmed_at <= post.capture_at`；每场 fixture
  只允许一个 pair。
- 冲突、缺身份、缺赛果、跨赛季、跨联赛、marker-only 和原始状态不合格的数据
  全部排除；lifecycle supersession relation 仅作诊断，不影响原始合格 evidence。
- 禁止 fuzzy、名称猜测或跨 bookmaker/line 拼接。

```text
PRE_ELIGIBILITY_TIME_AUTHORITY = capture_at
POST_ELIGIBILITY_TIME_AUTHORITY = capture_at

PRE_EVALUATED_AT_ROLE =
DETERMINISTIC_TIE_BREAKER_ONLY

POST_EVALUATED_AT_ROLE =
DETERMINISTIC_TIE_BREAKER_ONLY

PRE_ORDER =
capture_at DESC
evaluated_at DESC
evaluation_id DESC

POST_ORDER =
capture_at ASC
evaluated_at ASC
evaluation_id ASC

PAIR_QUOTE_SCOPE =
SAME_PROVIDER_X_BOOKMAKER_X_MARKET_X_SELECTION_X_EXACT_LINE

PRE_POST_PROVIDER_ID = SAME
PRE_POST_BOOKMAKER_ID = SAME
CAPTURE_ID = MAY_DIFFER
QUOTE_IDENTITY_MISSING_OR_CONFLICTING = FAIL_CLOSED

PAIR_IDENTITY_HASH_MINIMUM_FIELDS =
canonical_fixture_id
competition_id
season_id
provider_id
bookmaker_id
market
selection
exact_line
pre_evaluation_id
post_evaluation_id
```

Pre 是否发生在首发确认前只看 persisted `capture_at`，`evaluated_at` 不作为 eligibility
boundary。开赛前已采集、但首发确认后才完成处理的 Pre 仍可合格；`evaluated_at` 仅在
相同 `capture_at` 时用于稳定排序。

Pre/Post 不得跨 provider、bookmaker、selection 或 line 配对。

**数据获取权限方案（只授权方案，不授权启动）**：

1. **Phase 1：身份修复。** 35 个历史 results 只能使用已持久化的
   fixture/raw/capture provenance 建立 canonical competition/season 身份；仅精确唯一
   映射允许写入，多义或缺失继续保持 blocker；不得调用 Provider，不得用 direct SQL
   绕过写侧合同。后续实施必须使用独立、幂等、可回滚 PR。
2. **Phase 2：写侧就绪。** 后续独立 PR 核验并补齐
   `dynamic_prematch_evaluations`、`lineup_confirmed_events` 的真实写侧，以及 Pre/Post
   自动配对所需的 exact identity；不得制造历史样本或使用 synthetic 数据充数。
3. **Phase 3：真实未来采集。** 只有另行取得 activation 授权后，才允许启动 scheduler、
   产生 Provider 请求并为真实未来比赛积累 paired samples。activation PR 必须先登记：

```text
LEAGUE_SCOPE
MARKET_SCOPE
ENDPOINT_SCOPE
CAPTURE_CADENCE
DAILY_REQUEST_BUDGET
ROLLBACK
PROVIDER_CALL_LIMIT
```

Recommendation、Candidate、Formal、Lock、Production 全程保持关闭。

**Phase 1 身份修复设计与只读可行性审计**：

```text
RESULT_AUTHORITY = results
FIXTURE_IDENTITY_AUTHORITY = matchday_fixture_identities
LEAGUE_MAPPING_AUTHORITY = league_profile + league_season
RESULT_ROWS_MUTABLE = false
IDENTITY_REMEDIATION_MODE = INSERT_MISSING_ONLY
NEW_TABLE_COUNT = 0
NEW_MIGRATION_COUNT = 0
DIRECT_SQL_WRITE_ALLOWED = false
```

`results` 不得修改、删除、重建或增加 competition/season 字段；不得新建平行 identity
表，也不得以名称、球队或时间作模糊匹配。

每条 Result 的唯一许可证据链是：

```text
result.fixture_id
result.source_payload_sha256
result.source_capture_id
→ raw_payload（raw_payloads authority 的当前物理表）
→ matchday_endpoint_captures（存在时）
→ raw fixtures response
→ league_profile / league_season
→ proposed MatchdayFixtureIdentityV1
```

- `raw_payload.sha256` 必须等于 `result.source_payload_sha256`，endpoint 必须为
  `fixtures`；response 中必须恰好一个 API-Football 数字 provider fixture ID 与
  `result.fixture_id` 精确一致。
- fixture status、fulltime 比分必须与 Result 一致；kickoff、league ID、season 和
  主客 provider team ID 必须完整。禁止 team name、league name 或近似时间匹配。
- 非空 `source_capture_id` 必须精确命中，且 capture 的 raw hash、endpoint、fixture ID
  全部一致。空 capture ID 可按 raw hash 查找：唯一 capture 使用、无 capture 可仅依赖
  精确 raw provenance、多个冲突 capture 必须 fail-closed。
- Competition/season 必须用 DB 全部 `league_profile` / `league_season` 权威行，按
  `provider + provider_league_id + provider_season` 精确唯一映射。缺失、歧义和
  capture/raw/mapping 冲突分别记为 `COMPETITION_SEASON_MAPPING_MISSING`、
  `COMPETITION_SEASON_MAPPING_AMBIGUOUS`、
  `COMPETITION_SEASON_PROVENANCE_CONFLICT`；不得从当前 enabled season 猜历史赛季。

拟生成身份只允许完全复用 `MatchdayFixtureIdentityV1`：

```text
fixture_id
provider
provider_fixture_id
competition_id
provider_league_id
season
kickoff_utc
fixture_status
home_provider_team_id
away_provider_team_id
home_w2_team_id
away_w2_team_id
team_identity_status
raw_payload_sha256
endpoint_capture_id
captured_at
payload
identity_hash
```

Provider team IDs 必须来自同一 raw fixture。W2 team IDs 仅可取 reviewed exact
authority；未完成 reviewed mapping 时保持空值并使用既有 fail-closed status。
`identity_hash` 必须复用 repository 既有 semantic hash，不新增 hash 版本或身份算法。

只读审计矩阵：

```text
RESULT_COUNT = 35
SOURCE_CAPTURE_ID_PRESENT = 0
RAW_PAYLOAD_EXACT = 0
RAW_FIXTURE_EXACT = 0
CAPTURE_EXACT = 0
REGISTRY_EXACT = 0
WOULD_INSERT = 0
ALREADY_EXACT = 0
BLOCKED_MISSING = 35
BLOCKED_AMBIGUOUS = 0
BLOCKED_CONFLICT = 0

BLOCKER_COUNT =
RAW_PAYLOAD_NOT_FOUND = 35
RAW_FIXTURE_PROVENANCE_MISSING = 35
COMPETITION_SEASON_MAPPING_MISSING = 35

DB_WRITE_DELTA = 0
PROVIDER_CALL_DELTA = 0
```

35 条 Result 的 source hash 均未精确命中现存 raw authority，因而无法继续建立
无歧义 raw fixture 与 competition/season 证据链；本轮不得产生拟写入身份。

**身份 provenance 缺口最终决策（已冻结）**：

```text
IDENTITY_PROVENANCE_GAP_DECISION =
LEGACY_35_RESULTS_EXCLUDED_FROM_EVAL_02B

LEGACY_RESULT_FACTS_RETAINED = true
LEGACY_RESULT_FACTS_MUTATED = false
LEGACY_RESULT_EVAL_ELIGIBILITY = false

LEGACY_IDENTITY_REMEDIATION_CLOSED = true
IDENTITY_REMEDIATION_EXECUTION_AUTHORIZED = false

FUTURE_ONLY_PAIR_COLLECTION_REQUIRED = true
NEXT_REQUIRED_ACTION = WRITE_SIDE_READINESS_DESIGN
```

35 条 `results` 继续保留为不可变历史比分事实，不删除、不修改，也不补造
competition/season；它们不参与 EVAL-02B 的 sample count、time split、bootstrap、
评分或门禁。`MINIMUM_ELIGIBLE_TOTAL_PAIRS = 120` 必须完全由未来合法数据满足。

禁止伪恢复：

```text
NEW_PROVIDER_FETCH_CAN_RESTORE_LEGACY_PROVENANCE = false
FUZZY_IDENTITY_RECONSTRUCTION_ALLOWED = false
TEAM_NAME_MATCH_ALLOWED = false
APPROXIMATE_TIME_MATCH_ALLOWED = false
MANUAL_COMPETITION_SEASON_GUESS_ALLOWED = false
```

不得重新调用 Provider 下载同一比赛后替换原 source hash，不得用新 payload 冒充旧
payload；不得根据球队名、联赛名、比分、日期或近似开球时间补建身份；不得修改 Result
的 source hash 或 capture ID，也不得通过 direct SQL 将旧结果强行接入 EVAL-02B。

唯一允许重新打开的条件：

```text
LEGACY_REMEDIATION_REOPEN_CONDITION =
EXACT_ORIGINAL_RAW_BLOB_RECOVERED

REQUIRED_BLOB_VERIFICATION =
SHA256(blob) == result.source_payload_sha256

REOPEN_SCOPE =
IDENTITY_REMEDIATION_ONLY
```

原始 blob 还必须来自 fixtures endpoint，且 provider fixture、比分和状态精确一致，
provenance chain 无歧义。满足时只重新打开身份修复子任务，不重新执行：

```text
EVAL-01A
EVAL-01B
EVAL-01C
EVAL-02A
EVAL-02B_PREREGISTRATION_CONTRACT
```

下一阶段 `WRITE_SIDE_READINESS_DESIGN` 仅审查和设计未来
`dynamic_prematch_evaluations`、`lineup_confirmed_events`、baseline/candidate
五态分布及 Pre/Post exact pairing identity 的写侧；本 PR 不授权代码实施。

```text
WRITE_SIDE_IMPLEMENTATION_AUTHORIZED = false
RUNTIME_COLLECTION_AUTHORIZED = false
PROVIDER_CALLS_AUTHORIZED = false
SCHEDULER_START_AUTHORIZED = false

SCORING_IMPLEMENTATION = BLOCKED
EVAL_02B_START_AUTHORIZED = false
EVAL_02B = BLOCKED
EVAL_03 = NOT_STARTED
```

**未来写侧就绪设计（已冻结，未授权实施）**：

现有能力矩阵：

```text
DYNAMIC_EVALUATION_TABLE = EXISTS
DYNAMIC_EVALUATION_APPEND_API = EXISTS
DYNAMIC_EVALUATION_TRANSACTIONAL_PROJECTION = EXISTS

LINEUP_CONFIRMED_EVENT_TABLE = EXISTS
LINEUP_CONFIRMED_EVENT_APPEND_API = EXISTS
LINEUP_CONFIRMED_EVENT_PRODUCTION_CALLER = MISSING

LINEUP_CHANGED_PROJECTION_EVENT = EXISTS
POST_LINEUP_REFRESH_PLAN_FACTORY = EXISTS
POST_LINEUP_REFRESH_PLAN_PRODUCTION_CALLER = MISSING

MODEL_FIVE_STATE_DISTRIBUTION_SOURCE = EXISTS
MODEL_FIVE_STATE_DISTRIBUTION_PERSISTED_IN_DYNAMIC_EVALUATION = MISSING

EXPLICIT_PROVIDER_IN_DYNAMIC_EVALUATION = MISSING
CANONICAL_LINEUP_HASH_SHARED_BY_EVENT_AND_EVALUATION = MISSING
EXACT_PRE_POST_PAIR_PROJECTOR = MISSING

NEW_PARALLEL_WRITE_PIPELINE = false
NEW_TABLE_COUNT = 0
NEW_MIGRATION_COUNT = 0
```

唯一方案是复用当前 production projection graph，不新建平行写侧。

唯一写入边界：

```text
DYNAMIC_WRITE_BOUNDARY =
write_frozen_analysis_artifacts

LINEUP_EVENT_AND_DYNAMIC_EVALUATION_UNIT_OF_WORK =
SAME_DATABASE_TRANSACTION

READ_MODEL_CHECKPOINT_AND_DYNAMIC_EVALUATION_UNIT_OF_WORK =
SAME_DATABASE_TRANSACTION
```

未来实施为 `DynamicPrematchRepository` 增加
`append_lineup_event_in_session()`，并在现有
`write_frozen_analysis_artifacts()` 事务内依次处理 canonical lineup event、dynamic
evaluation、supersession、shadow read-model checkpoint；任一步冲突必须整批 rollback。
API/read path 不得写数据库，future refresh 不得另建独立 evaluation writer；不得新增
第二个 event/outbox 表，也不得使用 direct SQL。

Canonical lineup identity：

```text
LINEUP_INPUT_HASH_AUTHORITY =
confirmed_lineup_business_identity

LINEUP_EVENT_LINEUP_INPUT_HASH =
confirmed_lineup_business_identity

POST_EVALUATION_LINEUP_INPUT_HASH =
confirmed_lineup_business_identity

CANONICAL_LINEUP_IDENTITY_FIELDS =
fixture_id
home_team_external_id
home_sorted_starter_ids
away_team_external_id
away_sorted_starter_ids

LINEUP_INPUT_HASH_EXCLUDED_FIELDS =
captured_at
raw_sha256
baseline_artifact_hashes
lineup_change_features
model_version
release_sha
```

排除字段属于 provenance 或 `model_input_hash`，不是首发业务身份。Lineup event 必须由
同一 fixture 最新两条 COMPLETE、confirmed snapshot 生成：主客各 11 名首发、22 个
球员 ID 唯一、两队 snapshot 属于同一 capture、capture 在开球前，且两个 per-team
lineup identity hash 完整；任一条件不满足均不写 event。

每场唯一 authoritative lineup event：

```text
AUTHORITATIVE_LINEUP_EVENT_POLICY =
FIRST_COMPLETE_CONFIRMED_LINEUP_IDENTITY

AUTHORITATIVE_EVENT_TIME =
EARLIEST_COMPLETE_CONFIRMED_CAPTURE_AT

ELIGIBLE_LINEUP_EVENT_COUNT_PER_FIXTURE = 1

SAME_FIXTURE_SAME_LINEUP_HASH_SAME_CAPTURE =
ZERO_WRITE_EXACT_REPLAY

SAME_FIXTURE_SAME_LINEUP_HASH_DIFFERENT_CAPTURE =
ZERO_WRITE_REOBSERVATION

REOBSERVATION_PRESERVES_ORIGINAL_EVENT_TIME = true
REOBSERVATION_PRESERVES_ORIGINAL_EVENT_PAYLOAD = true

SAME_FIXTURE_DIFFERENT_LINEUP_HASH =
LINEUP_CONFIRMATION_CONFLICT

LINEUP_CONFIRMATION_CONFLICT_EVAL_02B_ELIGIBLE = false
SECOND_ELIGIBLE_LINEUP_EVENT_ALLOWED = false
```

同一套 XI 后续再次被观测时，不创建新 event、不修改最早确认时间，也不视为冲突。
Reobservation 不作为新的 authoritative payload 参与下述 payload-conflict 比较。没有
新的预注册 correction policy 时，只要同一 fixture 在首次确认后出现不同
`lineup_input_hash`，该 fixture 整体不得产生 EVAL-02B pair。

Dynamic evaluation v2：

```text
DYNAMIC_EVALUATION_SCHEMA_VERSION =
w2.dynamic_quote_evaluation.v2

DYNAMIC_EVALUATION_V1_EVAL_02B_ELIGIBLE = false
DYNAMIC_EVALUATION_V2_SCHEMA_ELIGIBILITY =
NECESSARY_NOT_SUFFICIENT

EVAL_02B_EVALUATION_ROLES =
PRE_CONFIRMATION / POST_CONFIRMATION

PRE_CONFIRMATION_ELIGIBILITY =
schema_version == w2.dynamic_quote_evaluation.v2
capture_at < authoritative_lineup_event.captured_at
lineup_input_hash == null
exact_quote_identity_complete == true
model_settlement_distribution_valid == true
state_not_marker_or_not_ready == true
original_state in ANALYSIS_PICK_ACTIVE | NO_EDGE_CURRENT

POST_CONFIRMATION_ELIGIBILITY =
schema_version == w2.dynamic_quote_evaluation.v2
capture_at >= authoritative_lineup_event.captured_at
lineup_input_hash == authoritative_lineup_event.lineup_input_hash
post_lineup_quote == true
quote_fresh == true
exact_quote_identity_complete == true
model_settlement_distribution_valid == true
state_not_marker_or_not_ready == true
original_state in ANALYSIS_PICK_ACTIVE | NO_EDGE_CURRENT

PRE_LINEUP_INPUT_HASH_REQUIRED = false
POST_LINEUP_INPUT_HASH_REQUIRED = true

DYNAMIC_EVALUATION_V2_FIELDS =
fixture_id
competition_id
season
provider
market
selection
exact_line
bookmaker_id
capture_id
quote_identity_hash
model_input_hash
lineup_input_hash
checkpoint
evaluated_at
capture_at
model_settlement_distribution
state
blockers
```

v2 schema 本身只提供必要条件，不能自动赋予 EVAL-02B 资格。Pre 的
`lineup_input_hash` 必须为空；Post 的 hash 必须精确匹配 authoritative event。
NOT_READY、marker 和其他原始状态不合格的 evaluation 均不合格；lifecycle
supersession relation 只输出诊断信息，不改变 immutable original evaluation 的资格。

`competition_id / season` 来自既有 `matchday_fixture_identities`；
`provider / bookmaker_id / exact_line / capture_id` 来自 exact quote identity；
`model_settlement_distribution` 是 selected side 的
`model_probability.settlement_distribution`；`lineup_input_hash` 使用上述 canonical
lineup identity；`model_input_hash` 覆盖 simulation、analysis evidence、lineup
features 和版本输入。Provider、competition、season、exact line、bookmaker、capture
和五态分布必须全部参与 v2 identity hash。继续使用现有 JSON payload，不改数据库表。

五态分布写入合同：

```text
MODEL_SETTLEMENT_DISTRIBUTION_STATE_ORDER =
WIN
HALF_WIN
PUSH
HALF_LOSS
LOSS

BASELINE_DISTRIBUTION = PRE.model_settlement_distribution
CANDIDATE_DISTRIBUTION = POST.model_settlement_distribution

STATE_SET_EXACT = true
FINITE_AND_NON_NEGATIVE = true
ABS(SUM - 1) <= 1e-9
MISSING_OR_INVALID = FAIL_CLOSED
```

每条 Pre/Post evaluation 各保存一套五态模型分布，不得在一条 evaluation 同时保存
baseline 和 candidate。写侧可复用现有状态枚举，但不得直接使用
`complete_five_state_distribution()` 的 `1e-6` 容差；EVAL-02B 必须实现冻结的
`1e-9`。PUSH、HALF_WIN、HALF_LOSS 不得转换为二元概率。

Lineup event payload 与幂等：

```text
LINEUP_EVENT_V2_FIELDS =
fixture_id
competition_id
season
captured_at
checkpoint
lineup_input_hash
home_lineup_identity_hash
away_lineup_identity_hash
home_starters
away_starters
source_capture_id
raw_sha256

SAME_NATURAL_IDENTITY_AND_SAME_PAYLOAD = ZERO_WRITE
SAME_NATURAL_IDENTITY_AND_DIFFERENT_PAYLOAD = FAIL_CLOSED
```

现有 `append_lineup_event()` 对所有 `IntegrityError` 直接返回 `false`，无法区分幂等与
冲突；未来实现必须显式比较已存 payload。

首发后赔率刷新计划复用 `lineup_confirmed_refresh_plan()`、
`matchday_checkpoint_plans` 和 `MatchdayRuntimeRepository`，不得新建 scheduler 或
plan 表。Event 成功写入后必须幂等地产生：

```text
checkpoint = LINEUP_CONFIRMED
endpoint = odds
scheduled_at = lineup_event.captured_at
fixture_id = lineup_event.fixture_id

LINEUP_EVENT_WITHOUT_POST_LINEUP_ODDS_PLAN =
WRITE_SIDE_NOT_READY

PLAN_EXISTS_BUT_PROVIDER_NOT_ACTIVATED =
READY_FOR_ACTIVATION_REVIEW

SCHEDULER_START_AUTHORIZED = false
PROVIDER_CALLS_AUTHORIZED = false
```

Pre/Post 配对所需字段与 event 前置条件：

```text
PAIR_PROJECTOR_REQUIRES =
EXACTLY_ONE_AUTHORITATIVE_ELIGIBLE_LINEUP_EVENT

ZERO_AUTHORITATIVE_EVENTS =
BLOCKED_LINEUP_EVENT_MISSING

MULTIPLE_OR_CONFLICTING_EVENTS =
BLOCKED_LINEUP_EVENT_CONFLICT

PRE =
last eligible PRE_CONFIRMATION evaluation
before authoritative event

POST =
first eligible POST_CONFIRMATION evaluation
after authoritative event

PRE_POST_EXACT_MATCH_FIELDS =
fixture_id
competition_id
season
provider
bookmaker_id
market
selection
exact_line

PAIR_STORAGE_MODE = DERIVED_READ_MODEL
NEW_PAIR_TABLE_COUNT = 0
```

只有恰好一个 authoritative eligible lineup event 时才允许选择 Pre/Post；0 个或多个/
冲突 event 必须按上述 blocker fail-closed。每场 fixture 最多一个 pair。
不得跨 provider、bookmaker、line 或 selection 配对；pair identity 在后续 projector
中按已冻结 minimum fields 确定性计算，不新建 pair 表。

实施工作包与顺序：

```text
WRITE_SIDE_IMPLEMENTATION_01 =
CANONICAL_LINEUP_EVENT_AND_ATOMIC_WRITE

WRITE_SIDE_IMPLEMENTATION_02 =
DYNAMIC_EVALUATION_V2_AND_FIVE_STATE_SNAPSHOT

WRITE_SIDE_IMPLEMENTATION_03 =
POST_LINEUP_ODDS_PLAN_PRODUCER

WRITE_SIDE_IMPLEMENTATION_04 =
READ_ONLY_EXACT_PAIR_PROJECTOR

WRITE_SIDE_IMPLEMENTATION_ORDER =
01 -> 02 -> 03 -> 04
```

四个工作包必须分别通过独立、可回滚 PR；任何工作包均不得自动开启 Provider、
scheduler 或运行采集。Implementation 01 已由 PR #441 合并完成：

```text
WRITE_SIDE_IMPLEMENTATION_01 = DONE
WRITE_SIDE_IMPLEMENTATION_01_PR = 441
WRITE_SIDE_IMPLEMENTATION_01_MERGE_SHA =
5c52a40a6f0b3afb8589c251bea0b7ba611012f5
WRITE_SIDE_IMPLEMENTATION_01_MAIN_CI = 30583359805
LINEUP_EVENT_PRODUCTION_CALLER = IMPLEMENTED
CANONICAL_LINEUP_EVENT_ATOMIC_WRITE = IMPLEMENTED
```

Implementation 02–04 已按 stacked tranche 完成：

```text
WRITE_SIDE_READINESS_DESIGN = FROZEN
WRITE_SIDE_READY = true
WRITE_SIDE_IMPLEMENTATION_AUTHORIZED = false
WRITE_SIDE_EXECUTION_TRANCHE = COMPLETED

WRITE_SIDE_IMPLEMENTATION_02 = DONE
WRITE_SIDE_IMPLEMENTATION_02_PR = 443
WRITE_SIDE_IMPLEMENTATION_02_HEAD =
8eaf04699414a1ebe65077e419651f567910c45d
WRITE_SIDE_IMPLEMENTATION_02_MERGE_SHA =
532e58c44fe388d7053d8c0b3c3b7d5fa934cacb
WRITE_SIDE_IMPLEMENTATION_02_MAIN_CI = 30598884065

WRITE_SIDE_IMPLEMENTATION_03 = DONE
WRITE_SIDE_IMPLEMENTATION_03_PR = 444
WRITE_SIDE_IMPLEMENTATION_03_HEAD =
b959e4a3a406fcc9898695643a17fac9c069281f
WRITE_SIDE_IMPLEMENTATION_03_MERGE_SHA =
882f69650d4773757529999e3f8292e8689231a2
WRITE_SIDE_IMPLEMENTATION_03_MAIN_CI = 30599432182

WRITE_SIDE_IMPLEMENTATION_04 = DONE
WRITE_SIDE_IMPLEMENTATION_04_PR = 445
WRITE_SIDE_IMPLEMENTATION_04_HEAD =
05b55b5e1fc6583abbdee705a6b39bd263da4372
WRITE_SIDE_IMPLEMENTATION_04_MERGE_SHA =
308e1edc9ed1748a18cd64c9325521e54a5777ba
WRITE_SIDE_IMPLEMENTATION_04_MAIN_CI = 30599981432

DYNAMIC_EVALUATION_V2 = IMPLEMENTED
FIVE_STATE_SNAPSHOT = IMPLEMENTED
POST_LINEUP_REFRESH_PLAN_PRODUCTION_CALLER = IMPLEMENTED
EXACT_PAIR_PROJECTOR = IMPLEMENTED

PAIR_EVIDENCE_AUTHORITY =
IMMUTABLE_ORIGINAL_EVALUATION
LIFECYCLE_SUPERSESSION_EFFECT =
DIAGNOSTIC_ONLY
PRE_POST_ELIGIBILITY_REQUIRES_NOT_SUPERSEDED = false
FORWARD_COLLECTION_ACTIVATION_REVIEW = FROZEN
FORWARD_COLLECTION_ACTIVATION_READY = false
COMPOSE_FAIL_CLOSED_DEFAULTS = VERIFIED
PROVIDER_CODE_DEFAULT_FAIL_CLOSED = MISSING
RUNTIME_AUTHORITY_ENFORCEMENT = MISSING
BOUNDED_SUPERVISED_ONE_SHOT = MISSING
ACTIVATION_BLOCKER =
SUPERVISED_FORWARD_COLLECTION_GUARD_REQUIRED
FORWARD_COLLECTION_GUARD_IMPLEMENTATION_AUTHORIZED = true
SUPERVISED_ONE_SHOT_AUTHORIZED = false
PERSISTENT_SCHEDULER_AUTHORIZED = false
NEXT_REQUIRED_ACTION =
SUPERVISED_FORWARD_COLLECTION_GUARD_IMPLEMENTATION

LEGACY_RESULT_EVAL_ELIGIBILITY = false
RUNTIME_COLLECTION_AUTHORIZED = false
PROVIDER_CALLS_AUTHORIZED = false
SCHEDULER_START_AUTHORIZED = false
SCORING_IMPLEMENTATION = BLOCKED
EVAL_02B_START_AUTHORIZED = false
EVAL_02B = BLOCKED
EVAL_03 = NOT_STARTED
```

激活审查已冻结，但尚未达到激活条件。只授权 Guard 代码实施，不授权 Provider、
scheduler、`SUPERVISED_ONE_SHOT`、生产部署或运行采集；
EVAL-02B gate 与 EVAL-03 均不得启动。

**Forward collection 激活审查合同（已冻结，实施仍阻塞）**：

```text
FORWARD_COLLECTION_ACTIVATION_MODES =
OFF
PREFLIGHT
SUPERVISED_ONE_SHOT

DEFAULT_ACTIVATION_MODE = OFF
SCHEDULER_MODE_SUPPORTED = false

PREFLIGHT =
PROVIDER_CALLS = 0
BUSINESS_DB_WRITES = 0
CELERY_TASKS_QUEUED = 0
CHECKPOINT_CLAIMS = 0
```

`PREFLIGHT` 只能验证配置和输出预计调用，不得调用 Provider、写业务数据库、claim
checkpoint 或 queue Celery task。`SUPERVISED_ONE_SHOT` 只能前台单进程执行，不启动
scheduler、不通过 Celery，必须复用 `run_future_refresh_task()` 以及既有 Provider
ledger、quota、raw/capture、DB persistence 和 projection writer；执行后自动返回
`OFF`，且不得修改 compose 默认开关。

```text
schema_version =
w2.forward_collection_activation.v1

environment = staging
release_sha = exact 40-char merged SHA
mode = SUPERVISED_ONE_SHOT
competition_id = exactly one
phase =
DISCOVERY_ONLY | CHECKPOINT_CAPTURE
fixture_ids = zero or one
checkpoint_plan_ids = zero or one
allowed_endpoints = bounded subset
max_provider_calls = bounded positive integer
expires_at = timezone-aware future timestamp
activation_nonce = non-empty unique value
persistence = db
provider_request_ledger_required = true
candidate_enabled = false
formal_recommendation_enabled = false
production_release_enabled = false

DISCOVERY_ONLY_ALLOWED_ENDPOINTS =
status,fixtures
DISCOVERY_ONLY_MAX_PROVIDER_CALLS = 2

CHECKPOINT_CAPTURE_ALLOWED_ENDPOINTS =
status,fixtures,odds,lineups
CHECKPOINT_CAPTURE_MAX_FIXTURES = 1
CHECKPOINT_CAPTURE_MAX_PLANS = 1
CHECKPOINT_CAPTURE_MAX_PROVIDER_CALLS = 4

SUPERVISED_ONE_SHOT_HTTP_MAX_ATTEMPTS = 1
```

Manifest 禁止 fuzzy competition/fixture、默认 competition、无到期时间、未绑定 exact
Git SHA、phase allowlist 外 endpoint 或超过 phase cap 的调用上限；不得通过增加重试
突破 manifest 最大调用数。

```text
RUNTIME_GATES =
CLI_ADMISSION_GATE
FUTURE_REFRESH_SERVICE_GATE
API_FOOTBALL_CLIENT_REQUEST_GATE

ANY_GATE_FAILURE_PROVIDER_CALLS = 0
ANY_GATE_FAILURE_STATUS = BLOCKED

EFFECTIVE_SCOPE =
INTERSECTION_MANIFEST_SCOPE_EXISTING_POLICY_SCOPE

AUTO_RETRY = false
SCHEDULER_RESTART = false
ENDPOINT_WIDENING = false
CALL_CAP_WIDENING = false
```

三重运行门必须都在 Provider HTTP 前校验 activation context，不能只依赖 compose 或
操作人员记忆。Provider 调用发生后不可回滚，但必须保留 request ledger、raw payload、
endpoint capture、run audit、checkpoint audit 与 exact activation manifest hash。
DB persistence 或 projection 失败时必须立即停止，不自动重试，不启动 scheduler 或
EVAL-02B gate。

此前冻结的身份修复实施流程保持休眠；只有满足上述 exact original raw blob 重开条件后，
未来实施才必须默认 `dry-run`，先生成 canonical remediation manifest；每行状态只能是：

```text
WOULD_INSERT
ALREADY_EXACT
BLOCKED_MISSING
BLOCKED_AMBIGUOUS
BLOCKED_CONFLICT
```

写入前必须重新核验 DB snapshot 与 manifest hash。仅 `WOULD_INSERT` 且 exact unique
的缺失身份可交给
`MatchdayRuntimeRepository.upsert_fixture_identities_with_business_changes()`；
`ALREADY_EXACT` 必须零写，已存在但稳定字段不同必须整批 fail-closed。第二次执行必须
零写且 manifest hash 一致。

未来实施写入 receipt 至少包含：

```text
fixture_id
identity_hash
raw_payload_sha256
endpoint_capture_id
manifest_hash
preexisting
inserted_at
```

回滚只可删除 `preexisting = false`、fixture ID 与 identity hash 仍精确一致、且尚未启动
Phase 2、采集或其他下游写入的行。身份已变化或已被下游消费时，自动回滚必须
fail-closed。

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
