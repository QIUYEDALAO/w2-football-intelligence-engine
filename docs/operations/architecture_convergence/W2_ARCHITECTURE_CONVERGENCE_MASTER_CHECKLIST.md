# W2 架构收敛执行总清单与 Codex 工作指令

> 本文件依据老板最终审理决定制定。  
> Codex 执行任何代码修改前，必须先将本文件内容写入 GitHub 仓库：
>
> `docs/operations/architecture_convergence/W2_ARCHITECTURE_CONVERGENCE_MASTER_CHECKLIST.md`
>
> 后续所有架构收敛 PR 只更新这一份总清单，不再为每个小步骤重复创建大量日期型上下文文档。
>
> 第零节是**已完成任务清单与逐项变更记录**，供老板逐项验收；其后各节是总任务、
> 红线与执行顺序。两者同处本文件，不再分散到第二份文档。
>
> **只有完成代码审核、完整 CI、必要的 staging 验收并合并后，才允许把 `[ ]` 改为 `[x]`。**
> 本地完成、只提交报告、CI 尚未结束、部署尚未验证，都不能打勾。

---

## 零、已完成任务清单与逐项变更记录

> 本节是提交老板验收的入口。它回答"已经做了什么、依据是什么、怎么自行复核"；
> 后面各节回答"总任务是什么、还剩什么"。每完成一个任务在此追加一节，不新开
> 日期型文档（红线 13）。
>
> 复核方式：逐条读"改动"与"依据"，用附带的"复核命令"自行验证。所有命令都可
> 在仓库根目录直接执行，不依赖任何会话上下文。

### 0.1 全局进度速览

`main` 顶端 `748b50e5c990c6138193810ec319e0e413a7ab25`，migration head
`0041_converge_odds_history_and_projection`。

**staging 实际状态（ARCH-P1-02 验收后）**：release
`1d02a45c6f38c3613ac3dddab784869095bf6804`，migration current
`0041_converge_odds_history_and_projection`，**65 张表 + 1 个
`current_market_projection` 视图**，六个服务全部 healthy、restart count
全 0；`main` 与 staging 的 migration head 已一致。

| # | 任务 | PR | Merge SHA | 状态 | 详细记录 |
|---|---|---|---|---|---|
| 1 | ARCH-00 建立总清单 | #371 | `09ca14a9` | 已验收合并 | 见第七节 |
| 2 | ARCH-01 关闭 PR #370 | #374 | `160a6750` | 已验收合并 | 见该任务节 |
| 3 | ARCH-P0-01 删除 reports 文件读取 | #375 | `1e9e811d` | 已验收合并 | 见该任务节 |
| 4 | ARCH-P0-02 赔率读取路径收敛 | #376 | `dae21e59` | 已验收合并 | 见该任务节 |
| 5 | ARCH-P0-03 联赛白名单数据库化 | #377 | `7bd5088b` | 已验收合并 | 见该任务节 |
| 6 | ARCH-P0-04 P0 总验收 | #378 | `d62e3351` | 已验收合并 | 见该任务节 |
| 7 | ARCH-P1-01 僵尸表盘点与删除 | #379 | `76201af8` | 已验收合并 | 见该任务节 |
| 8 | 第 0 步 P1-01 收口 + 清单修订 | #380 | `8af05dd` | **已合并** | **0.2** |
| 9 | ARCH-P1-02 赔率表收敛 | #381 | `f53b073f` | **DONE / 已验收合并** | **0.3 / 0.4 / 0.5** |
| 10 | 架构清单顺序与合同修订 | #382 | `db3fd12f` | **已验收合并** | **0.6** |
| 11 | ARCH-HYGIENE-01 生成审计产物退出 Git | #383 | `748b50e5` | **DONE / 已验收合并** | **ARCH-HYGIENE-01** |

第 1–7 项由前序会话完成，其回执保留在各自任务节内，本节不重复。第 8、9 项
的详细变更依据见 0.2–0.5。

**当前执行**：ARCH-HYGIENE-02。后续顺序（见第三节）：ARCH-P1-04A →
04B → 04C → P1-03 → P1-05 → P1-06 → P1-07 → P1-08 →
P2-02 → P2-03 → P2-04 → P2-06 → P2-05。原 ARCH-P2-01 已由
ARCH-HYGIENE-02 取代，不再执行。

#### 本轮两项工作的性质对比

| | 第 0 步（#380） | ARCH-P1-02（#381） |
|---|---|---|
| 生产代码改动 | 无 | 有 |
| 数据库改动 | 无 | drop 1 表、建 1 视图（migration `0041`） |
| Dashboard 展示变化 | 无 | 有，**已获老板批准**，见 0.3 三节 |
| 安全开关 | 未动 | 未动 |
| 完整 CI | 全绿（run `30002502410`） | final exact-head `30017659192` 全绿 |
| staging 验收 | 不涉及 | **通过**，见 0.5 |
| 合并 | PR #380 已合并 | PR #381 已合并为 `f53b073f` |
| 可否回滚 | 可，revert 即可 | 可，revert + `0041 → 0040` |

---

### 0.2 第 0 步：ARCH-P1-01-CLOSE + 清单修订（PR #380，已合并 `8af05dd`）

**性质**：docs-only。零生产代码、零 schema、零配置、零开关变更。

#### 改动 0.1 ARCH-P1-01 收口

- **文件**：`docs/operations/architecture_convergence/W2_ARCHITECTURE_CONVERGENCE_MASTER_CHECKLIST.md`
- **改动**：`Status: READY_FOR_EXTERNAL_REVIEW` → `DONE`，补入 Merge SHA
  `76201af8aad43976ffbcd7d2f72726bac4bc8106`、PR `#379`、final head
  `a40342beadc820527a036df88ee5c29485ba3f36`、CI run `29994028200`、验收时间
  `2026-07-23T09:20:43Z`；最后一个未打勾项 `PR 合并` 改为 `[x]`。
- **依据**：PR #379 已在 GitHub 合并，上述值取自 GitHub API，非人工填写。
- **复核命令**：

  ```bash
  gh pr view 379 --json state,mergedAt,mergeCommit,headRefOid
  ```

#### 改动 0.2 固化原回执里的两处占位

- **改动**：原回执写"PR final receipt head 以 `refs/pull/379/head` 为准""final
  receipt CI 以最新 required checks 为准"，合并后已可确定，替换为实际值
  `a40342be` 与 run `29994028200`。
- **依据**：合并前无法自引用 commit SHA，合并后可回溯确定。
- **复核命令**：

  ```bash
  gh run list --commit a40342beadc820527a036df88ee5c29485ba3f36 --json databaseId,conclusion
  ```

#### 改动 0.3 记录老板批准的两项决定

- **改动**：总清单第一节新增"2026-07-23 老板批准的清单修订"，作为两项决定的
  唯一权威记录；第三节写入新的 P1 权威顺序。
- **内容**：① P1-04 拆为 04A/04B/04C，P1-03 后移至 04C 之后，新增 P1-07，
  P1-08 追加三条验收；② P1-05 条件提前开关（预批准，触发即可执行，无需再次
  请示，但必须记录触发原因）。
- **依据**：老板 2026-07-23 口头批准，本节即其落地。

#### 改动 0.4 P1 章节按新顺序重排

- **改动**：`ARCH-P1-04` 拆为三节（04A/04B/04C），`ARCH-P1-03` 物理移动到
  04C 之后，新增 `ARCH-P1-07` 一节，`ARCH-P1-08` 追加三条验收，`ARCH-P2-04`
  追加"回执压缩"一项。任务编号保留历史编号以便追溯。
- **复核命令**：

  ```bash
  grep -n "^## ARCH-P1-0" docs/operations/architecture_convergence/W2_ARCHITECTURE_CONVERGENCE_MASTER_CHECKLIST.md
  ```

  预期顺序：01 → 02 → 04(总述) → 04A → 04B → 04C → 03 → 05 → 06 → 07 → 08。

#### 改动 0.5 新增 drop migration 守卫要求

- **改动**：自 ARCH-P1-02 起，所有新 drop migration 的 `upgrade()` 必须先断言
  再删除，断言不成立即抛错。
- **依据**：`0038`/`0039`/`0040` 只有 `has_table` 守卫，在有数据的环境重放会
  无提示删数据。历史 revision 不追溯修改。

#### 改动 0.6 仓库上下文文本同步

三个文件此前仍描述已关闭的 PR #370 与"动态首发"阶段，与实际状态不符：

- `PROJECT_STATE.yaml`：`repository` 块从 PR #370 切到 `main@76201af` /
  migration `0040`；新增 `architecture_convergence` 块（已完成任务、P1 顺序、
  `next_task`、预批准顺序变更、表数 144→66）；`staging` 块更新到 P1-01 验收
  release；`release_invariants` 把 `PR_370_KEEP_DRAFT` 换为 `PR_370_CLOSED` +
  `FEATURE_DEVELOPMENT_FREEZE`。
- `NEXT_ACTION.md`：改为指向总清单，不再重复 SHA/CI/状态；点名下一任务与开工
  前固定动作；真实首发 canary 归入"延后的 ops 工作"。
- `PROJECT_LEDGER.md`：追加一条 2026-07-23 条目，记录 P0 验收、P1-01 结果、
  两项批准决定。
- **约束**：`current_phase` 的 `id/status/next_phase` 未动，因为
  `tests/contract/test_delivery_status_documentation.py` 会交叉校验它与
  `NEXT_ACTION.md` 的措辞；改动后该契约仍通过。
- **复核命令**：

  ```bash
  .venv/bin/python -m pytest tests/contract/test_delivery_status_documentation.py -q
  ```

---

### 0.3 ARCH-P1-02：赔率表收敛（PR #381）

**验收目标**：`CANONICAL_ODDS_HISTORY_AUTHORITY_COUNT = 1`、
`CURRENT_MARKET_PROJECTION_AUTHORITY_COUNT = 1`。

#### 一、事实核查（先于任何改动）

##### 1.1 legacy 表没有生产写入者

- **交接稿的说法**：`future_market_observation` 仍有写入者。
- **实际**：写方法 `FutureRefreshDbRepository.append_observations()` 全仓库
  只有测试调用。`src/w2/ingestion/future_refresh.py:1452` 的
  `ledger.append_observations(...)` 作用于文件版 `MarketObservationLedger`
  （JSONL），与 DB repository 同名但不是同一个类。DB 持久化分支
  `_persist_db()` 写的是 `matchday_market_observations`。
- **数据库佐证**：`pg_stat_user_tables` 上该表
  `n_tup_ins=3840`、`n_tup_upd=0`、`n_tup_del=0`，全部为历史写入。
- **结论**：本任务不是拆双写，而是删死路径 + 证明无独有数据 + drop。
  ARCH-P1-01 矩阵中该表"生产写=有"是把 ORM 写方法的存在当成了可达写路径，
  已在总清单锚点中更正。

##### 1.2 3840 行 legacy 数据无独有价值

staging 只读对账（release `d004cd94`，migration `0040`，66 表）：

| 指标 | 值 |
|---|---|
| legacy 行数 | 3840 |
| 去重后业务元组 | 1920 |
| 重复形态 | 1920 条 bare + 1920 条 `api_football:` 前缀 |
| 完整 quote identity 命中 | 3840 / 3840 |
| raw payload sha 命中 | 3840 / 3840 |
| 每元组命中 canonical 行数 | 恰好 1 |
| legacy 归一化 hash | `f3790cd3162df8e6895b7cdc86408ab7` |
| canonical 同范围 hash | `f3790cd3162df8e6895b7cdc86408ab7` |

- **结论**：不需要搬运任何业务数据，drop 不删除独有历史，符合红线 7。

#### 二、数据库改动

##### 2.1 新增 migration `0041_converge_odds_history_and_projection`

- **文件**：`migrations/versions/0041_converge_odds_history_and_projection.py`（新增）
- **upgrade 行为**：
  1. 若 canonical 表不存在 → 抛 `ODDS_CONVERGENCE_CANONICAL_TABLE_MISSING`；
  2. 统计 legacy 表中**未被 canonical 按完整 quote identity + raw payload
     hash 覆盖**的行，非零 → 抛 `ODDS_CONVERGENCE_UNCOVERED_LEGACY_ROWS`
     并终止，不删除任何数据；
  3. drop `future_market_observation`；
  4. 建 `current_market_projection` 视图。
- **downgrade 行为**：删视图，重建 legacy 表结构与两个索引（空表）。1920 条
  报价全程留在 canonical 表中，不存在"只能靠回滚找回"的数据。
- **守卫为何不是"空表断言"**：本表非空但为完全重复，按总清单
  `DROP_MIGRATION_GUARD_KINDS = EMPTY_TABLE | FULLY_COVERED_DUPLICATE`
  的第二种。覆盖判定使用完整业务身份，不是只比主键。
- **复核命令**（守卫确实会拦住）：

  ```bash
  .venv/bin/python -m pytest tests/integration/test_migrations.py -q
  ```

  往返复核：

  ```bash
  W2_DATABASE_URL="sqlite+pysqlite:////tmp/w2check.db" .venv/bin/python -m alembic upgrade head
  W2_DATABASE_URL="sqlite+pysqlite:////tmp/w2check.db" .venv/bin/python -m alembic downgrade 0040_drop_empty_fk_components
  W2_DATABASE_URL="sqlite+pysqlite:////tmp/w2check.db" .venv/bin/python -m alembic upgrade head
  ```

##### 2.2 `current_market_projection` 视图

- **文件**：`src/w2/infrastructure/persistence/market_projection_view.py`（新增）
- **是什么**：canonical 历史表之上的**视图**，不是第二张事实表，因此不可能与
  历史漂移。保留每个
  `(fixture, market, bookmaker, selection, line)` 上最新的、未挂起、非滚球的
  报价。
- **为什么是视图**：总清单要求"一张当前盘口投影（表或视图）"，红线 4 禁止新增
  竞争性事实表。
- **建立时机**：真实数据库由 migration 建立；测试用的 `create_all` schema 由
  `Base.metadata` 的 `after_create` 事件建立——两边读同一个对象，测试不会退化
  成读空表。
- **不挂在 `Base.metadata` 上**：否则 `create_all` 会把它建成 TABLE。
- **复核命令**：

  ```bash
  .venv/bin/python -m pytest tests/contract/test_production_odds_reads.py -q
  ```

#### 三、读路径改动

##### 3.1 两条读路径都改读视图

- **文件**：`src/w2/ingestion/future_refresh_repository.py`
- **改动**：`_canonical_market_observations_for_fixtures()` 不再把全部历史行
  拉进内存做 latest-per-key 去重，改为 `select` 视图。新增
  `_projection_observations()` 与 `_projection_row_dict()`；删除内存去重循环与
  `_matchday_observation_dict()`。
- **语义对账**（staging 全量）：

  | | 旧内存投影 | 视图 |
  |---|---|---|
  | 行数 | 10648 | 10648 |
  | hash | `056069e2ab386b5deae451239f917fb0` | `056069e2ab386b5deae451239f917fb0` |

- **结论**：无界读路径逐行一致，零语义差异。

##### 3.2 有界读路径的确定性排序（**经老板批准的展示变化**）

