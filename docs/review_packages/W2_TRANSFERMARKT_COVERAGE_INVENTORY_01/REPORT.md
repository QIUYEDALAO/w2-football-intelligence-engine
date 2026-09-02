# W2-TRANSFERMARKT-COVERAGE-INVENTORY

状态：`DONE_READ_ONLY_INVENTORY / NO_MATERIALIZATION`

## 1. 资产与分析环境

- 唯一访问 URL：`https://pub-e682421888d945d684bcae8890b0ec20.r2.dev/data/transfermarkt-datasets.duckdb`
- HTTP：`200`；下载 `211,038,208` bytes；耗时 `136.591977s`
- SHA-256：`808959f5b5b16bb698180c348b269d9ec26e1d1a5538767ffe9d971b96796d1c`
- `Last-Modified`：`2026-08-05T07:15:17Z`
- ETag：`ec6e1ca92499b22f604c2f179515477f-26`
- 最终存储：`/Users/liudehua/.hermes/private/w2-tm-coverage-inventory-01/transfermarkt-datasets.duckdb`，位于 Git worktree 之外，保持私有未跟踪；没有复制进仓库。

与 2026-07-22 审计资产相比，size 从 `204,746,752` 增至 `211,038,208`（`+6,291,456` bytes，`+3.07%`），SHA、Last-Modified、ETag 均变化，确认上游资产已更新。没有访问 R2 root 之外的 URL。

DuckDB 最初用 `uv venv .local/duckdb-venv --python 3.12` 创建本任务私有忽略环境，再以 `uv pip install --python .local/duckdb-venv/bin/python duckdb==1.5.4` 安装；实测 `duckdb.__version__ == 1.5.4`。全量测试发现仓库的 secret guard 会扫描 ignored binary 后，资产和分析 venv 一并迁至仓外私有目录 `/Users/liudehua/.hermes/private/w2-tm-coverage-inventory-01/`，随后 guard 单测通过。`pyproject.toml`、`uv.lock` 均未改变。资产以 `duckdb.connect(..., read_only=True)` 打开，`SHOW TABLES` 仍含既有审计列出的 13 张表。

## 2. 13 个 ACTIVE 联赛与 Transfermarkt 对应

联赛清单来自当前生产 VPS PostgreSQL 的 `league_season JOIN league_profile`，查询包裹在 `BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY ... ROLLBACK` 中；实测 13 行、均为 season `2026` / lifecycle `ACTIVE`。

| W2 competition_id | 生产名称 | 国家 | Transfermarkt competition_id | 对应状态 |
|---|---|---|---|---|
| allsvenskan | Allsvenskan | Sweden | `SE1` | 明确对应 |
| argentina_primera | Liga Profesional de Futbol | Argentina | `ARG1` | 明确对应 |
| brasileirao_serie_a | Campeonato Brasileiro Serie A | Brazil | `BRA1` | 明确对应 |
| bundesliga | Bundesliga | Germany | `L1` | 明确对应 |
| chinese_super_league | Chinese Super League | China | — | **无 Transfermarkt 对应** |
| eliteserien | Eliteserien | Norway | `NO1` | 明确对应 |
| eredivisie | Eredivisie | Netherlands | `NL1` | 明确对应 |
| la_liga | La Liga | Spain | `ES1` | 明确对应 |
| ligue_1 | Ligue 1 | France | `FR1` | 明确对应 |
| mls | Major League Soccer | United States | `MLS1` | 明确对应 |
| premier_league | Premier League | England | `GB1` | 明确对应 |
| primeira_liga | Primeira Liga | Portugal | `PO1` | 明确对应 |
| serie_a | Serie A | Italy | `IT1` | 明确对应 |

俱乐部“W2 对得上”只做本次只读统计：将生产 2026 fixture identity 涉及的 W2 canonical team 名称，与 Transfermarkt `clubs.name/club_code` 人工核验为单一明确同队；不保存映射、不建立对照表。未命中项是：Bundesliga `SV Elversberg`、La Liga `Racing Santander`、Ligue 1 `Le Mans`、Premier League `Coventry`、Primeira Liga `Academico Viseu`。其余能对应联赛的当前 W2 球队均可明确识别；中超因 competition 不存在不继续猜测。

