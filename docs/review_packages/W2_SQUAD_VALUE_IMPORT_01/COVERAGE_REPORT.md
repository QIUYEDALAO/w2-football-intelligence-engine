# W2-SQUAD-VALUE-IMPORT-01

状态：`DONE_ISOLATED_IMPORT / PRODUCTION_UNCHANGED`

本任务从仓库固定白名单 URL 执行了一次 R2 快照导入，写入本任务隔离 SQLite；生产数据库只执行只读查询。未调用 Football Provider，未生成默认值，未执行历史回填、拟合或模型接入。

## 1. 快照身份与 as-of 语义

- URL：`https://pub-e682421888d945d684bcae8890b0ec20.r2.dev/data/players.csv.gz`
- SHA-256：`1457768f75cb27adb38b2227b9c8facc53174a626cbe1e18f9019b5647fa8d3c`
- `captured_at`：`2026-09-02T16:59:25Z`
- 球员引用：`50,149`
- 有 `market_value_in_eur`：`41,528`
- 有 position：`50,149`
- 隔离库实际新增：1 条 source snapshot、50,149 条 player reference、41,528 条 valuation observation，共 `91,678` 行。

`captured_at` 作为数据库 `observed_at` 写入 append-only 身价 observation；唯一身份包含 `transfermarkt_player_id / observed_at / source_sha256`。后续新内容快照会按新的 hash 与时间累积，历史比赛只能选择不晚于比赛 as-of 的 observation，不能用今天身价回填过去。

派发包所称“从未执行过一次”与当前生产只读事实部分冲突：生产已有一份 `2026-07-11T12:43:19Z` 的同 URL 快照，SHA-256 为 `921f986c8e6ddae235783440ee01725547120473e7e92b2c232780c5c521766a`，含 `50,149` 条 reference 和 `31,507` 条 valuation observation；但 `team_value_asof_artifacts=0`，整队聚合确实从未产出 artifact。本任务没有修改或覆盖这份生产历史。

## 2. 启用联赛口径

本地生产基线 `config/competitions/` 只有 `world_cup_2026.v1.json` 一份，且 `enabled=true`。这只能说明配置文件口径为 `1`，不是运行权威。

生产数据库只读查询得到：`league_profile=14`、`league_season=14`；其中 `13` 个 2026 season 为 `ACTIVE`，`world_cup_2026` 为 `CONFIGURED`。因此派发包/旧 Obsidian 的“11 联赛”不是当前可复核事实。本报告以 13 个 `ACTIVE` season 为运行覆盖率分母。

## 3. 球员映射覆盖

口径：每个 `fixture × team` 只取最新 structured lineup snapshot；分母为该 snapshot 的实际球员行，命中要求 `valuation_source_player_id` 在本次 R2 快照中存在且有数值身价。没有 lineup 行的联赛记为 `N/A`，不伪造 0% 样本。

| ACTIVE 联赛 | fixture 数 | 最新 lineup 球员 | 身价映射命中 | 命中率 | 首发球员 | 首发身价命中 | 首发命中率 |
|---|---:|---:|---:|---:|---:|---:|---:|
| allsvenskan | 42 | 77 | 19 | 24.68% | 44 | 18 | 40.91% |
| argentina_primera | 73 | 0 | 0 | N/A | 0 | 0 | N/A |
| brasileirao_serie_a | 59 | 0 | 0 | N/A | 0 | 0 | N/A |
| bundesliga | 20 | 0 | 0 | N/A | 0 | 0 | N/A |
| chinese_super_league | 45 | 88 | 0 | 0.00% | 44 | 0 | 0.00% |
| eliteserien | 42 | 40 | 0 | 0.00% | 22 | 0 | 0.00% |
| eredivisie | 43 | 0 | 0 | N/A | 0 | 0 | N/A |
| la_liga | 41 | 0 | 0 | N/A | 0 | 0 | N/A |
| ligue_1 | 27 | 0 | 0 | N/A | 0 | 0 | N/A |
| mls | 75 | 0 | 0 | N/A | 0 | 0 | N/A |
| premier_league | 30 | 0 | 0 | N/A | 0 | 0 | N/A |
| primeira_liga | 43 | 0 | 0 | N/A | 0 | 0 | N/A |
| serie_a | 30 | 0 | 0 | N/A | 0 | 0 | N/A |
| **合计** | **570** | **205** | **19** | **9.27%** | **110** | **18** | **16.36%** |

低覆盖事实：`chinese_super_league` 与 `eliteserien` 在已有 lineup 中均为 0%；`allsvenskan` 也只有 24.68% 全球员、40.91% 首发命中。其余 10 联赛没有 structured lineup 样本，不能把缺少分母写成命中率。

## 4. 整队与首发两个口径

### 整队 roster policy

`value_identity.py` 的整队口径要求 `LATEST_COMPLETE_SNAPSHOT_AT_OR_BEFORE_AS_OF`，并依赖 reviewed Transfermarkt team crosswalk、registered roster 和 player-club membership。生产只读计数为：team crosswalk `16`、registered roster `0`、club membership `0`、team-value artifact `0`。

因此 13 个 ACTIVE 联赛的 `570` 个 fixture 中，双方整队 `squad_value_eur` 可算为 **`0/570`**。不能用 R2 的 `current_club_id` 代替历史完整 roster，也没有使用默认值、均值或当前身价回填。

### confirmed XI

生产现有最新 lineup 中有 `5` 个 fixture 同时具备两队 confirmed 且各 11 名首发：allsvenskan `2`、chinese_super_league `2`、eliteserien `1`。按本次快照逐名要求 22 人都有数值身价，双方 `confirmed_xi_value_eur` 可算为 **`0/5`**；相对全部 ACTIVE fixtures 为 `0/570`。

整队与首发均保持 fail closed。快照导入增加了身价 observation，但没有自动创造 reviewed player mapping、历史 roster 或首发完整覆盖。

## 5. 边界

- `calibrate_lambdas`：未接入。
- `squad_value_log_weight`：未修改。
- 当前身价历史拟合/回算：未执行。
- URL：只访问固定 R2 `players.csv.gz`；白名单校验未放宽。
- Football Provider：`0` 次。
- R2 HTTP：`1` 次，仅固定白名单 `players.csv.gz`。
- 生产写、ledger、migration、部署、GitHub：均为 `0`。