- **问题**：有界读在每个 `(fixture, market)` 上截断到
  `SCOPED_OBSERVATION_ROWS_PER_MARKET = 128` 行，但截断前排序键只到
  `canonical_selection`，**不含 `line`**。仅 `line` 不同的行之间没有 tie-break，
  旧实现落到 Python dict 插入顺序，即数据库返回行的任意顺序。
- **后果**：staging 上 45 个 fixture/market 组超过 128 行，涉及 24 场比赛。
  也就是说**改动前**，两次相同请求即可合法返回不同的 128 条报价。这是既有
  缺陷，非本任务引入；因此不存在"忠实复现旧顺序"的选项。
- **决定**：老板 2026-07-23 选定候选 A——排序键补全为

  ```text
  projection_fixture_id, canonical_market, bookmaker_id,
  canonical_selection, line, observation_id
  ```

  128 行上限不变。
- **影响面**（staging 实测）：

  | 指标 | 值 |
  |---|---|
  | 进入范围的投影行 | 9649 |
  | 上限后保留 | 7812 |
  | 被上限截掉 | 1837 |
  | 受影响 fixture/market 组 | 45 |
  | 受影响比赛 | 24 |
  | 保留集 hash | `64b9fca07f19c75c9e3d670cda22c399` |

- **收益**：截断结果自此可复现，同一份数据重复请求必然返回同一组。
- **回归测试**：`test_bounded_projection_read_has_a_total_deterministic_order`
  钉住该顺序。

#### 四、删除清单（每处附零引用依据）

| 删除对象 | 文件 | 零引用依据 |
|---|---|---|
| `FutureMarketObservationModel` | `src/w2/infrastructure/persistence/future_refresh_models.py` | 表已 drop；删除后全仓库无引用 |
| 该模型的导出 | `src/w2/infrastructure/persistence/__init__.py` | 同上 |
| `append_observations()` | `src/w2/ingestion/future_refresh_repository.py` | 生产调用方 0，仅测试调用 |
| `_observation_model()` / `_observation_dict()` | 同上 | 仅被 `append_observations` 使用 |
| `_latest_observation_dicts()` | 同上 | 全仓库无调用方 |
| `_matchday_observation_dict()` | 同上 | 内存投影删除后无调用方 |
| `scripts/clean_w2_legacy_ah_pool.py` | 整文件删除 | 唯一数据源是被 drop 的表，表没了脚本无法运行 |
| 该脚本的镜像打包与存在性断言 | `Dockerfile.api`、`tests/contract/test_runtime_packaging.py` | 脚本已删除 |
| 6 个 legacy 专用测试 | `tests/integration/test_future_refresh_db_persistence.py`、`tests/unit/test_legacy_ah_pool_cleanup.py` | 断言对象已不存在；覆盖由新静态守卫接管（更强：表根本不能存在） |
| 断言 legacy 表存在 | `tests/integration/test_migrations.py`、`tests/integration/test_stage10a_persistence.py` | 改为断言其**不存在** |
| 直接查 legacy 表的行数检查 | `scripts/run_predeploy_e2e_smoke.sh` | 表已 drop，改为断言"表不存在 + 投影视图存在" |
| legacy 表列为 P0/P1 权威域 | `scripts/audit_w2_runtime_authorities.py` | 改为 `matchday_market_observations`；删除其"Phase B 后的迁移目标"占位 |

#### 五、新增防回归

| 测试 | 断言 | 文件 |
|---|---|---|
| `test_legacy_odds_table_is_fully_removed` | `src/w2` 与 `apps` 下任何模块再引用被删表即失败；模型不在 `Base.metadata` | `tests/contract/test_production_odds_reads.py` |
| `test_current_market_projection_is_a_view_over_the_canonical_history` | 投影是 view，不是 table，不在 `Base.metadata` | 同上 |
| `test_bounded_projection_read_has_a_total_deterministic_order` | 重复读取返回完全相同的顺序 | 同上 |

守卫扫描范围为 `src/w2`、`apps`、`scripts`、`infra` 下的
`.py/.sh/.sql/.yml/.yaml`，按**行**判定，放行"断言该表不存在"的行。

**该守卫是被 CI 反教出来的**：首版只扫 `src/w2` 与 `apps`，遗漏了
`scripts/run_predeploy_e2e_smoke.sh` 里直接 `select count(*) from
future_market_observation`，本地测试全过、CI 的 `predeploy-e2e` 才报
`relation "future_market_observation" does not exist`（run `30005506955`）。
扩大范围后同类遗漏会在本地即被拦下。

#### 六、本地验证结果

```text
ruff        PASS
mypy        PASS (260 files)
pytest      1445 passed, 4 skipped
alembic     0041 -> 0040 -> 0041 往返 PASS (SQLite)
bash -n     scripts/run_predeploy_e2e_smoke.sh PASS
```

CI 历史：run `30005506955` 的 `verify` 与 `staging-parity` 通过、
`predeploy-e2e` 失败（原因见五节）；修复后重跑。

唯一失败项 `tests/regression/test_guards.py::test_secret_patterns_are_guarded`
在**未改动的树上同样失败**（已用 `git stash` 验证），原因是本地
`.learnings/` 目录触发 secret scan，该目录不在仓库中也不存在于 CI。

#### 七、红线自查

| 红线 | 本任务 |
|---|---|
| 不新增表 | 未新增。投影是视图 |
| 不新增竞争性配置或 fallback | 未新增。反而删掉了第二套投影实现 |
| 不动模型权重/门槛/安全开关 | 未动 |
| 不开放 Formal/Lock/Production | 未动 |
| drop 前证明零读零写零依赖 | 见一、二节 |
| 历史业务数据不删除 | 3840 行经证明为完全重复，1920 条报价留在 canonical |
| 一个 PR 只解决一个任务 | 是 |
| 不以本地测试代替 CI/staging | CI 与 staging 验收另行记录于总清单 |

#### 八、完成状态

**当前状态：ARCH-P1-02 已通过最终验收并合并。**

- [x] 分支推送到 GitHub（`4195e63`，单提交，已摘除两个误提交文件，见九节）
- [x] 整改前完整 CI 全绿：run `30008088208`，`verify`、`staging-parity`、
      `predeploy-e2e` 三项均 `success`
- [x] 0.4 三项代码整改的完整 CI 全绿：run `30011185720` @ `4f137d2`，
      `verify`、`staging-parity`、`predeploy-e2e` 三项均 `success`
      （已核对 run `conclusion` 字段，非仅监听命令退出码）
- [x] staging 验收通过：部署 exact head `1d02a45` → migration 至 `0041` →
      20 轮只读探测 80/80 → 零写证明 → 表数 `66 → 65` → `0041→0040→0041`
      往返通过。完整回执见 0.5
- [x] exact-head CI：run `30011857074` @ `1d02a45`，`success`
- [x] 最终回执提交的完整 CI 全绿：run `30016906612` @ `db55523`，
      `verify`、`staging-parity`、`predeploy-e2e` 三项均 `success`
- [x] final exact-head CI 全绿：run `30017659192` @
      `47c7ef7da368fa54b4643e56c0efdeb2990f23f5`
- [x] 外部审核对 0.3、0.4、0.5 逐项最终验收通过
- [x] PR #381 合并：merge SHA
      `f53b073f5f53e078d75831ad4f2c0c648f32db88`，本任务状态为 `DONE`

#### 九、本轮执行方的自查与更正

以下三项由执行方主动交代，供验收时一并核对：

1. **CI 状态曾被误报。** 执行方一度报告"CI 全绿"，实际 run `30005506955` 的
   conclusion 是 `failure`：`verify` 与 `staging-parity` 通过、`predeploy-e2e`
   失败。原因是只看了监听命令的退出码、未核对 run conclusion。
2. **静态守卫覆盖面不足导致漏删。** 首版守卫只扫 `src/w2` 与 `apps`，遗漏
   `scripts/run_predeploy_e2e_smoke.sh` 中直接查被删表的语句，本地全过而 CI
   报 `relation "future_market_observation" does not exist`。已扩大扫描范围
   （见五节），并把冒烟脚本改为断言"表不存在 + 投影视图存在"。
3. **两个不应提交的文件曾被带入分支。** `ARCH_EXECUTION_HANDOFF.md`（交接单
   明写不提交）与 `docs/expert_reviews/W2_SYSTEM_STATE_AND_REFACTOR_REVIEW_2026-07-19.md`
   （红线 13 的日期型证据文档）因 `git add -A` 被提交。已重做分支摘除，两者
   保持未跟踪。另有 50 个 `docs/audits/system_truth/*` 产物因运行 audit 脚本
   被重新生成，已 revert，未进入提交。

**复核命令**：

```bash
git ls-tree --name-only HEAD ARCH_EXECUTION_HANDOFF.md
git ls-tree -r --name-only HEAD docs/audits/system_truth/ | head
git log --oneline main..HEAD
```

---

### 0.4 ARCH-P1-02 对 GitHub 二次验收意见的整改

本节保留合并前某轮外部验收与整改过程；最终完成状态以 0.3 八节及 0.5 为准。
当时的外部验收结论：`ARCH-P1-02_CODE_DIRECTION_PASS`、
`ARCH-P1-02_CI_PASS`，但
`DROP_GUARD_REMEDIATION_REQUIRED`、
`PROJECTION_PROVIDER_IDENTITY_REMEDIATION_REQUIRED`、
`STAGING_ACCEPTANCE_PENDING`、`CHECKLIST_SYNC_PENDING`、`DO_NOT_MERGE`。

执行方逐条复核后确认**五条意见全部成立，无一误判**。整改如下。

#### 整改一：0041 删除守卫扩展为完整共同语义

- **原问题**：守卫只比较 8 个字段（fixture、bookmaker_id、market、selection、
  line、odds、captured_at、raw_payload_sha256）。价格身份相同但
  `provider_bet_id` 或 `raw_market_label` 不同的行会被误判为已覆盖并删除。
- **整改**：比较字段扩展为两表**全部 15 个共同业务字段**：

  ```text
  provider, fixture_id, bookmaker_id, bookmaker_name, provider_bet_id,
  raw_market_label, canonical_market, selection, line, decimal_odds,
  suspended, live, provider_last_update(=provider_updated_at),
  captured_at, raw_payload_sha256
  ```

  有意排除并在迁移中写明理由（常量 `EXCLUDED_SEMANTIC_FIELDS`）：
  `ingested_at`（本地写入时间，不属于报价）、`source_revision`（执行写入的
  代码版本）。
- **新增前置断言**：`candidate` 或 `formal_recommendation` 为真的行抛
  `ODDS_CONVERGENCE_FLAGGED_LEGACY_ROWS`。这类行带决策含义，canonical 表
  不建模，任何情况下都不得当作重复删除。该断言在覆盖检查**之前**执行。
- **staging 数据实测**（只读，整改后口径）：

  ```text
  UNCOVERED_UNDER_EXTENDED_SEMANTICS = 0
  LEGACY_CANDIDATE_TRUE              = 0
  LEGACY_FORMAL_TRUE                 = 0
  ```

  即加严后迁移在真实数据上仍可通过，不会卡死。

#### 整改二：补齐守卫的自动化回归测试

- **原问题**：总清单声称 `pytest tests/integration/test_migrations.py` 可证明
  守卫生效，但该文件的实际 diff 只把"表应存在"改成了"表不应存在"，并未新增
  守卫测试。执行方当时只做了一次性人工验证就写入文档，**这是不合格的**。
- **整改**：新增 **11 个**自动化测试（验收意见要求 4 个），全部在
  `tests/integration/test_migrations.py`：

  | 测试 | 断言 |
  |---|---|
  | legacy 报价完全无 canonical 对应 | upgrade 失败，`UNCOVERED`，表仍在，视图未创建 |
  | 价格身份相同但共同语义字段不同（7 例参数化：`provider_bet_id`、`raw_market_label`、`bookmaker_name`、`provider`、`provider_last_update`、`suspended`、`live`） | 每例 upgrade 失败，`UNCOVERED`，表仍在 |
  | `candidate = true` | upgrade 失败，`FLAGGED`，表仍在 |
  | `formal_recommendation = true` | upgrade 失败，`FLAGGED`，表仍在 |
  | 全部行完整覆盖 | upgrade 成功，表被删，投影为 VIEW 而非 TABLE |

  **表述更正**：本节初稿写"失败用例同时断言视图未被部分替换"，属过度表述——
  当时只有 1 个用例查了视图，其余 10 个只查了表。已抽出统一断言
  `_assert_migration_left_database_untouched()`，现在**全部 10 个失败用例**
  都同时断言三件事：legacy 表仍存在、投影视图不存在、投影也未被建成表。
  该表述自此与代码一致。

#### 整改三：投影视图的 Provider 命名空间隔离

- **原问题**：视图分区为
  `(projection_fixture_id, canonical_market, bookmaker_id, canonical_selection, line)`，
  其中 `projection_fixture_id` 是裸 provider fixture id。两个 Provider 若复用
  相同数字 fixture/bookmaker id，两条报价会落入同一分区，其中一条被覆盖丢失。
- **整改**：分区身份改为**带 Provider 命名空间**：

  ```text
  provider, fixture_id(canonical 带命名空间), canonical_market,
  bookmaker_id, canonical_selection, line
  ```

- **同类问题的第二处（验收意见未提，执行方一并修复）**：有界读的 128 行
  截断此前按裸 fixture id 分组，两个 Provider 撞号会互相挤占同一配额。已改为
  按 `(provider, fixture_id, canonical_market)` 分组；投影读取排序也以
  `provider` 为首键。
- **staging 数据实测**（只读）：新旧分区在现有数据上结果完全一致，属纯加固、
  不改变现有行为：

  ```text
  OLD_PARTITION_ROWS = 10648    NEW_PARTITION_ROWS = 10648
  OLD_PARTITION_HASH = 3bf130fc8209be2ac990c3cd212d7622
  NEW_PARTITION_HASH = 3bf130fc8209be2ac990c3cd212d7622
  CANONICAL_FIXTURE_ID_ALL_NAMESPACED = 44644 / 44644
  DISTINCT_PROVIDERS_IN_CANONICAL     = 1
  ```

- **新增双 Provider 回归测试**
  `test_projection_keeps_two_providers_that_reuse_the_same_numeric_ids`：两个
  Provider 复用同一数字 fixture/bookmaker id 时，投影必须保留两条报价。
- **如实说明一处边界**：该测试中有界读只返回一个 Provider 的报价。原因是
  `latest_market_observations_for_fixtures(["123"])` 的**既有调用契约**把裸
  fixture id 固定解析到 `api_football:` 命名空间，这是调用侧的既有收窄，不是
  投影层的行丢失——视图本身两条都保留。测试断言如实描述该行为，未包装成
  "两个都返回"。若需放开该契约，属独立任务。

#### 整改四：staging 验收（当时待执行，后已通过）

本轮整改记录形成时尚未执行；随后已按要求执行并通过，完整结果见 0.5。验收
覆盖：部署 SHA =
PR exact head、migration current = `0041`、legacy 表不存在、投影对象类型为
`VIEW`、表数 `66 → 65`、legacy 3840 行完整共同语义覆盖、canonical 44644 行
无丢失、旧/新投影行数与 hash 对账、20 轮真实 HTTP 全 200 且结果 hash 稳定、
Provider calls 增量 0、DML 增量 0、recommendation/lock/settlement 全 0、
`0041 → 0040 → 0041` 往返通过。