## 3. 严格可算口径

本报告同时给出三个递进计数：

1. **阵容可还原**：一场比赛的主客队各恰好 11 条 `starting_lineup`，双方均有 substitute 行，所有 lineup player ID 非空。这是从实际出场名单得到的历史比赛阵容，不声称等于赛季注册 roster。
2. **整队身价严格可算**：在阵容可还原基础上，该场双方所有 `game_lineups` 球员逐人都有比赛日或更早的正数 valuation，且最近日期没有冲突。
3. **首发身价严格可算**：在阵容可还原基础上，双方各 11 名首发逐人满足同一 as-of 正数、无冲突条件。

任一球员缺 valuation 或最近日期存在多个不同 valuation，整场即失败；没有使用“大部分球员有值”口径。百分比统一以该联赛 `games` 全量为分母；括号内同时说明阵容已可还原样本中的命中情况。

## 4. 逐联赛盘点

| 联赛 / TM ID | competitions | clubs / W2 当前队可明确匹配 | games / 日期跨度 | game_lineups：行 / 场 / 首发 / 替补 / 日期跨度 | player_valuations：行 / 球员 / 日期跨度 | 阵容可还原 | 整队身价严格可算 | 首发身价严格可算 |
|---|---:|---:|---|---|---|---:|---:|---:|
| Allsvenskan `SE1` | 是 | 19 / 16/16 | 329 / 2025-03-29→2026-07-06 | 9,664 / 243 / 5,346 / 4,318 / 2025-03-29→2026-07-06 | 5,171 / 734 / 2006-02-03→2026-06-05 | 243/329 (73.86%) | 3/329 (0.91%；阵容内 1.23%) | 62/329 (18.84%；阵容内 25.51%) |
| Argentina Primera `ARG1` | 是 | 32 / 30/30 | 418 / 2025-01-24→2026-05-05 | 16,875 / 368 / 8,096 / 8,779 / 2025-01-24→2026-05-05 | 9,856 / 1,251 / 2004-10-04→2026-05-22 | 368/418 (88.04%) | 20/418 (4.78%；阵容内 5.43%) | 170/418 (40.67%；阵容内 46.20%) |
| Brasileirao `BRA1` | 是 | 24 / 20/20 | 557 / 2025-03-29→2026-06-01 | 25,501 / 557 / 12,254 / 13,247 / 2025-03-29→2026-06-01 | 9,995 / 1,220 / 2004-10-04→2026-05-26 | 557/557 (100.00%) | 14/557 (2.51%；阵容内 2.51%) | 217/557 (38.96%；阵容内 38.96%) |
| Bundesliga `L1` | 是 | 31 / 17/18 | 4,284 / 2012-08-24→2026-05-16 | 151,144 / 3,978 / 87,516 / 63,628 / 2013-08-09→2026-05-16 | 37,049 / 2,628 / 2004-10-04→2026-06-01 | 3,978/4,284 (92.86%) | 3,344/4,284 (78.06%；阵容内 84.06%) | 3,913/4,284 (91.34%；阵容内 98.37%) |
| Chinese Super League | 否 | 0 / 0/16 | 0 / — | 0 / 0 / 0 / 0 / — | 0 / 0 / — | 0 | 0 | 0 |
| Eliteserien `NO1` | 是 | 19 / 16/16 | 329 / 2025-03-29→2026-05-30 | 10,131 / 258 / 5,676 / 4,455 / 2025-03-29→2026-05-30 | 4,354 / 708 / 2008-07-03→2026-05-29 | 258/329 (78.42%) | 14/329 (4.26%；阵容内 5.43%) | 104/329 (31.61%；阵容内 40.31%) |
| Eredivisie `NL1` | 是 | 29 / 18/18 | 4,210 / 2012-08-10→2026-05-17 | 159,175 / 3,894 / 85,668 / 73,507 / 2013-08-02→2026-05-17 | 29,861 / 2,777 / 2004-10-04→2026-05-28 | 3,894/4,210 (92.49%) | 2,037/4,210 (48.38%；阵容内 52.31%) | 3,725/4,210 (88.48%；阵容内 95.66%) |
| La Liga `ES1` | 是 | 33 / 19/20 | 5,320 / 2012-08-18→2026-05-24 | 195,454 / 4,891 / 107,583 / 87,871 / 2013-08-17→2026-05-24 | 37,559 / 2,708 / 2004-10-04→2026-06-05 | 4,889/5,320 (91.90%) | 3,032/5,320 (56.99%；阵容内 62.02%) | 4,618/5,320 (86.80%；阵容内 94.46%) |
| Ligue 1 `FR1` | 是 | 36 / 17/18 | 4,997 / 2012-08-10→2026-05-17 | 173,728 / 4,613 / 101,486 / 72,242 / 2013-08-09→2026-05-17 | 33,562 / 3,013 / 2004-10-04→2026-06-01 | 4,613/4,997 (92.32%) | 2,074/4,997 (41.50%；阵容内 44.96%) | 4,136/4,997 (82.77%；阵容内 89.66%) |
| MLS `MLS1` | 是 | 30 / 30/30 | 727 / 2025-02-22→2026-05-25 | 22,820 / 574 / 12,628 / 10,192 / 2025-02-22→2026-05-25 | 9,351 / 1,255 / 2004-10-04→2026-06-02 | 574/727 (78.95%) | 101/727 (13.89%；阵容内 17.60%) | 318/727 (43.74%；阵容内 55.40%) |
| Premier League `GB1` | 是 | 37 / 19/20 | 5,320 / 2012-08-18→2026-05-24 | 186,646 / 4,940 / 108,680 / 77,966 / 2013-08-17→2026-05-24 | 33,743 / 2,933 / 2003-12-15→2026-06-03 | 4,940/5,320 (92.86%) | 2,687/5,320 (50.51%；阵容内 54.39%) | 4,680/5,320 (87.97%；阵容内 94.74%) |
| Primeira Liga `PO1` | 是 | 35 / 17/18 | 4,152 / 2012-08-17→2026-05-16 | 145,195 / 3,830 / 84,225 / 60,970 / 2013-08-16→2026-05-16 | 30,927 / 3,107 / 2004-10-04→2026-05-28 | 3,824/4,152 (92.10%) | 2,203/4,152 (53.06%；阵容内 57.61%) | 3,307/4,152 (79.65%；阵容内 86.48%) |
| Serie A `IT1` | 是 | 39 / 20/20 | 5,320 / 2012-08-25→2026-05-24 | 222,611 / 4,939 / 108,658 / 113,953 / 2013-08-24→2026-05-24 | 50,413 / 3,752 / 2004-10-04→2026-06-05 | 4,939/5,320 (92.84%) | 3,243/5,320 (60.96%；阵容内 65.66%) | 4,902/5,320 (92.14%；阵容内 99.25%) |