#### 整改五：总清单同步

整改当时已同步：0.1 状态改为"外部验收不通过，整改中"；八节勾选"分支已推送"与
"整改前完整 CI 全绿 run `30008088208`"；staging 项按要求保持未勾选，待真实
验收后再勾。

#### 整改状态

```text
GUARD_SEMANTIC_COMPLETENESS      = FIXED
GUARD_REGRESSION_TESTS           = FIXED (11 tests)
PROJECTION_PROVIDER_NAMESPACE    = FIXED (view + bounded read grouping)
CHECKLIST_SYNC                   = FIXED
POST_REMEDIATION_CI              = PASS (run 30011185720 @ 4f137d2)
EXACT_HEAD_CI                    = PASS (run 30011857074 @ 1d02a45)
STAGING_ACCEPTANCE               = PASS (见 0.5)
```

---

### 0.5 ARCH-P1-02 真实 staging 验收回执

老板 2026-07-23 授权在 exact head `1d02a45c6f38c3613ac3dddab784869095bf6804`
上执行真实 staging 验收。全部项目通过。

#### 验收环境

```text
STAGING_HOST            = 118.196.30.136
DEPLOYED_RELEASE        = 1d02a45c6f38c3613ac3dddab784869095bf6804
RELEASE_ENV_W2_GIT_SHA  = 1d02a45c6f38c3613ac3dddab784869095bf6804
API_CONTAINER_W2_GIT_SHA= 1d02a45c6f38c3613ac3dddab784869095bf6804
EXACT_HEAD_CI           = 30011857074 (success)
PREVIOUS_RELEASE        = d004cd946a42ad2fade0799d297ca31358c2f41e
```

三处 release 标识（symlink、`release.env`、API 容器内环境变量）一致，证明
运行中的服务确实是 exact head，而非仅仅切了 symlink。

#### 逐项结果

| 验收项 | 期望 | 实测 | 结果 |
|---|---|---|---|
| migration current | `0041` | `0041_converge_odds_history_and_projection` | 通过 |
| staging 表数 | `66 → 65` | 基线 66 → 验收后 65 | 通过 |
| 视图数 | 1 | 1 | 通过 |
| `future_market_observation` | 不存在 | `information_schema` 命中 0 | 通过 |
| `current_market_projection` | `VIEW` 非 `TABLE` | `table_type = VIEW` | 通过 |
| canonical 行数 | 44644 不减少 | 44644（基线与验收后一致） | 通过 |
| legacy 扩展语义覆盖 | 0 uncovered / 0 flagged | 迁移前实测 0 / 0；迁移守卫放行 | 通过 |
| 投影行数 | 10648 | 10648 | 通过 |
| 投影 hash | `3bf130fc8209be2ac990c3cd212d7622` | 同值 | 通过 |
| 20 轮真实 HTTP | 全 200、hash 稳定 | 80/80 = 200，distinct hash = 1，`4b8f7f24…` | 通过 |
| Provider calls | 增量 0 | `provider_request_logs` 162 → 162 | 通过 |
| DML | 增量 0 | 见下方说明 | 通过 |
| recommendation / lock / settlement / gate5 | 全 0 | 全 0 | 通过 |
| `0041 → 0040 → 0041` | 往返通过 | 通过，中间态 66 表 / 0 视图 / legacy 表恢复 | 通过 |
| 服务健康 | 全 healthy | 6/6 healthy，restart count 全 0 | 通过 |
| 安全开关 | 不变 | provider_calls_disabled=true，scheduler/recommendation/formal/production 全 false | 通过 |

#### DML 口径说明（重要，避免误读）

`pg_stat_user_tables` 聚合值从基线 `58159/390/0` 变为 `54319/393/0`，
**insert 看起来减少了 3840**。这不是删数据：

- `-3840` 恰等于被 drop 的 legacy 表行数——该表的每表计数器随表一起消失，
  从聚合中扣除；
- `+3` 次 update 全部来自 `alembic_version` 的版本戳（upgrade / downgrade /
  再 upgrade 各一次）；
- **`n_tup_del` 全库始终为 0**，逐表核查 `tables_with_any_delete = none`，
  证明没有任何一行业务数据被删除；
- 排除 `alembic_version` 后的业务表计数为 `54318/345/0`，与基线业务口径一致。

#### 20 轮 HTTP 的口径说明

首轮探测发现 cycle hash 不稳定，逐字段 diff 后确认**唯一差异是 `request_id`**
（每次请求生成的 UUID），业务内容完全一致。剔除该字段后重测，20 轮 distinct
hash = 1。探测前后 DML 均为 `54319/393/0`，80 次读取零写入。

#### 执行过程中发现并纠正的一处问题

首次 `systemctl start` 对已在运行的服务是空操作，容器仍跑着上一版本
`d004cd94`（容器内不存在 `market_projection_view.py`）。当时那轮 HTTP 探测
实际验证的是**旧代码 + 新库结构**，不构成本任务的验收证据。已改用
`systemctl restart` 重建容器，确认 API 容器内 `W2_GIT_SHA` 为 `1d02a45` 后
重跑全部 HTTP 验收。上表记录的是重跑后的结果。

（附带旁证：旧代码在 legacy 表已删、视图已建的库上仍全部返回 200，说明本次
schema 变更对上一版本向后兼容。此项不作为验收依据。）

#### 最终结果

```text
FINAL_EXACT_HEAD_CI   = PASS (run 30017659192 @ 47c7ef7)
EXTERNAL_FINAL_REVIEW = PASS
MERGE                 = PASS (f53b073f5f53e078d75831ad4f2c0c648f32db88)
```

本回执提交只改动文档与测试断言，**不含任何生产代码改动**——生产代码与
staging 已验收的 `1d02a45` 完全一致，可用
`git diff 1d02a45 <head> -- src/ apps/ migrations/` 复核为空。

---

### 0.6 架构清单顺序与合同修订（PR #382，已合并 `db3fd12f`）

**性质**：docs-only。零生产代码、零 schema、零配置、零开关变更。

- final head：`6b9b496bd8867a060a621175f72da1d5e06e337e`
- final exact-head CI：run `30030832487`，`verify`、`staging-parity`、
  `predeploy-e2e` 全部 PASS
- merge SHA：`db3fd12fedb76e9a9cb074f7a3dcc3294042c2fc`
- 合并时间：`2026-07-23T18:08:22Z`
- 结果：正式插入 `ARCH-HYGIENE-01/02`，固化
  `DEPENDENCY_CONTRACT_V1` 与审计 SHA 语义，授权从该 merge SHA 开始
  `ARCH-HYGIENE-01`。

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

### 2026-07-23 老板批准的清单修订（P1 阶段）

ARCH-P1-01 合并后，基于对 `main@76201af8aad43976ffbcd7d2f72726bac4bc8106`
的系统状态复审，老板批准以下两项决定。本节是这两项决定的唯一权威记录。

**决定一：P1 任务拆分与顺序调整（已生效）**

```text
ARCH_P1_04_SPLIT = 04A_WRITE_PIPELINE / 04B_READ_SWITCH / 04C_CONTRACT_CLEANUP
ARCH_P1_03_MOVED_AFTER = ARCH-P1-04C
ARCH_P1_07_ADDED = COMPETITION_READ_PATH_IMPORT_TIME_FIX
ARCH_P1_08_ACCEPTANCE_ADDED = 3
```

- `ARCH-P1-04` 拆为 04A（评估持久化写侧管线）、04B（Dashboard 读切换并删除
  全部生产 fallback）、04C（合同层与死代码清理）。拆分理由：04B 是行为切换，
  需要 staging 语义对账；04C 是删除，需要零引用证据；两者回滚粒度不同，
  按红线第 6 条必须可独立回滚。
- `ARCH-P1-03` 移到 04 系列之后。理由：身份收敛的对账口径依赖 04A 建立的
  投影链路；先做投影可让身份不一致以可观测的方式暴露。
- 新增 `ARCH-P1-07`（竞赛域读路径 import-time 副作用修正），小任务。
- `ARCH-P1-08` 追加三条验收，见该任务。

新执行顺序：

```text
ARCH-P1-01 (DONE) -> ARCH-P1-02 (DONE)
  -> ARCH-HYGIENE-01 -> ARCH-HYGIENE-02
  -> ARCH-P1-04A -> ARCH-P1-04B -> ARCH-P1-04C
  -> ARCH-P1-03 -> ARCH-P1-05 -> ARCH-P1-06
  -> ARCH-P1-07 -> ARCH-P1-08 -> P2-02...P2-06
```

`ARCH-HYGIENE-01` 与 `ARCH-HYGIENE-02` 是 P1-02 之后、P1-04A 之前的正式
前置任务。原 `ARCH-P2-01` 的 scripts/archive 方案已由
`ARCH-HYGIENE-02` 取代，不再执行。

**决定二：ARCH-P1-05 条件提前开关（已批准，触发后无需再次请示）**

```text
ARCH_P1_05_EARLY_TRIGGER = STAGING_ONSITE_BUILD_REPEATEDLY_FAILS
ARCH_P1_05_EARLY_POSITION = BEFORE_ARCH_P1_04A
ARCH_P1_05_EARLY_APPROVAL = PRE_APPROVED_2026_07_23
```

若 ARCH-P1-04 系列的 staging 验收因服务器现场构建（网络或软件源不稳定）
反复失败，执行方可直接把 ARCH-P1-05 提到 ARCH-P1-04A 之前执行，无需再次
请示；提前执行时必须在 ARCH-P1-05 任务下记录触发原因和触发时间。这是本
清单中唯一的预批准顺序变更。

**唯一允许的顺序回退**

若执行 ARCH-P1-04A 时发现球队/球员身份不一致阻塞投影对账，可向老板申请把
`ARCH-P1-03` 提前。此项需要单独批准，不属于预批准范围。

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

P1 阶段的顺序已按第一节"2026-07-23 老板批准的清单修订"调整，当前权威顺序为：

```text
ARCH-P1-01 (DONE)
ARCH-P1-02 (DONE)  赔率表收敛
ARCH-HYGIENE-01    生成审计产物退出 Git
ARCH-HYGIENE-02    Scripts 权威盘点与证据化直接删除
ARCH-P1-04A  评估持久化——写侧管线
ARCH-P1-04B  Dashboard 读切换 + 删除全部生产 fallback
ARCH-P1-04C  合同层与死代码清理
ARCH-P1-03   球队身份 Crosswalk 收敛
ARCH-P1-05   CI 构建镜像、服务器 pull-only（有预批准的条件提前开关）
ARCH-P1-06   Compose 环境变量去重
ARCH-P1-07   竞赛域读路径修正
ARCH-P1-08   P1 总验收
ARCH-P2-02...ARCH-P2-06
```

本文件中的章节按此顺序排列。任务编号保留历史编号以便追溯，章节先后以本
顺序为准。

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
PR: #378 (MERGED)
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