La Liga 的 lineup distinct games 为 4,891，但 2 场没有满足双方完整结构，因此阵容可还原为 4,889；Primeira Liga 同理为 3,830 与 3,824。所有统计来自只读 DuckDB 查询。

## 5. 结论

为避免“足以”变成主观包装，本盘点采用保守的投入判断带：严格全联赛 games 分母可算率 `>=70%` 记为“足以直接支撑下一步”；`50%–<70%` 记为“有价值但需限定 cohort”；`<50%` 记为“不足”。这只是是否值得继续做映射工程的盘点带，不是模型准入门，也未改变任何冻结阈值。

### 整队身价

- **足以直接支撑**：Bundesliga（78.06%）。
- **有价值但需限定 cohort**：La Liga（56.99%）、Premier League（50.51%）、Primeira Liga（53.06%）、Serie A（60.96%）。
- **不足**：Allsvenskan、Argentina Primera、Brasileirao、Eliteserien、Eredivisie、Ligue 1、MLS；Chinese Super League 为 0。

这里不能把 92% 左右的 lineup source coverage 直接写成整队身价可算：荷甲和法甲虽可还原阵容很多，但全名单逐人 as-of valuation 严格率仍只有 48.38%/41.50%。

### 首发身价

- **足以直接支撑**：Bundesliga、Eredivisie、La Liga、Ligue 1、Premier League、Primeira Liga、Serie A（79.65%–92.14%）。
- **不足**：Allsvenskan、Argentina Primera、Brasileirao、Eliteserien、MLS（18.84%–43.74%）；Chinese Super League 为 0。