```text
Status: DONE
Branch: codex/arch-p1-01-direct-table-removal
Merged PR: #379
Merge SHA: 76201af8aad43976ffbcd7d2f72726bac4bc8106
Base SHA: d62e335100ebd41856a5b7822938424a511a5fb0
Final PR head: a40342beadc820527a036df88ee5c29485ba3f36
Final exact-head CI: 29994028200 (W2 Stage 2 CI, success)
Implementation exact-head CI: 29993024046 (verify, staging-parity,
  predeploy-e2e passed)
Staging acceptance: DEAD_TABLES_EVIDENCE_BACKED_AND_DROPPED
  (144 -> 66 tables; 0040 -> 0039 -> 0040 roundtrip passed; 20/20 read-only
  HTTP 200; provider_request_logs delta 0; DML delta 0)
Completed at: 2026-07-23T09:20:43Z
Owner: Codex
Migration head after merge: 0040_drop_empty_fk_components
Rollback: revert PR #379; downgrade 0040 -> 0039 restores all 35 tables as
  empty structures, as proven by the executed staging roundtrip.
```

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
- [x] migration upgrade/downgrade、完整 CI 和 staging 验收通过。
- [x] PR 合并。

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
| `ablation_run` | 0 | 无 | 无 | 无 | 无 | 1/0 | 无（空 replay 组件） | 删除（0040） |
| `alembic_version` | 1 | 有 | 有 | 无 | 无 | 0/0 | 有（1 行） | 保留 |
| `api_request_audit` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `asof_samples` | 0 | 无 | 无 | 无 | 无 | 2/0 | 无（空 dataset/as-of 组件） | 删除（0040） |
| `audit_events` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `backup_run` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `bookmakers` | 0 | 无 | 无 | 无 | 无 | 0/1 | 无（旧 Stage3 赔率叶子） | 删除（0040） |
| `calibration_artifact` | 0 | 无 | 无 | 无 | 无 | 1/0 | 无（空 model experiment 组件） | 删除（0040） |
| `canonical_historical_ah_facts` | 0 | 有 | 有 | 无 | 无 | 1/0 | 运行/安全契约 | 保留 |
| `canonical_team_match_history` | 102 | 有 | 有 | 有 | 无 | 3/0 | 有（102 行） | 保留 |
| `canonical_teams` | 16 | 有 | 有 | 无 | 无 | 0/4 | 有（16 行） | 保留 |
| `challenger_model` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `competitions` | 0 | 无 | 无 | 无 | 无 | 0/2 | 正式推荐/结算 Fixture FK 安全合同 | 保留 |
| `data_provenance` | 0 | 无 | 无 | 无 | 无 | 1/0 | 无（空旧 provenance 组件） | 删除（0040） |
| `data_quality_runs` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `dataset_artifacts` | 0 | 无 | 无 | 无 | 无 | 1/0 | 无（空 dataset/as-of 组件） | 删除（0040） |
| `dataset_sources` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `dataset_versions` | 0 | 无 | 无 | 无 | 无 | 0/2 | 无（空 dataset/as-of 组件） | 删除（0040） |
| `dependency_risk` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `dynamic_prematch_evaluations` | 0 | 有 | 有 | 有 | 无 | 0/2 | 运行/安全契约 | 保留 |
| `dynamic_prematch_supersessions` | 0 | 有 | 有 | 有 | 无 | 2/0 | 运行/安全契约 | 保留 |
| `evaluation_record` | 0 | 无 | 无 | 无 | 无 | 1/0 | 无（空 replay 组件） | 删除（0040） |
| `feature_snapshots` | 0 | 无 | 无 | 无 | 无 | 1/0 | 无（旧 Stage3 特征叶子） | 删除（0040） |
| `fixtures` | 0 | 无 | 无 | 无 | 无 | 7/11 | 正式推荐、锁、赛果、结算当前 FK 安全合同 | 保留 |
| `football_data_team_crosswalks` | 0 | 有 | 有 | 无 | 无 | 0/0 | 运行/安全契约 | 保留 |
| `forward_cycle_checkpoint` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `forward_cycle_run` | 0 | 无 | 无 | 无 | 无 | 0/1 | 无（空旧 forward cycle 组件） | 删除（0040） |
| `forward_evaluation` | 0 | 无 | 无 | 无 | 无 | 1/0 | 无（空 forward holdout 组件） | 删除（0040） |
| `forward_gate_audit` | 0 | 无 | 无 | 无 | 无 | 1/0 | 无（空旧 forward cycle 组件） | 删除（0040） |
| `forward_holdout_run` | 0 | 无 | 无 | 无 | 无 | 0/1 | 无（空 forward holdout 组件） | 删除（0040） |
| `forward_market_snapshot` | 0 | 有 | 无 | 无 | 有 | 0/0 | 报表读取契约 | 保留 |
| `forward_operational_alert` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `forward_prediction_lock` | 0 | 无 | 无 | 无 | 无 | 1/1 | 无（空 forward holdout 组件） | 删除（0040） |
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
| `ingestion_runs` | 0 | 无 | 无 | 无 | 无 | 0/1 | Provider 请求审计账本当前 FK 安全合同 | 保留 |
| `injuries` | 0 | 无 | 无 | 无 | 无 | 2/0 | 无（旧 Stage3 伤停叶子） | 删除（0040） |
| `label_references` | 0 | 无 | 无 | 无 | 无 | 0/1 | 无（空 dataset/as-of 组件） | 删除（0040） |
| `league_profile` | 14 | 有 | 有 | 无 | 无 | 0/0 | 有（14 行） | 保留 |
| `league_readiness_audit` | 20 | 有 | 有 | 无 | 无 | 0/0 | 有（20 行） | 保留 |
| `league_season` | 14 | 有 | 有 | 无 | 无 | 0/0 | 有（14 行） | 保留 |
| `league_team_membership` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `lineup_confirmed_events` | 0 | 无 | 有 | 有 | 无 | 0/0 | prematch 运行契约 | 保留 |
| `lineup_source_snapshots` | 0 | 有 | 有 | 有 | 无 | 0/0 | lineup 运行契约 | 保留 |
| `lineups` | 0 | 无 | 无 | 无 | 无 | 3/0 | 无（旧 Stage3 阵容叶子） | 删除（0040） |
| `market_baseline_run` | 0 | 无 | 无 | 无 | 无 | 0/1 | 无（空 market baseline 组件） | 删除（0040） |
| `market_consensus` | 0 | 无 | 无 | 无 | 无 | 1/0 | 无（旧 Stage3 market consensus 叶子） | 删除（0040） |
| `market_fit_diagnostic` | 0 | 无 | 无 | 无 | 无 | 1/0 | 无（空 market baseline 组件） | 删除（0040） |
| `market_quality_assessment` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `markets` | 0 | 无 | 无 | 无 | 无 | 1/0 | 无（旧 Stage3 market 叶子） | 删除（0040） |
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
| `model_artifact` | 0 | 无 | 无 | 无 | 无 | 1/0 | 无（空 model experiment 组件） | 删除（0040） |
| `model_evaluation` | 0 | 无 | 无 | 无 | 无 | 1/0 | 无（空 model experiment 组件） | 删除（0040） |
| `model_experiment` | 0 | 无 | 无 | 无 | 无 | 0/3 | 无（空 model experiment 组件） | 删除（0040） |
| `model_gate_decision` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `model_runs` | 0 | 无 | 无 | 无 | 无 | 0/1 | 正式 Recommendation.prediction_id FK 安全合同 | 保留 |
| `odds_observations` | 0 | 无 | 无 | 无 | 无 | 2/0 | 无（当前赔率权威为 matchday_market_observations） | 删除（0040） |
| `operational_alert` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `operational_metric_snapshot` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `operations_check_result` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `operations_cycle` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `player_club_membership_observations` | 0 | 无 | 有 | 无 | 无 | 0/0 | 历史身份写入契约 | 保留 |
| `player_identity_crosswalks` | 0 | 有 | 有 | 无 | 无 | 0/0 | ARCH-P1-03 待对账 | 保留 |
| `player_identity_mappings` | 0 | 有 | 有 | 有 | 无 | 0/1 | lineup 身份契约 | 保留 |
| `player_valuation_observations` | 0 | 有 | 有 | 有 | 无 | 0/0 | 估值运行契约 | 保留 |
| `players` | 0 | 无 | 无 | 无 | 无 | 0/4 | 无（旧 Stage3 player 子图整体为空） | 删除（0040） |
| `prediction_snapshot` | 0 | 无 | 无 | 无 | 无 | 1/0 | 无（空 replay 组件） | 删除（0040） |
| `predictions` | 0 | 无 | 无 | 无 | 无 | 2/1 | Recommendation.prediction_id 当前正式追踪合同 | 保留 |
| `promotion_relegation_mapping` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `provider_entity_mappings` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `provider_request_logs` | 162 | 有 | 有 | 有 | 无 | 1/0 | 有（162 行） | 保留 |
| `provider_team_identity_crosswalks` | 16 | 有 | 有 | 有 | 无 | 1/0 | 有（16 行） | 保留 |
| `quota_usage` | 9 | 有 | 有 | 有 | 无 | 0/0 | 有（9 行） | 保留 |
| `raw_payload` | 220 | 有 | 有 | 有 | 无 | 0/0 | 有（220 行） | 保留 |
| `raw_payload_references` | 0 | 无 | 无 | 无 | 无 | 0/1 | 无（现行原始载荷权威为 raw_payload） | 删除（0040） |
| `read_model_checkpoint` | 8 | 有 | 有 | 无 | 有 | 0/0 | 有（8 行） | 保留 |
| `recommendation_locks` | 0 | 有 | 无 | 无 | 有 | 3/2 | 安全锁账本 | 保留 |
| `recommendations` | 0 | 有 | 有 | 无 | 有 | 2/2 | 正式推荐安全账本 | 保留 |
| `referees` | 0 | 无 | 无 | 无 | 无 | 0/1 | Fixture 正式推荐/结算身份合同字段 | 保留 |
| `registered_roster_snapshots` | 0 | 有 | 有 | 无 | 无 | 0/0 | roster 运行契约 | 保留 |
| `release_audit` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `release_candidate` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `replay_checkpoint` | 0 | 无 | 无 | 无 | 无 | 1/0 | 无（空 replay 组件） | 删除（0040） |
| `replay_event` | 0 | 无 | 无 | 无 | 无 | 1/0 | 无（空 replay 组件） | 删除（0040） |
| `replay_run` | 0 | 无 | 无 | 无 | 无 | 0/5 | 无（空 replay 组件） | 删除（0040） |
| `restore_run` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `results` | 0 | 有 | 无 | 无 | 有 | 1/1 | 结算读取契约 | 保留 |
| `retention_audit` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `season_rollover_plan` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `seasons` | 0 | 无 | 无 | 无 | 无 | 1/3 | Fixture 正式推荐/结算身份合同 | 保留 |
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
| `squads` | 0 | 无 | 无 | 无 | 无 | 3/0 | 无（旧 Stage3 player 子图整体为空） | 删除（0040） |
| `stage7i_lifecycle_event` | 0 | 有 | 有 | 有 | 无 | 0/0 | supervision 运行契约 | 保留 |
| `stage7i_lifecycle_heartbeat` | 0 | 有 | 有 | 有 | 无 | 0/0 | supervision 运行契约 | 保留 |
| `stage7i_lifecycle_run` | 0 | 有 | 有 | 有 | 无 | 0/0 | supervision 运行契约 | 保留 |
| `stages` | 0 | 无 | 无 | 无 | 无 | 1/1 | Fixture 正式推荐/结算身份合同 | 保留 |
| `structured_lineup_players` | 0 | 有 | 有 | 有 | 无 | 2/0 | lineup 运行契约 | 保留 |
| `structured_lineup_snapshots` | 0 | 有 | 有 | 有 | 无 | 0/1 | lineup 运行契约 | 保留 |
| `suspensions` | 0 | 无 | 无 | 无 | 无 | 2/0 | 无（旧 Stage3 player 子图整体为空） | 删除（0040） |
| `sync_cursors` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `system_metadata` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0038） |
| `t30_validation_snapshots` | 0 | 有 | 有 | 有 | 无 | 0/0 | prematch 运行契约 | 保留 |
| `team_identity_crosswalks` | 16 | 有 | 有 | 无 | 无 | 0/0 | 有（16 行） | 保留 |
| `team_lineup_baselines` | 0 | 有 | 有 | 有 | 无 | 0/0 | lineup 运行契约 | 保留 |
| `team_rating_snapshots` | 16 | 有 | 有 | 有 | 无 | 1/0 | 有（16 行） | 保留 |
| `team_ratings` | 0 | 无 | 无 | 无 | 无 | 1/0 | 无（现行评分权威为 team_rating_snapshots） | 删除（0040） |
| `team_value_asof_artifacts` | 0 | 有 | 有 | 无 | 无 | 0/0 | FAH 运行契约 | 保留 |
| `team_xg_match` | 104 | 有 | 有 | 有 | 无 | 0/0 | 有（104 行） | 保留 |
| `team_xg_rolling_snapshot` | 28 | 有 | 有 | 有 | 无 | 0/0 | 有（28 行） | 保留 |
| `teams` | 0 | 无 | 无 | 无 | 无 | 0/7 | Fixture 正式推荐/结算身份合同 | 保留 |
| `tournament_operations_plan` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `tournament_profile` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `tournament_readiness_audit` | 0 | 无 | 无 | 无 | 无 | 0/0 | 无（空表） | 删除（0039） |
| `transfermarkt_player_references` | 0 | 有 | 有 | 有 | 无 | 0/0 | player identity 运行契约 | 保留 |
| `venues` | 0 | 无 | 无 | 无 | 无 | 0/1 | Fixture 正式推荐/结算身份合同字段 | 保留 |
| `weather_observations` | 0 | 无 | 无 | 无 | 无 | 1/0 | 无（旧 Stage3 天气叶子） | 删除（0040） |

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
- migration `0040_drop_empty_fk_components` 追加按 FK 依赖顺序删除 35 表：
  - replay：`replay_run`、`replay_event`、`replay_checkpoint`、
    `prediction_snapshot`、`evaluation_record`、`ablation_run`；
  - dataset/as-of：`dataset_versions`、`dataset_artifacts`、
    `label_references`、`asof_samples`；
  - model experiment/artifact：`model_experiment`、`model_artifact`、
    `calibration_artifact`、`model_evaluation`；
  - forward holdout/evaluation：`forward_holdout_run`、
    `forward_prediction_lock`、`forward_evaluation`；
  - market baseline：`market_baseline_run`、`market_fit_diagnostic`；
  - 旧 provenance：`raw_payload_references`、`data_provenance`；
  - 旧 forward cycle：`forward_cycle_run`、`forward_gate_audit`；
  - Stage3 空叶子：`bookmakers`、`odds_observations`、
    `market_consensus`、`markets`、`feature_snapshots`、`players`、
    `squads`、`lineups`、`injuries`、`suspensions`、`team_ratings`、
    `weather_observations`。
- 0038/0039 的 43 表均为 0 行、0 入站/出站外键、0 生产读写、0 任务、0 报表，
  不含独有数据；只存在的 ORM 注册、历史脚本或旧测试未作为保留理由。
- 0040 的 35 表在 drop 前均为 0 行、0 生产读写、0 任务、0 报表；其
  FK 连通子图经递归检查后没有当前业务入口。外键只用于确定子表先删、
  父表后删的顺序，不作为保留理由。
- 数据迁移行数为 0；每张表的规范化空集 hash 均为 SHA-256
  `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945`。
- 历史 migration 与已在 staging 执行的 `0039` 原样保留；追加删除只在
  `0040` 中实施。各 revision downgrade 恢复原列、外键、唯一约束和索引，
  upgrade 再次正式删除。

**迁移后 drop**

- 无。没有非空重复表同时满足唯一权威已确认、字段身份可逆和 hash 对账
  三项直接证据，因此本任务不搬运或删除任何业务数据。

**保持原状并继续调查**

- 赔率身份组：`future_market_observation`、`matchday_market_observations`。
  两者存在实际生产路径和数据，后续身份收敛仍由 ARCH-P1-02 处理；已为空
  且无生产路径的旧 `odds_observations` 不再参与对账，在 0040 直接删除。
- 球队/球员身份组：`football_data_team_crosswalks`、
  `team_identity_crosswalks`、
  `provider_team_identity_crosswalks`、`player_identity_crosswalks`、
  `player_identity_mappings`。存在实际 Repository 路径、有效数据或
  canonical 对账依赖，由 ARCH-P1-03 处理。
- Stage3 核心保留组件为 `competitions -> seasons/stages -> fixtures`、
  `teams/referees/venues -> fixtures` 与
  `model_runs -> predictions -> recommendations`。当前
  `tracking/formal_results.py`、`settlement/history.py`、
  `recommendation_lock_snapshot.py` 和 `audit_export/tables.py` 直接执行
  正式推荐、不可变锁、赛果、结算及审计合同；因此相关 FK 核心表属于当前
  安全合同，不以“关系结构”作为保留理由。
- `ingestion_runs` 由非空且当前生产写入的 `provider_request_logs` 引用，
  用于 Provider 请求审计账本身份，属于当前安全合同。
- 其余保留表的逐表理由以矩阵为准：有非空数据、生产读写、任务、报表或
  明确的当前安全/已批准业务合同；不存在仅写“关系结构待收敛”的保留项。
- `alembic_version` 是 migration 控制表，不是业务表，不得删除。

**本轮验收回执**

- 状态流转：外部二次验收修复期间为 `FIX_IN_PROGRESS`；递归组件审计、
  0040 migration、完整 CI、staging 往返与零写验收完成后转
  `READY_FOR_EXTERNAL_REVIEW`；外部审核通过并合并后为 `DONE`。0039 始终
  保持不变，追加删除只通过新 revision `0040` 执行；
- PR：`#379`，已于 `2026-07-23T09:20:43Z` 合并，merge SHA
  `76201af8aad43976ffbcd7d2f72726bac4bc8106`；
- validated implementation/final code head：
  `d004cd946a42ad2fade0799d297ca31358c2f41e`；
- PR final receipt head：合并时 GitHub `headRefOid` =
  `a40342beadc820527a036df88ee5c29485ba3f36`（合并后可回溯确定，故在此固化）；
- implementation exact-head CI：run `29993024046`，`verify`、
  `staging-parity`、`predeploy-e2e` 全绿；
- final receipt exact-head CI：run `29994028200`（`W2 Stage 2 CI`）在
  `a40342be` 上 `success`，合并前 required checks 全部通过；
- staging release SHA：
  `d004cd946a42ad2fade0799d297ca31358c2f41e`；
- staging migration：
  `0040_drop_empty_fk_components`；
- migration 往返：
  `0040 -> 0039 -> 0040` 通过；downgrade 后 staging 为 101 表，
  0040 的 35/35 张表全部恢复且均为 0 行；upgrade 后 staging 为 66 表，
  35/35 张表再次全部不存在；
- staging 表数：`144 -> 66`，共删除 78 张直接证据完整的空表，其中
  0038/0039 删除 43 张、0040 追加删除 35 张；
- 20 轮真实公共 HTTP 只读检查全部通过：`20/20 HTTP 200`，读取
  `/v1/dashboard/day-view`、`/v1/dashboard/summary`、`/v1/fixtures`、
  `/v1/providers/status` 各 5 次，p95 `151.3ms`、max `154.3ms`；
- Provider request logs：`162 -> 162`，增量 0；
- staging 全业务表 DML 统计：
  `insert/update/delete = 58159/390/0 -> 58159/390/0`，增量 0；
- `recommendations=0`、`recommendation_locks=0`、
  `gate5_recommendation_lock_event=0`、`settlements=0`、
  `shadow_strategy_lock=0`；
- `W2_PROVIDER_CALLS_DISABLED=true`、
  `W2_PROVIDER_SCHEDULER_ENABLED=false`、
  `W2_RECOMMENDATION_ENABLED=false`、`W2_CANDIDATE_ENABLED=false`、
  `W2_PRODUCTION_RELEASE=false`；
- API、worker、scheduler、web、PostgreSQL、Redis 全部 healthy；
  `/opt/w2/current`、`release.env`、API/Web release SHA 与 staging release
  SHA 一致。

**验收**

```text
DEAD_TABLES_EVIDENCE_BACKED_AND_DROPPED
NO_BUSINESS_HISTORY_DELETED
```

---

## ARCH-P1-02：赔率表收敛

```text
Status: DONE
Branch: codex/arch-p1-02-odds-table-convergence
PR: #381 (MERGED)
Base SHA: 8af05ddbacf32370303fb0e57e5097d6634c278e
Started at: 2026-07-23T19:30:00+0800
Owner: Codex
Validated implementation head: 1d02a45c6f38c3613ac3dddab784869095bf6804
Exact-head CI: 30011857074 (success)
CI history: 30005506955 (predeploy-e2e 失败，已修) -> 30008088208 (pass)
  -> 30011185720 (整改后 pass) -> 30011857074 (exact head, pass)
  -> 30016906612 (最终回执 db55523, pass)
Final head: 47c7ef7da368fa54b4643e56c0efdeb2990f23f5
Final exact-head CI: 30017659192 (success)
Merge SHA: f53b073f5f53e078d75831ad4f2c0c648f32db88
Completed at: 2026-07-23T15:04:25Z
Staging acceptance: PASS — release 1d02a45，migration 0041，表数 66 -> 65，
  投影为 VIEW，canonical 44644 不变，投影 10648 行 hash 3bf130fc，
  20 轮 HTTP 80/80 且 hash 稳定，Provider 与业务 DML 增量 0，
  0041 -> 0040 -> 0041 往返通过。完整回执见第零节 0.5
Evidence: 变更记录 0.3；整改记录 0.4；staging 验收回执 0.5
Rollback: revert PR #381；migration downgrade 0041 -> 0040 删视图并恢复 legacy
  表结构；1920 条报价全程留在 canonical 表中（往返已在 staging 实测）
```

**本任务已完成并合并。** 下一任务是 `ARCH-HYGIENE-01`；本次 docs-only
清单修订 PR 合并前，不得开始其代码修改。

### 现状锚点（2026-07-23 在 `main@8af05dd` 与 staging 复核）

```text
CANONICAL_HISTORY_AUTHORITY   = matchday_market_observations (44644 行)
CURRENT_PRODUCTION_READ_ENTRY =
  ReadModelRepository.future_market_observations_for_fixtures()
  (src/w2/api/repository.py)
CANONICAL_WRITE_ENTRY         =
  MatchdayRuntimeRepository.insert_market_observations()
  (经 FutureFixtureRefresh._persist_db, src/w2/ingestion/future_refresh.py)
LEGACY_TABLE                  = future_market_observation (3840 行)
LEGACY_WRITE_METHOD           =
  FutureRefreshDbRepository.append_observations()
  (src/w2/ingestion/future_refresh_repository.py)
LEGACY_WRITE_PRODUCTION_CALLERS = 0
CURRENT_MARKET_PROJECTION_OBJECT = 无（读时在 Python 内存去重）
```

**对交接锚点的更正**：legacy 表当前**没有生产写入者**。
`FutureRefreshDbRepository.append_observations()` 全仓库只有测试调用；
`src/w2/ingestion/future_refresh.py:1452` 的 `ledger.append_observations(...)`
作用于文件版 `MarketObservationLedger`（JSONL），与 DB repository 同名但不是
同一个类。DB 持久化分支 `_persist_db()` 写的是 `matchday_market_observations`。
`pg_stat_user_tables` 佐证：legacy 表 `n_tup_ins=3840`、`n_tup_upd=0`、
`n_tup_del=0`，全部为历史写入。

因此本任务不是拆双写，而是：删除死写入路径 + 证明 legacy 行无独有数据 +
drop + 建立唯一当前盘口投影。

### staging identity/hash 对账（只读，2026-07-23）

```text
STAGING_RELEASE   = d004cd946a42ad2fade0799d297ca31358c2f41e
STAGING_MIGRATION = 0040_drop_empty_fk_components
STAGING_TABLES    = 66
LEGACY_ROWS                    = 3840
LEGACY_DISTINCT_BUSINESS_TUPLES= 1920
LEGACY_DUPLICATION_SHAPE       = 1920 bare + 1920 "api_football:" prefixed
FULL_QUOTE_IDENTITY_MATCH      = 3840 / 3840 (100%)
  （fixture、bookmaker、market、selection、signed line、odds、captured_at）
RAW_PAYLOAD_SHA_MATCH          = 3840 / 3840 (100%)
TUPLE_TO_CANONICAL_CARDINALITY = {1}   （每个 legacy 业务元组恰好命中 1 行）
LEGACY_NORMALIZED_HASH         = f3790cd3162df8e6895b7cdc86408ab7
CANONICAL_SUBSET_HASH          = f3790cd3162df8e6895b7cdc86408ab7
UNIQUE_DATA_IN_LEGACY          = 0
```

legacy 表的 3840 行是同一 1920 条报价在两种 fixture id 写法下的重复存储，
且全部被 canonical 表逐字段覆盖。因此**不需要搬运任何业务数据**，drop 不
删除任何独有历史。

### 补充要求：drop migration 必须先断言再删除

自本任务起，所有 drop migration 的 `upgrade()` 在删除每张表前必须先查询并
断言，断言不成立即抛错终止，不得静默继续。按删除依据分两种，只能二选一：

- **空表删除**：`SELECT count(*)`，非零即抛错。
- **重复表删除**：`SELECT count(*)` 统计未被唯一权威表覆盖的行，非零即抛错；
  覆盖判定必须使用完整 quote/业务身份，不得只比主键。

背景：`0038`、`0039`、`0040` 只有 `has_table` 守卫，在有数据的环境重放会
无提示删除数据。历史 revision 保持原样不追溯修改，本要求只对新 revision
生效。

```text
DROP_MIGRATION_GUARD = REQUIRED_FROM_ARCH_P1_02
DROP_MIGRATION_GUARD_KINDS = EMPTY_TABLE | FULLY_COVERED_DUPLICATE
```

### 已解决：有界读路径的截断顺序（老板 2026-07-23 选定候选 A）

```text
Blocker: BOUNDED_PROJECTION_READ_HAS_NO_DEFINED_TRUNCATION_ORDER
Resolution: OPTION_A_TOTAL_DETERMINISTIC_ORDER
Approved by: 老板，2026-07-23
```

投影读取的排序键补全为：

```text
projection_fixture_id, canonical_market, bookmaker_id, canonical_selection,
line, observation_id
```

这是一次**经批准的 Dashboard 展示变化**，只影响被 128 行上限截断的组合。
staging 实测影响面：

```text
SCOPED_PROJECTION_ROWS          = 9649
ROWS_KEPT_AFTER_BOUND           = 7812
ROWS_DROPPED_BY_BOUND           = 1837
AFFECTED_FIXTURE_MARKET_GROUPS  = 45
AFFECTED_FIXTURES               = 24
KEPT_SET_HASH                   = 64b9fca07f19c75c9e3d670cda22c399
```

上限 `SCOPED_OBSERVATION_ROWS_PER_MARKET = 128` 不变。截断结果自此可复现：
同一份数据重复请求必然返回同一组 `KEPT_SET_HASH`。

无界读路径（`latest_market_observations()` → `market_snapshots()`）切到
`current_market_projection` 视图，语义在 staging 全量数据上逐行对账一致：

```text
STAGING_INPUT_ROWS   = 44644
OLD_PATH_ROWS        = 10648
VIEW_ROWS            = 10648
OLD_PATH_HASH        = 056069e2ab386b5deae451239f917fb0
VIEW_HASH            = 056069e2ab386b5deae451239f917fb0
UNBOUNDED_READ_PARITY= EXACT
```

有界读路径（`latest_market_observations_for_fixtures()`）**不能**在本任务
直接切换。它在每个 `(fixture, market)` 组上截断到
`SCOPED_OBSERVATION_ROWS_PER_MARKET = 128` 行，而截断前的排序键是
`(fixture, market, bookmaker, selection)`——不含 `line`。同一排序键下的多个
line 变体之间**没有任何 tie-break**，现行实现落到 Python dict 的插入顺序，
即数据库返回行的任意顺序。

证据（staging，只读）：

```text
OVER_BOUND_FIXTURE_MARKET_GROUPS            = 45    （超过 128 行，截断生效）
AMBIGUOUS_SORT_GROUPS_SAME_FIRST_SEEN       = 946
ROWS_INSIDE_OVER_BOUND_FIXTURE_MARKETS      = 7597
```

即：当前生产读路径对这 45 个 fixture/market 组合是**不确定的**——两次相同
请求可以合法返回不同的 128 条报价。这是既有缺陷，不是本任务引入的。因此
不存在"忠实复现旧顺序"这一选项：任何确定性排序都会改变这些组合下
Dashboard 实际展示的报价子集，触发立即停止条件"Dashboard 语义发生未批准
变化"。

```text
Next required decision: 有界投影读取的截断顺序采用哪一种确定性定义。
候选 A（建议）：order by projection_fixture_id, canonical_market, bookmaker_id,
  canonical_selection, line, observation_id —— 顺序稳定、可复现、与无界路径
  同源，代价是这 45 个组合展示的报价子集会变化一次。
候选 B：提高或取消 128 行上限，使截断不再发生 —— 不改变展示内容，但放大
  单次响应体积，需要评估 Dashboard 与 API 负载。
候选 C：维持现状不切换有界路径 —— 当前投影会保留两套实现，与
  CURRENT_MARKET_PROJECTION_AUTHORITY_COUNT = 1 冲突。
```

决定作出后，两条读路径都只读该视图，仓库内不再保留第二套投影实现
（内存去重与 `_matchday_observation_dict` 已删除）。

- [x] 从活跃赔率表中选定：
  - 一张唯一 append-only 历史表；
  - 一张当前盘口投影（表或视图）。
- [x] 不创建第二套历史表。
- [x] 完成历史数据迁移和 identity/hash 对账。
- [x] 停止 legacy 写入，禁止新增或保留双写过渡。
- [x] 所有读路径切到 canonical 历史 + 当前投影。
- [x] 删除 legacy ORM、Repository、脚本、测试、配置及其全部运行时引用。
- [x] 在同一 PR 使用新 migration drop 已完成迁移且证据充分的旧表；
  不创建 archive、backup、兼容 view 或替代 fallback。
- [x] 证据不足的表保持原状并继续调查，不重命名隔离。
- [x] 新增 drop migration 的 `upgrade()` 对每张待删表先 `SELECT count(*)`，
  非零即抛错。
- [x] migration upgrade/downgrade、行数/hash 对账、完整 CI 和 staging 验收通过。
- [x] PR 合并。

**验收**

```text
CANONICAL_ODDS_HISTORY_AUTHORITY_COUNT = 1
CURRENT_MARKET_PROJECTION_AUTHORITY_COUNT = 1
DROP_MIGRATION_NONEMPTY_GUARD = PRESENT
```

---

## ARCH-HYGIENE-01：生成审计产物退出 Git

```text
Status: DONE
Started at: 2026-07-23T18:43:42Z
Owner: Codex
Base SHA: db3fd12fedb76e9a9cb074f7a3dcc3294042c2fc
Branch: codex/arch-hygiene-01-generated-audits-exit-git
PR: #383 (MERGED)
Previous correction head: 47d3fdf9941ddce3f2c9fbe9466c8afa2ce2c53c
Previous correction exact-head CI: 30054047005 (PASS)
Implementation head: b6d858d614647d62f5cbc271e1d6f7f7da59303d
Implementation exact-head CI: 30055030785 (PASS)
Final head: 48acd4391f7d95c487bd47576532db36cf22fb1c
Final exact-head CI: 30055670729 (PASS)
Merge SHA: 748b50e5c990c6138193810ec319e0e413a7ab25
Completed at: 2026-07-24T00:37:57Z
Scope: docs/audits/system_truth 生成产物、相关生成器及双重静态守卫
Next task: ARCH-HYGIENE-02
```

本任务只治理生成审计产物的版本控制边界，不修改生产行为或任何安全开关，
也不重写 Git 历史。

### Codex 执行指令合同

```text
CODEX_INSTRUCTION_POLICY_V1
NEW_TASK_FIRST_TURN = READ_AND_EXECUTE_COMPLETE_TASK_CONTRACT
SAME_PR_FOLLOW_UP = APPLY_INCREMENTAL_DELTA_ONLY
STATUS_DOCUMENT_AUTHORITY = THIS_MASTER_CHECKLIST
```

新任务的首轮必须读取并执行该任务的完整合同；同一 PR 的后续修复仅应用新增
指令，不重复创建状态文档、不重写已验收回执。

### 受跟踪文件逐项分类矩阵（开工基线 69 项）

统一路径前缀：`docs/audits/system_truth/`。引用扫描口径为该目录外的精确
文件名引用；69 项均为 `0`。生成器与同目录 manifest 的内部引用不构成人工
维护证据。

证据代码：

- `G1`：commit `22391c8` 批量建立的 V1 结构化审计，具有成对 JSON/Markdown、
  schema 与生成时间字段。
- `G2`：commit `8482813` 与
  `scripts/audit_w2_runtime_authorities.py` 的明确输出表；其中 V2
  compatibility aliases 来自原 `phase0_aliases`。
- `H1`：commit `601fd55` 的人工 post-consolidation 实施回执；当前生成器无
  对应 writer，JSON 也不含生成时间/生成器 SHA 合同。
- `H2`：commit `22391c8` 的人工叙事性简化计划；无成对 JSON、无生成器
  writer。