### 0 与低覆盖的卡点

- Chinese Super League：无 competition，所以下游 clubs/games/lineups/valuations 全部不可盘点，严格率 0。
- Allsvenskan、Argentina Primera、Brasileirao、Eliteserien、MLS：不是无 lineup；主要卡在比赛日期之前找不到每名球员的 valuation，整份名单比首发更容易因一个替补缺值而全场失败。
- 欧洲 7 联赛首发覆盖强；剩余缺口仍是个别球员 as-of valuation，而不是需要用当前值回填历史。
- 当前 W2 2026 队伍对 Transfermarkt clubs 的名称识别缺口仅 5 队，但这只是盘点，不等于经审核的 identity mapping；不能据此直接物化。

### 是否值得投入对照表

**值得，但只值得分层投入，不值得一次性做 13 联赛全量对照。** 第一优先应是 7 个首发严格率 >=70% 的欧洲联赛；其中 Bundesliga 同时具备高整队率。La Liga、Premier League、Primeira Liga、Serie A 的整队 cohort 也有 50%–61%，可在明确限定日期/cohort 后评估。瑞超、阿甲、巴甲、挪超、MLS 的整队率仅 0.91%–13.89%，当前不值得先做整队对照；中超在源头无 competition，更不应投入映射。

结论没有放宽 all-or-nothing：**大多数联赛（12 个有对应中的 11 个）当前都不足以直接支撑严格整队身价；首发则有 7 个联赛足以。**

## 6. 验证

- 全量：`2949 passed / 9 skipped / 5 failed / 5 warnings`，耗时 `387.44s`。
- 5 个失败均在父提交 `1de3c1ef554d00a408577f59f4864e04f1d341da` 以相同 node ID 复现：
  - `tests/contract/test_compose_env_dedup.py::test_compose_expansion_matches_authorized_runtime_delta[path0]`：宿主 Docker 无 Compose 插件。
  - `tests/contract/test_compose_env_dedup.py::test_compose_expansion_matches_authorized_runtime_delta[path1]`：宿主 Docker 无 Compose 插件。
  - `tests/contract/test_sc18_input_authority.py::test_sc18_authority_artifacts_are_complete_and_self_checking`：宿主无裸 `python` 命令。
  - `tests/integration/test_future_refresh_staging_parity.py::test_preflight_fails_root_0700_runtime_for_worker_uid`：macOS 宿主无法按测试要求建立 Linux UID/GID ownership。
  - `tests/integration/test_future_refresh_staging_parity.py::test_preflight_passes_worker_owned_0750_runtime`：同上。
- secret guard：资产迁到仓外后，`tests/regression/test_guards.py::test_secret_patterns_are_guarded` 单测 `1 passed`，并在最终全量中通过。
- Ruff 全仓：PASS。
- 仓外资产复核：size/SHA 与上文一致；DuckDB `1.5.4` 以 `read_only=True` 打开并列出 13 张表。
- identity/verdict 探针使用 `CALIBRATION_VERSION` 与默认 `LambdaCalibrationParams()` 实测：`21960a863fd93dcae01ff8804e73fd0ef9d8360e8f2b8073313f226322e5db71` / `APPROVED_VALIDATED`。
- 本任务仅新增本报告；`pyproject.toml`、`uv.lock`、生产代码、迁移与模型文件均无 diff。

## 7. Stop lines

- Football Provider：`0` 次；本任务上限 100，未接近上限。
- R2 HTTP：`1` 次，仅获准完整资产 URL。
- 生产数据库：只读事务查询；生产写 `0`。
- W2 数据物化、W2↔Transfermarkt 对照表、ledger、migration、部署、GitHub/GHCR：均为 `0`。
- `calibrate_lambdas` 接入、当前身价历史回填、`CALIBRATION_VERSION`、模型参数/权重：均为 `0`。
- 资产与 DuckDB 分析 venv 均位于 worktree 外的私有目录，未跟踪、不提交。
- identity/verdict 保持 `21960a863fd93dcae01ff8804e73fd0ef9d8360e8f2b8073313f226322e5db71` / `APPROVED_VALIDATED`。