| 文件 | 分类 | 直接证据 | 目录外精确引用 | 决定 |
|---|---|---|---:|---|
| `W2_AUTHORITY_MAP_V1.json` | MACHINE_GENERATED | G1 | 0 | git rm |
| `W2_AUTHORITY_MAP_V1.md` | MACHINE_GENERATED | G1 | 0 | git rm |
| `W2_AUTHORITY_MAP_V3.json` | MACHINE_GENERATED | G2 | 0 | git rm |
| `W2_AUTHORITY_MAP_V3.md` | MACHINE_GENERATED | G2 | 0 | git rm |
| `W2_CAPABILITY_LIFECYCLE_LEDGER_V1.json` | MACHINE_GENERATED | G1 | 0 | git rm |
| `W2_CAPABILITY_LIFECYCLE_LEDGER_V1.md` | MACHINE_GENERATED | G1 | 0 | git rm |
| `W2_CONFIG_FLAG_MATRIX_V1.json` | MACHINE_GENERATED | G1 | 0 | git rm |
| `W2_CONFIG_FLAG_MATRIX_V1.md` | MACHINE_GENERATED | G1 | 0 | git rm |
| `W2_CONFIG_FLAG_MATRIX_V3.json` | MACHINE_GENERATED | G2 | 0 | git rm |
| `W2_CONFIG_FLAG_MATRIX_V3.md` | MACHINE_GENERATED | G2 | 0 | git rm |
| `W2_CONSOLIDATION_ACCEPTANCE_REPORT_V1.json` | MACHINE_GENERATED | G2 | 0 | git rm |
| `W2_CONSOLIDATION_ACCEPTANCE_REPORT_V1.md` | MACHINE_GENERATED | G2 | 0 | git rm |
| `W2_CONSOLIDATION_IMPLEMENTATION_REPORT_V1.json` | HUMAN_MAINTAINED | H1 | 0 | 保留 |
| `W2_CONSOLIDATION_IMPLEMENTATION_REPORT_V1.md` | HUMAN_MAINTAINED | H1 | 0 | 保留 |
| `W2_CONSOLIDATION_MANIFEST_V1.json` | MACHINE_GENERATED | G2 | 0 | git rm |
| `W2_CONSOLIDATION_MANIFEST_V1.md` | MACHINE_GENERATED | G2 | 0 | git rm |
| `W2_DATABASE_OWNERSHIP_MAP_V1.json` | MACHINE_GENERATED | G1 | 0 | git rm |
| `W2_DATABASE_OWNERSHIP_MAP_V1.md` | MACHINE_GENERATED | G1 | 0 | git rm |
| `W2_DATABASE_OWNERSHIP_MAP_V3.json` | MACHINE_GENERATED | G2 | 0 | git rm |
| `W2_DATABASE_OWNERSHIP_MAP_V3.md` | MACHINE_GENERATED | G2 | 0 | git rm |
| `W2_DATA_ASSET_REGISTRY_V1.json` | MACHINE_GENERATED | G1/G2 | 0 | git rm |
| `W2_DATA_ASSET_REGISTRY_V1.md` | MACHINE_GENERATED | G1 | 0 | git rm |
| `W2_DATA_ASSET_REGISTRY_V3.json` | MACHINE_GENERATED | G2 | 0 | git rm |
| `W2_DATA_ASSET_REGISTRY_V3.md` | MACHINE_GENERATED | G2 | 0 | git rm |
| `W2_FACTOR_STRATEGY_REGISTRY_V2.json` | MACHINE_GENERATED | G2 alias | 0 | git rm |
| `W2_FACTOR_STRATEGY_REGISTRY_V2.md` | MACHINE_GENERATED | G2 alias | 0 | git rm |
| `W2_FACTOR_STRATEGY_REGISTRY_V3.json` | MACHINE_GENERATED | G2 | 0 | git rm |
| `W2_FACTOR_STRATEGY_REGISTRY_V3.md` | MACHINE_GENERATED | G2 | 0 | git rm |
| `W2_FINDING_REGISTRY_V3.json` | MACHINE_GENERATED | G2 | 0 | git rm |
| `W2_FINDING_REGISTRY_V3.md` | MACHINE_GENERATED | G2 | 0 | git rm |
| `W2_LEGACY_DUPLICATE_CODE_REGISTER_V1.json` | MACHINE_GENERATED | G1 | 0 | git rm |
| `W2_LEGACY_DUPLICATE_CODE_REGISTER_V1.md` | MACHINE_GENERATED | G1 | 0 | git rm |
| `W2_LEGACY_DUPLICATE_CODE_REGISTER_V3.json` | MACHINE_GENERATED | G2 | 0 | git rm |
| `W2_LEGACY_DUPLICATE_CODE_REGISTER_V3.md` | MACHINE_GENERATED | G2 | 0 | git rm |
| `W2_PROVIDER_ENDPOINT_MATRIX_V2.json` | MACHINE_GENERATED | G2 alias | 0 | git rm |
| `W2_PROVIDER_ENDPOINT_MATRIX_V2.md` | MACHINE_GENERATED | G2 alias | 0 | git rm |
| `W2_PROVIDER_ENDPOINT_MATRIX_V3.json` | MACHINE_GENERATED | G2 | 0 | git rm |
| `W2_PROVIDER_ENDPOINT_MATRIX_V3.md` | MACHINE_GENERATED | G2 | 0 | git rm |
| `W2_PR_LINEAGE_MAP_V2.json` | MACHINE_GENERATED | G2 native V2 | 0 | git rm |
| `W2_PR_LINEAGE_MAP_V2.md` | MACHINE_GENERATED | G2 native V2 | 0 | git rm |
| `W2_RECOMMENDATION_LIFECYCLE_TRACE_V2.json` | MACHINE_GENERATED | G2 alias | 0 | git rm |
| `W2_RECOMMENDATION_LIFECYCLE_TRACE_V2.md` | MACHINE_GENERATED | G2 alias | 0 | git rm |
| `W2_RECOMMENDATION_LIFECYCLE_TRACE_V3.json` | MACHINE_GENERATED | G2 | 0 | git rm |
| `W2_RECOMMENDATION_LIFECYCLE_TRACE_V3.md` | MACHINE_GENERATED | G2 | 0 | git rm |
| `W2_RISK_REGISTER_V2.json` | MACHINE_GENERATED | G2 native V2 | 0 | git rm |
| `W2_RISK_REGISTER_V2.md` | MACHINE_GENERATED | G2 native V2 | 0 | git rm |
| `W2_RUNTIME_CALL_GRAPH_V2.json` | MACHINE_GENERATED | G2 alias | 0 | git rm |
| `W2_RUNTIME_CALL_GRAPH_V2.md` | MACHINE_GENERATED | G2 alias | 0 | git rm |
| `W2_RUNTIME_CALL_GRAPH_V3.json` | MACHINE_GENERATED | G2 | 0 | git rm |
| `W2_RUNTIME_CALL_GRAPH_V3.md` | MACHINE_GENERATED | G2 | 0 | git rm |
| `W2_RUNTIME_DEPLOYMENT_DELTA_V1.json` | MACHINE_GENERATED | G1 | 0 | git rm |
| `W2_RUNTIME_DEPLOYMENT_DELTA_V1.md` | MACHINE_GENERATED | G1 | 0 | git rm |
| `W2_RUNTIME_DEPLOYMENT_DELTA_V3.json` | MACHINE_GENERATED | G2 | 0 | git rm |
| `W2_RUNTIME_DEPLOYMENT_DELTA_V3.md` | MACHINE_GENERATED | G2 | 0 | git rm |
| `W2_SCHEDULER_CHECKPOINT_MATRIX_V2.json` | MACHINE_GENERATED | G2 alias | 0 | git rm |
| `W2_SCHEDULER_CHECKPOINT_MATRIX_V2.md` | MACHINE_GENERATED | G2 alias | 0 | git rm |
| `W2_SCHEDULER_CHECKPOINT_MATRIX_V3.json` | MACHINE_GENERATED | G2 | 0 | git rm |
| `W2_SCHEDULER_CHECKPOINT_MATRIX_V3.md` | MACHINE_GENERATED | G2 | 0 | git rm |
| `W2_SIMPLIFICATION_PLAN_V1.md` | HUMAN_MAINTAINED | H2 | 0 | 保留 |
| `W2_SYSTEM_TRUTH_AUDIT_MANIFEST_V2.json` | MACHINE_GENERATED | G2 alias | 0 | git rm |
| `W2_SYSTEM_TRUTH_AUDIT_MANIFEST_V2.md` | MACHINE_GENERATED | G2 alias | 0 | git rm |
| `W2_SYSTEM_TRUTH_MATRIX_V1.json` | MACHINE_GENERATED | G1 | 0 | git rm |
| `W2_SYSTEM_TRUTH_MATRIX_V1.md` | MACHINE_GENERATED | G1 | 0 | git rm |
| `W2_SYSTEM_TRUTH_MATRIX_V3.json` | MACHINE_GENERATED | G2 | 0 | git rm |
| `W2_SYSTEM_TRUTH_MATRIX_V3.md` | MACHINE_GENERATED | G2 | 0 | git rm |
| `W2_TEST_COVERAGE_AUTHORITY_MATRIX_V2.json` | MACHINE_GENERATED | G2 alias | 0 | git rm |
| `W2_TEST_COVERAGE_AUTHORITY_MATRIX_V2.md` | MACHINE_GENERATED | G2 alias | 0 | git rm |
| `W2_TEST_COVERAGE_AUTHORITY_MATRIX_V3.json` | MACHINE_GENERATED | G2 | 0 | git rm |
| `W2_TEST_COVERAGE_AUTHORITY_MATRIX_V3.md` | MACHINE_GENERATED | G2 | 0 | git rm |

分类汇总：`MACHINE_GENERATED=66`、`HUMAN_MAINTAINED=3`；机器生成项基线
共 `206648` 行、`6746431` 字节。删除只改变 Git 跟踪边界，历史仍可从 Git
对象读取，不重写历史。

### 本 PR 实施与直接证据

- 写入方扫描：全仓库只有
  `scripts/audit_w2_runtime_authorities.py` 写入该 system-truth 文件族；未发现
  第二个写入 `docs/audits/system_truth` 的生成器。
- 已对 66 个 `MACHINE_GENERATED` 文件执行 `git rm`；3 个人工文件继续跟踪。
- 生成器默认目录改为 `runtime/audits/system_truth`，并提供
  `--output-dir`/`output_dir`；JSON、Markdown、manifest、路径替换和 glob
  均使用传入目录。
- `generation_head` 在生成开始时读取，所有 payload 的
  `source_review_sha` 在发布前统一校验；生成前与发布前均检查 staged、
  unstaged 和全部实际扫描的 untracked/ignored 输入，发生漂移时保留原目标
  目录且拒绝发布。
- 实际扫描、untracked/ignored 守卫与测试共同复用一份输入路径合同，覆盖
  `src/apps/scripts/tests/migrations/**/*.py`、`.github/workflows/*.{yml,yaml}`、
  `docker-compose.yml`、`infra/compose/*.{yml,yaml}`、`scripts/*.sh` 和
  `.env.example`。
- `audit_generator_sha` 表示生成器所在 Git 代码版本；
  `audit_output_commit_sha` 及其无消费者占位字段已删除。
- 原生 `W2_PR_LINEAGE_MAP_V2`、`W2_RISK_REGISTER_V2` 保留生成；原
  `phase0_aliases` 的 7 组兼容 V2 副本不再生成。
- `.gitignore` 与 `scripts/check_tracked_outputs.py` 双重守卫覆盖未来版本；
  3 个人工文件在两层规则中均明确允许。
- 唯一断链位于人工 `W2_SIMPLIFICATION_PLAN_V1.md`：其原 V1 matrix 文件名
  已改为本总清单权威路径，同时删除已失效的硬编码旧审计 SHA。

### 最终整改回执

前一整改 implementation head
`47d3fdf9941ddce3f2c9fbe9466c8afa2ce2c53c`、exact-head CI
`30054047005` 已证明工作树身份预检、输出目录安全、序列化前路径别名与 JSON
自哈希、未知 Markdown 静态守卫四项整改通过。

本轮 implementation head
`b6d858d614647d62f5cbc271e1d6f7f7da59303d`、exact-head CI
`30055030785` 在同一共享输入合同中补齐 workflow YAML、Compose YAML、
Shell 与 `.env.example`，CI 的 `verify`、`staging-parity`、
`predeploy-e2e` 均为 `PASS`。直接回归证据为：

- staged、unstaged、五个 Python 根目录的 untracked 与 ignored Python 输入：
  `PASS`；
- `.github/workflows/untracked.yml`：拒绝，`PASS`；
- `infra/compose/untracked.yaml`：拒绝，`PASS`；
- `scripts/untracked.sh`：拒绝，`PASS`；
- ignored `infra/compose/ignored_probe.yaml`：拒绝，`PASS`；
- 非 Python 输入不一致时，在任何实际扫描和输出目录验证前失败，既有输出保持
  不变：`PASS`；
- 输出目录归属/原子恢复、18 个 JSON 自哈希、绝对路径归零与未知
  `W2_NEW_MACHINE_REPORT_V1.md` 静态守卫继续通过。

```text
TRACKED_GENERATED_AUDIT_FILES = 0
V2_ALIAS_OUTPUTS = 0
HARDCODED_PERSONAL_PATHS = 0
HARDCODED_SOURCE_REVIEW_SHA = 0
SOURCE_REVIEW_SHA_SOURCE = CURRENT_GIT_HEAD
SOURCE_REVIEW_SHA_MATCHES_GENERATION_HEAD = PASS
SOURCE_REVIEW_SHA_INPUTS_MATCH_GIT_HEAD = PASS
UNTRACKED_SCANNED_NON_PYTHON_FILES_ACCEPTED = 0
PENDING_COMMIT_PLACEHOLDERS = 0
AUDIT_GENERATION_DIRTIES_GIT = 0
BROKEN_AUDIT_REFERENCES = 0
RUNTIME_OUTPUT = 18 JSON + 18 Markdown
IMPLEMENTATION_EXACT_HEAD_CI = 30055030785
VERIFY = PASS
STAGING_PARITY = PASS
PREDEPLOY_E2E = PASS
```

外部最终验收与合并已经完成；以下项目均已有上述实现、回归测试、exact-head
CI 和 merge SHA 的直接证据。

- [x] 逐项区分 `docs/audits/system_truth` 中机器生成文件与人工维护文件，
  形成可复核清单；人工维护文件继续受 Git 管理。
- [x] 对已跟踪的机器生成审计产物执行 `git rm`，不删除人工维护证据。
- [x] 将所有相关生成器的默认输出迁到 `runtime/` 或临时目录。
- [x] 停止生成 V2 兼容别名，并删除既有 V2 别名输出。
- [x] 删除生成器、模板和审计产物中的硬编码个人路径及硬编码的旧
  `SOURCE_REVIEW_SHA`。
- [x] 明确区分两个版本字段：`audit_generator_sha` 表示生成器代码版本；
  `source_review_sha` 表示本次被审计代码树版本，两者不得混用。
- [x] 生成器每次运行时必须通过 `git rev-parse HEAD` 从当前 Git HEAD
  动态取得完整 `source_review_sha`；不得从静态常量、模板默认值或人工复制值
  读取。
- [x] 生成结果必须校验其 `source_review_sha` 等于本次生成开始时取得的 Git
  HEAD；不一致立即失败，不得输出或提交该审计结果。
- [x] 全量扫描并删除所有 `PENDING_COMMIT` 占位，不得把数量写死为“三处”。
- [x] 同时在 `.gitignore` 与 `check_tracked_outputs.py` 增加守卫，阻止机器生成
  审计产物再次进入 Git。
- [x] 运行全部相关生成器后，`git status --short` 必须保持干净。
- [x] 复核所有保留文档的引用，确保移出 Git 后没有断链。
- [x] 完整 exact-head CI 通过；不得在本任务中重写 Git 历史、改变生产行为
  或安全开关。
- [x] PR 经外部审核并合并。

**验收**

```text
TRACKED_GENERATED_AUDIT_FILES = 0
V2_ALIAS_OUTPUTS = 0
HARDCODED_PERSONAL_PATHS = 0
HARDCODED_SOURCE_REVIEW_SHA = 0
SOURCE_REVIEW_SHA_SOURCE = CURRENT_GIT_HEAD
SOURCE_REVIEW_SHA_MATCHES_GENERATION_HEAD = PASS
SOURCE_REVIEW_SHA_INPUTS_MATCH_GIT_HEAD = PASS
UNTRACKED_SCANNED_NON_PYTHON_FILES_ACCEPTED = 0
PENDING_COMMIT_PLACEHOLDERS = 0
AUDIT_GENERATION_DIRTIES_GIT = 0
BROKEN_AUDIT_REFERENCES = 0
```

---

## ARCH-HYGIENE-02：Scripts 权威盘点与证据化直接删除

```text
Status: IN_PROGRESS
Branch: codex/arch-hygiene-02-script-authority-convergence
Base SHA: 748b50e5c990c6138193810ec319e0e413a7ab25
Started at: 2026-07-24T00:42:35Z
Owner: Codex
Supersedes: ARCH-P2-01
Deletion policy: DEAD 直接删除；不建立 scripts/archive
```

### Inventory universe 生成合同与证据口径

inventory universe 不是手写的 `scripts/` 文件列表，而由
`tests/contract/test_script_authority_inventory.py` 在每次 Pytest 中重新生成：

1. `git ls-files` 中任一路径段名为 `scripts` 且后缀为
   `.py/.sh/.mjs/.js/.ts` 的实际存在文件；
2. `.github/workflows`、全部 Dockerfile、Compose、`infra/` systemd/cron、
   `Makefile`、`apps/web/package.json` 中直接执行的脚本或模块；
3. `pyproject.toml [project.scripts]` 的全部 console entrypoint；
4. `alembic.ini script_location` 对应的 migration `env.py`；
5. CI 中作为 Python 程序直接执行的 `tests/secret_scan.py`。

路径解析同时覆盖 Python `-m`、Uvicorn module、Celery `-A`、显式
`.py/.sh/.mjs` 路径；运维文档、Python subprocess/runpy/importlib 与 Shell
调用用于逐项证据和 DEAD 判定。开工基线共 `145` 个脚本身份；本 PR 删除
`8` 个 DEAD 后，当前 universe 为 `137`。矩阵测试要求当前 universe 与
全部非 DEAD 行逐项相等，DEAD 行逐项不存在，任何漏项、重复分类或误删都会
令 CI 失败。

证据代码：

- `E1`：Git 跟踪全集与 Python/import/subprocess/runpy/importlib/Shell 扫描；
- `E2`：`.github/workflows/ci.yml` 或 `check_w2_all.py` 的直接/传递执行边；
- `E3`：Dockerfile、Compose、systemd、package build hook 或部署调用；
- `E4`：当前运维文档/runbook 或脚本自身明确的人工 CLI 合同；
- `E5`：Pytest 对 CLI/脚本函数或打包路径的直接验证；
- `E6`：`pyproject` console entrypoint、Alembic 或 migration 调用；
- `E7`：只允许人工审核后执行的一次性恢复、回填或历史重建合同；
- `D1`：E1–E6 全部调用面为零；`D2`：依赖产物已删除或已有现行权威替代。

### 完整逐脚本唯一分类矩阵

`部署引用` 列的“是”包括 Docker/Compose/systemd/cron/package build hook；
“否”表示四类配置均未调用。`运维文档` 为当前显式人工入口；没有文档但保留
为 `MANUAL_OPS` 的脚本，其直接调用方写为“人工 CLI”，依据是脚本自己的
参数/只读输出合同，不把“零引用”伪装成自动调用。

<!-- SCRIPT_AUTHORITY_MATRIX_START -->
| path | 唯一分类 | 直接调用方 | 传递调用链 | 运行环境 | 部署引用 | 运维文档 | 决定 | 证据 |
|---|---|---|---|---|---|---|---|---|
| `apps/api/main.py` | `RUNTIME_ENTRYPOINT` | Dockerfile.api / Compose Uvicorn | config → process | runtime | 是 | 无 | `KEEP` | E3/E5/E6 |
| `apps/scheduler/main.py` | `RUNTIME_ENTRYPOINT` | Dockerfile.scheduler / Compose `python -m` | config → process | runtime | 是 | 无 | `KEEP` | E3/E5/E6 |
| `apps/web/scripts/write-meta.mjs` | `DEPLOYMENT` | package.json predev/prebuild | npm → script | build | 是 | 无 | `KEEP` | E3 |
| `apps/worker/celery_app.py` | `RUNTIME_ENTRYPOINT` | Dockerfile.worker / Compose Celery | config → process | runtime | 是 | 无 | `KEEP` | E3/E5/E6 |
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
| `scripts/publish_w2_static_report.py` | `MANUAL_OPS` | A-151 static report runbook | operator → script | ops | 是 | A-151_STATIC_REPORT_WEB_ROOT | `KEEP` | E3/E4/E5 |
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
| `scripts/run_xg_history_backfill.py` | `RUNTIME_ENTRYPOINT` | apps/worker/celery_app.py | worker → task | runtime | 否 | 无 | `KEEP` | E1/E3/E6 |
| `scripts/seed_competition_runtime_authority.py` | `MIGRATION_ONLY` | migration 0037 | Alembic → seed | migration | 否 | 无 | `KEEP` | E5/E6 |
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

分类汇总：

```text
RUNTIME_ENTRYPOINT = 9
CI_DIRECT = 7
CI_TRANSITIVE = 29
DEPLOYMENT = 11
MANUAL_OPS = 68
MIGRATION_ONLY = 3
ONE_TIME_RECOVERY = 10
DEAD = 8
TOTAL_BASELINE = 145
TOTAL_RETAINED = 137
```

### `check_w2_all.py` 完整直接与传递调用图

AST 守卫读取 `COMMANDS` 字面量，并递归扫描每个子脚本的
`subprocess.run/Popen/check_*`、`runpy`、`os.system` 与 `scripts.*` import。
最终执行图如下：

```text
.github/workflows/ci.yml
└── scripts/check_w2_all.py
    ├── scripts/check_w2_stage1_contracts.py
    ├── scripts/check_w2_stage3_data_model.py
    ├── scripts/check_w2_stage4_ingestion.py
    ├── scripts/check_w2_stage4b_live_smoke.py
    ├── scripts/check_w2_stage5_asof.py
    ├── scripts/check_w2_stage5b.py
    ├── scripts/check_w2_stage6_market.py
    ├── scripts/check_w2_stage7_models.py
    ├── scripts/check_w2_stage8_replay.py
    ├── scripts/check_w2_stage7b.py
    ├── scripts/check_w2_stage7c.py
    ├── scripts/check_w2_stage7d.py
    ├── scripts/check_w2_stage7e.py
    ├── scripts/check_w2_stage10a.py
    ├── scripts/check_w2_stage11a.py
    ├── scripts/check_w2_stage12a.py
    ├── scripts/check_w2_stage13a.py
    ├── scripts/check_w2_stage14a.py
    └── scripts/check_w2_stage15a.py
```

19 个直接子节点均无 subprocess/runpy/importlib/Shell 执行子节点；部分 checker
会读取 `run_*` 源码或检查文件存在性，但不会执行该脚本，故不伪记为传递执行。
去重前，`check_w2_all.py` 还直接执行 Boss Console、tracked-output、Ruff、
Mypy、Pytest；去重后前两项仍由 GitHub CI 独立直接执行，后三项唯一重测试
owner 为 GitHub CI：

```text
CHECK_W2_ALL_RUFF_INVOCATIONS = 0
CHECK_W2_ALL_MYPY_INVOCATIONS = 0
CHECK_W2_ALL_PYTEST_INVOCATIONS = 0
CI_RUFF_OWNER = GITHUB_CI (.github/workflows/ci.yml:77)
CI_MYPY_OWNER = GITHUB_CI (.github/workflows/ci.yml:79)
CI_PYTEST_OWNER = GITHUB_CI (.github/workflows/ci.yml:81)
```

### DEAD 删除证据

对下列 8 个脚本逐项扫描 Python/import/subprocess、Shell、GitHub CI、
Dockerfile/Compose、systemd/cron、`pyproject`、tests、运维文档，直接调用
均为 0；不能只依据“代码引用 0”，第二列同时给出失效业务合同或现行替代：

| DEAD 脚本 | 失效/替代直接证据 |
|---|---|
| `scripts/check_dashboard_v2_baseline.py` | 旧 Dashboard V2 manifest 只有该脚本读取；现行 CI 使用 `check_boss_console_baseline.py` 与 Boss Console V2 权威 |
| `scripts/check_w2_stage6b.py` | 强制读取的 4 个 `reports/W2_STAGE6B_*` 产物全部不存在；reports 已退出生产/CI 权威 |
| `scripts/check_w2_stage7f.py` | 强制读取的 `archive/scripts/run_stage7f_gate4_checkpoint.py` 与 archive reports 全部不存在 |
| `scripts/check_w2_stage7g.py` | 强制读取的 `archive/scripts/run_stage7g_continuity_audit.py` 及 Stage7G reports 不存在 |
| `scripts/check_w2_stage9b.py` | 唯一输入 `reports/W2_STAGE9B_SHADOW_OPERATIONS.json` 不存在 |
| `scripts/check_w2_stage10b.py` | 无任何执行入口；现行同源/API、打包、正式推荐关闭合同由 Boss Console、runtime entrypoint 与 Stage10 单元/合同测试持续覆盖 |
| `scripts/check_w2_stage10d.py` | 强制读取的 4 个 `reports/W2_STAGE10D_*` 产物全部不存在；时区/coverage 由 `test_stage10d_beijing_matchday.py` 等当前测试覆盖 |
| `scripts/check_w2_stage12b.py` | 唯一输入 `reports/W2_STAGE12B_W1_W2_COMPARISON.json` 不存在；生成 CLI 仍按人工 ops 身份保留 |

同时删除只服务旧 Dashboard V2 守卫的
`docs/ui/dashboard-v2/DASHBOARD_V2_VISUAL_BASELINE_MANIFEST.json`。删除合计
`9` 个文件、`609` 行、`23630` 字节；其中 DEAD 脚本 `8` 个、`547` 行、
`21266` 字节。删除后上述 9 个路径在矩阵与静态守卫之外的全仓库引用均为 0。

### 本地实现验收

```text
SCRIPT_INVENTORY_COVERAGE = 100_PERCENT
UNCLASSIFIED_SCRIPTS = 0
MULTI_CLASSIFIED_SCRIPTS = 0
DEAD_SCRIPTS_RETAINED = 0
NON_DEAD_SCRIPTS_DELETED = 0
SCRIPTS_ARCHIVE_DIRECTORIES = 0
BROKEN_SCRIPT_REFERENCES = 0
CHECK_W2_ALL_DIRECT_CHILDREN = 19
CHECK_W2_ALL_TRANSITIVE_CHILDREN = 0
CHECK_W2_ALL_RUFF_INVOCATIONS = 0
CHECK_W2_ALL_MYPY_INVOCATIONS = 0
CHECK_W2_ALL_PYTEST_INVOCATIONS = 0
CI_RUFF_OWNER = GITHUB_CI
CI_MYPY_OWNER = GITHUB_CI
CI_PYTEST_OWNER = GITHUB_CI
CHECK_W2_ALL = PASS
INVENTORY_CONTRACT_TESTS = 8_PASS
RUFF = PASS
MYPY = PASS (260 source files)
PYTEST = 1492_PASS_4_SKIP
GIT_DIFF_CHECK = PASS
SHELL_SYNTAX = PASS
PRODUCTION_BEHAVIOR_CHANGED = false
DATABASE_SCHEMA_CHANGED = false
SAFETY_SWITCHES_CHANGED = false
STAGING = NOT_APPLICABLE
```

每个脚本必须逐项归入且只能归入以下一种分类：

```text
RUNTIME_ENTRYPOINT
CI_DIRECT
CI_TRANSITIVE
DEPLOYMENT
MANUAL_OPS
MIGRATION_ONLY
ONE_TIME_RECOVERY
DEAD
```

只有证据充分的 `DEAD` 脚本可以直接删除。不得以移动到 archive、重命名或
增加兼容入口代替删除；其他类别必须记录实际调用方和证据。

- [ ] 全量扫描 GitHub CI、`check_w2_all.py`、Dockerfile、Compose、
  systemd/cron、Python `subprocess`、Shell 调用、`pyproject` entrypoint
  以及运维文档。
- [ ] 为每个脚本记录分类、直接/传递调用方、运行环境、删除或保留决定和
  证据。
- [ ] 只有 `DEAD` 可连同无效引用和测试直接删除；不建立
  `scripts/archive/`。
- [ ] `check_w2_all.py` 只运行 W2 stage/contract checker。
- [ ] GitHub CI 单独负责 Ruff、Mypy、Pytest。
- [ ] 禁止 `check_w2_all.py` 与 GitHub CI 重复执行 Ruff、Mypy、Pytest
  三项重测试。
- [ ] 完整 CI 通过并合并。

---

## ARCH-P1-04：Dashboard 单一 Read Model（拆为 04A / 04B / 04C）

老板已决定使用现有 `read_model_checkpoint` 作为唯一页面投影。原 ARCH-P1-04
按 2026-07-23 批准的决定拆为三个独立 PR，三者合起来等价于原任务范围，且
每个都可独立回滚：

```text
ARCH-P1-04A  写侧管线：worker 产出并投影评估，只做影子对账，不切读路径
ARCH-P1-04B  读切换：Dashboard 只读投影，删除全部生产 fallback
ARCH-P1-04C  合同层与死代码清理：删除 legacy 决策合同与无调用方计算方法
```

拆分不放宽任何原验收项；原 ARCH-P1-04 的两条验收在 04B 完成时判定。

### 已知依赖循环 baseline 与关闭责任

```text
KNOWN_DEPENDENCY_CYCLE_BASELINE = api <-> ingestion
```

- `ARCH-P1-04A`：不得新增 `worker/ingestion -> api` 依赖；写侧投影逻辑不得
  继续放在 API 包中。
- `ARCH-P1-04B`：删除 `api -> ingestion/features/markets/pricing/strategy/
  simulation` 的读时计算依赖。
- `ARCH-P1-04C`：加入 `DEPENDENCY_CONTRACT_V1`；将 `api <-> ingestion`
  循环归零；增加 AST import graph 静态守卫并禁止新增循环依赖。

#### `DEPENDENCY_CONTRACT_V1` 分层规则

```text
LAYER_ORDER = apps -> dashboard/presentation -> api -> infrastructure -> domain
```

下层不得反向依赖上层；`apps` 只在 composition root 中组装各层。分层合同如下：

- `domain`（`src/w2/domain`）：只承载领域模型、值对象和纯业务合同；除标准库
  与第三方纯计算依赖外，不得 import `infrastructure`、`api`、
  `dashboard/presentation` 或 `apps`。
- `infrastructure`（`src/w2/infrastructure`）：实现持久化和外部系统 adapter，
  可以 import `domain`；明确不得 import `w2.api`、`w2.dashboard` 或
  仓库根目录 `apps`。
- `api`（`src/w2/api`）：只负责读模型、应用服务编排和 API 合同，可以 import
  `domain` 与 `infrastructure`，不得 import `w2.dashboard` 或 `apps`；按
  `ARCH-P1-04B` 删除对
  `ingestion/features/markets/pricing/strategy/simulation` 的读时计算依赖。
- `dashboard/presentation`（`src/w2/dashboard` 及 presentation 代码）：只可
  依赖 `api` 的公开读/应用合同与 `domain` 值合同，不得依赖
  `infrastructure` 内部实现或 `apps`，不得形成读时计算权威。
- `apps`（仓库根目录 `apps/`）：只作为进程入口和 composition root，可以向下
  import `dashboard/presentation`、`api`、`infrastructure`、`domain` 并完成
  依赖注入，不得承载可复用领域规则或另建业务权威；任何 `src/w2` 包均不得
  反向 import `apps`。

`ARCH-P1-04C` 的 AST import graph 守卫必须覆盖普通 import、from import 和
相对 import，并显式扫描 `domain`、`infrastructure`、`api`、
`dashboard/presentation` 与 `apps`；将所有违反上述方向的边归零。不得以宽泛
allowlist 固化违规边，并必须阻止新增分层反向依赖或循环。

---

## ARCH-P1-04A：评估持久化——写侧管线

**独立 PR。本任务不切换任何读路径。**

### 现状锚点（2026-07-23 复审）

```text
EVALUATION_TABLE            = dynamic_prematch_evaluations (已存在)
PROJECTION_TABLE            = read_model_checkpoint (已存在)
REPOSITORY                  = src/w2/prematch/repository.py
ORM                         = src/w2/infrastructure/persistence/api_models.py
PROJECTOR                   = src/w2/api/dashboard_read_models.py (已实现但休眠)
PROJECTOR_ONLY_CALLER_TODAY = scripts/project_stage10b_live_snapshot.py (离线)
```

两张表和 repository 均已存在，投影器代码也已写好，当前唯一调用方是离线
脚本。本任务是把已有投影器接入 worker 生产链路，**不新增表**。

- [ ] 审计 `read_model_checkpoint` 的 schema、写入者和当前覆盖。
- [ ] 确保它可以承载 Boss Console 当前所需全部字段。
- [ ] worker 在赔率、首发或赛程变化后计算分析卡，落
  `dynamic_prematch_evaluations`，并投影到 `read_model_checkpoint`。
- [ ] 投影记录必须带 projection version/hash、source event、
  last projected time。
- [ ] 不新增表、不新增配置文件、不新增 fallback。
- [ ] 影子对账：投影结果与现行读时计算结果逐场 hash 比对，不切换 API
  读路径。
- [ ] 投影随赔率/首发变化自动更新，不依赖人工 materialize 或离线脚本。
- [ ] 不得新增 `worker/ingestion -> api` 依赖；把写侧投影逻辑从 API 包移入
  写侧权威包，禁止继续放在 API 包中。
- [ ] 完整 CI 与 staging 验收通过。
- [ ] PR 合并。

**验收**

```text
PROJECTION_SHADOW_RECONCILIATION = 100_PERCENT_HASH_MATCH
PROJECTION_TRIGGERED_BY_EVENT = TRUE
MANUAL_MATERIALIZE_REQUIRED = FALSE
NEW_TABLES = 0
NEW_WORKER_INGESTION_TO_API_DEPENDENCIES = 0
WRITE_SIDE_PROJECTION_LOGIC_IN_API = 0
```

---

## ARCH-P1-04B：Dashboard 读切换 + 删除全部生产 fallback

**独立 PR。这是行为切换，必须有 staging 语义对账。**

- [ ] 所有 Dashboard 与分析生产端点只读 `read_model_checkpoint` 投影。
- [ ] 删除：
  - seed fallback；
  - legacy fallback；
  - runtime JSON fallback（含 `prediction_locks.json`、`result_events.json`
    两处残留）；
  - reports fallback；
  - live/frozen 自动选择（`_uses_frozen_public_authority` 链路）；
  - API 读路径里的特征组装、Poisson 与模拟调用；
  - 前端市场概率重算。
- [ ] **fail-closed 语义**：`src/w2/api/repository.py` 在
  `main@76201af` 上有 25 处 `except Exception`、58 处 `except` 子句，
  多数静默返回空集。"异常吞成空数据"计入 fallback；数据库故障必须返回
  `SYSTEM_DEGRADED` 一类的明确状态，不得返回空集冒充"无数据"。逐处分类，
  并给出改造后各处的返回语义。
- [ ] 新增静态守卫测试（照 `tests/contract/test_production_report_reads.py`
  的模式）：禁止 `src/w2/api`、`apps/api` import 特征引擎、pricing 或
  simulation。
- [ ] frozen artifact 仅保留内部审计/canary。
- [ ] API 返回 projection version/hash、source event、last projected time。
- [ ] 删除 `api -> ingestion/features/markets/pricing/strategy/simulation` 的
  全部读时计算依赖。
- [ ] old/new 全部当前比赛语义对账。
- [ ] 15/30 场 Dashboard 行为和视觉不退化。
- [ ] 完整 CI 与 staging 验收通过。
- [ ] PR 合并。

**验收**

```text
DASHBOARD_READ_AUTHORITY = READ_MODEL_CHECKPOINT_ONLY
PRODUCTION_FALLBACK_COUNT = 0
IMPLICIT_EMPTY_RESULT_FALLBACK_COUNT = 0
API_FEATURE_PRICING_SIMULATION_IMPORTS = 0
API_TO_READ_TIME_COMPUTATION_DEPENDENCIES = 0
```

---

## ARCH-P1-04C：合同层与死代码清理

**独立 PR。这是删除，必须每处附零引用证据。**

与 04B 分开的原因：04B 是行为切换，需要 staging 对账；04C 是删除，需要
零引用证据；两者回滚粒度不同。

### 现状锚点（2026-07-23 复审）

口径为 `main@76201af8aad43976ffbcd7d2f72726bac4bc8106` 实测。

```text
LEGACY_SHIM    = src/w2/domain/legacy_decision_shim.py (113 行)
LEGACY_ADAPTER = src/w2/domain/decision_adapter.py (986 行)
LEGACY_LOC     = 1099 行合计
REPOSITORY     = src/w2/api/repository.py
                 6770 行 / 233 个类方法 / 256 个 def（含嵌套）
```

- [ ] 删除 `legacy_decision_shim.py` 与 `decision_adapter.py` 中的旧合同
  转换，使 `RecommendationDecisionV3` 成为投影的唯一输出格式。
- [ ] 删除 `src/w2/api/repository.py` 中已无调用方的计算方法，使该文件
  收敛为纯投影读取器体量。
- [ ] 每一处删除附零引用证据（静态扫描 `src/`、`apps/`、`scripts/`、
  `tests/`、`config/`、`infra/` 与 CI）。
- [ ] 不引入替代 shim、兼容层或 adapter。
- [ ] 加入 `DEPENDENCY_CONTRACT_V1`，以 AST import graph 静态守卫覆盖
  `src/w2` 一级包依赖。
- [ ] 将已知 `api <-> ingestion` 循环归零，并禁止新增任何循环依赖。
- [ ] 完整 CI 与 staging 验收通过。
- [ ] PR 合并。

**验收**

```text
LEGACY_DECISION_CONTRACT_LOC = 0
DECISION_OUTPUT_FORMAT_COUNT = 1
UNREFERENCED_REPOSITORY_COMPUTE_METHODS = 0
DEPENDENCY_CONTRACT = DEPENDENCY_CONTRACT_V1
DOMAIN_TO_INFRASTRUCTURE_API_DASHBOARD_APPS = 0
INFRASTRUCTURE_TO_API_DASHBOARD_APPS = 0
API_TO_DASHBOARD_APPS = 0
DASHBOARD_PRESENTATION_TO_INFRASTRUCTURE_APPS = 0
SRC_W2_TO_APPS = 0
APPS_BUSINESS_AUTHORITY_COUNT = 0
API_INGESTION_CYCLE_COUNT = 0
NEW_DEPENDENCY_CYCLES = 0
```

---

## ARCH-P1-03：球队身份 Crosswalk 收敛

**顺序说明**：按 2026-07-23 批准的决定，本任务从 ARCH-P1-02 之后移到
ARCH-P1-04C 之后。范围不变。

### 现状锚点（2026-07-23 复审）

待收敛组：

```text
football_data_team_crosswalks
team_identity_crosswalks
provider_team_identity_crosswalks
player_identity_crosswalks
player_identity_mappings
```

### 允许的顺序回退

若执行 ARCH-P1-04A 时发现身份不一致阻塞投影对账，向老板申请把本任务提前。
这是本清单中唯一允许的顺序回退，需要单独批准，不在预批准范围内。

- [ ] 盘点全部球队身份和 provider crosswalk 表。
- [ ] 指定 canonical team 体系为唯一权威。
- [ ] 迁移有效映射及 review provenance。
- [ ] 其他 crosswalk 在有效映射迁移及对账完成后停止写入，并在同一 PR
  删除代码引用与正式 drop；证据不足的表保持原状继续调查。
- [ ] provider IDs 仅作 provenance，不再作为模型主身份。
- [ ] 完成 fixture、history、rating、lineup 读取对账。
- [ ] 新增 drop migration 的 `upgrade()` 对每张待删表先 `SELECT count(*)`，
  非零即抛错。
- [ ] PR 合并。

**验收**

```text
CANONICAL_TEAM_IDENTITY_AUTHORITY_COUNT = 1
```

---

## ARCH-P1-05：部署改为 CI 构建、服务器拉镜像

### 条件提前开关（2026-07-23 预批准）

若 ARCH-P1-04 系列的 staging 验收因服务器现场构建（网络或软件源不稳定）
反复失败，执行方可直接把本任务提到 ARCH-P1-04A 之前执行，无需再次请示。
提前执行时必须在此处记录：

```text
EARLY_EXECUTION_TRIGGERED = <yes/no>
TRIGGER_REASON =
TRIGGERED_AT =
```

当前状态：`EARLY_EXECUTION_TRIGGERED = no`。

### 范围

当前仓库根有 5 个 Dockerfile：`Dockerfile.api`、`Dockerfile.worker`、
`Dockerfile.scheduler`、`Dockerfile.migrations`、`Dockerfile.web`。Python 侧
4 个合并为单镜像多 command，Web 保留独立镜像。

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

## ARCH-P1-07：竞赛域读路径修正

**2026-07-23 新增的小任务，独立 PR。**

`src/w2/competitions/league_whitelist_scope.py` 的模块级常量
（`TOP_FIVE_COMPETITIONS` 等）在 import 时查库，造成两个问题：

1. 导入方在没有已种子数据库的环境直接抛错；
2. 常量在进程存活期内不随 DB `enabled` 热切换刷新，削弱 ARCH-P0-03
   "改库即生效"的承诺。

- [ ] 把模块级查库常量改为函数调用，取消 import 时的数据库访问。
- [ ] 保持 ARCH-P0-03 的 DB 权威语义不变：不引入缓存旁路，不引入新的
  运行时权威或环境变量覆盖。
- [ ] 核查 audit/backtest 导入链上的其他 import-time 副作用并一并修正。
- [ ] 新增回归测试：无数据库连接时 import 成功；DB `enabled` 变更后同一
  进程内下一次调用即生效。
- [ ] 完整 CI 与 staging 验收通过。
- [ ] PR 合并。

**验收**

```text
IMPORT_TIME_DB_ACCESS_COUNT = 0
DB_ENABLED_HOT_CHANGE_EFFECTIVE_WITHOUT_RESTART = PASS
```

---

## ARCH-P1-08：P1 总验收

- [ ] 一套赔率历史。
- [ ] 一套当前盘口投影。
- [ ] 一套 canonical team identity。
- [ ] Dashboard 单一 read model。
- [ ] CI 镜像发布。
- [ ] 服务器 pull-only。
- [ ] 无生产 fallback。
- [ ] API 层无特征引擎、pricing、simulation import，静态守卫常绿。
- [ ] 读路径 fail-closed，无隐式空数据 fallback。
- [ ] legacy 决策合同代码为零。
- [ ] P1 完整 CI 与 staging 验收通过。
- [ ] 人工验收。

**完成标准**

```text
P1_ARCHITECTURE_CONVERGENCE_PASS
API_FEATURE_PRICING_SIMULATION_IMPORTS = 0
IMPLICIT_EMPTY_RESULT_FALLBACK_COUNT = 0
LEGACY_DECISION_CONTRACT_LOC = 0
```

---

# 阶段 P2：卫生治理，可穿插但不得抢占 P0/P1

## ARCH-P2-01：Scripts 整理（已取代）

```text
Status: SUPERSEDED_BY_ARCH_HYGIENE_02
```

原 scripts/archive 方案已删除，不再执行。脚本权威盘点、分类及证据化直接删除
统一由 `ARCH-HYGIENE-02` 完成；确认无用的 `DEAD` 脚本必须直接删除，不建立
archive。

---

## ARCH-P2-02：Docs 整理

```text
Scope: HUMAN_MAINTAINED_DOCUMENTS_ONLY
Generated audit artifacts owner: ARCH-HYGIENE-01
```

本任务只处理人工编写和人工维护的文档。机器生成的审计产物、其别名、生成器
及输出目录治理全部且仅归 `ARCH-HYGIENE-01`，不得在 P2-02 重复处理。

- [ ] 只盘点人工维护文档；人工编写的日期型一次性证据移入
  `docs/archive/`。
- [ ] 同一审计只保留最新权威版本。
- [ ] 旧文档添加 `SUPERSEDED_BY`。
- [ ] 不删除仍有审计价值的历史证据。
- [ ] 不修改、移动或删除机器生成审计产物及其生成器。
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
- [ ] 压缩本总清单的任务回执：每个任务只保留 CI run 号、merge SHA 和
  一行结论，细节留在 PR 描述中（2026-07-23 追加）。
- [ ] PR 合并。

---

## ARCH-P2-06：`src/w2` 一级包角色与依赖矩阵

对 `src/w2` 的全部一级包生成并维护一张逐包矩阵，字段必须完整：

```text
package
runtime callers
ops callers
test callers
incoming dependencies
outgoing dependencies
cycles
image inclusion
role
decision
evidence
```

`role` 只能取以下值之一：

```text
CORE
ADAPTER
OFFLINE_TOOL
TEST_SUPPORT
DEAD
```

- [ ] 矩阵覆盖 `src/w2` 全部一级包，不允许抽样。
- [ ] 运行时、运维、测试调用方及入向/出向依赖均有直接证据。
- [ ] 记录每个包所在依赖循环及生产镜像是否包含该包。
- [ ] `replay`、`data_assets`、`migration`、`audit_export` 先标记为
  `OFFLINE_TOOL` 候选并继续调查，不得直接判为 `DEAD`。
- [ ] 每个保留或删除决定均附可复核证据；只有证据充分的 `DEAD` 可删除。
- [ ] 完整 CI 通过并合并。

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
