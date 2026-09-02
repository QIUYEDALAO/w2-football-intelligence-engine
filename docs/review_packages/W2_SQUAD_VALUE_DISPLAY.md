# W2-SQUAD-VALUE-DISPLAY 验收记录

## 结论

Transfermarkt R2 当前 `players.csv.gz` 已导入本地隔离数据库，并同时保存为：

- 原始 player reference 快照；
- append-only player valuation observation；
- append-only registered-roster membership snapshot。

分析卡片新增只读 `team_value_display`：整队身价与确认首发身价分口径展示，分别标注
`captured_at`。没有确认首发时只展示整队口径；任何缺失都显示为不可用，不用均值、默认值
或当前值回填历史比赛。本交付不接入模型。

## 快照导入

| 字段 | 实测值 |
|---|---:|
| captured_at | `2026-09-02T09:22:54Z` |
| URL | `https://pub-e682421888d945d684bcae8890b0ec20.r2.dev/data/players.csv.gz` |
| SHA-256 | `1457768f75cb27adb38b2227b9c8facc53174a626cbe1e18f9019b5647fa8d3c` |
| 下载量 | 4,160,452 bytes |
| 下载耗时 | 3.721 s |
| player rows | 50,149 |
| valued rows | 41,528 |
| positioned rows | 50,149 |
| registered-roster membership rows | 50,149 |
| API-Football Provider calls | 0 |

导入目标为隔离 SQLite：`.local/squad-value-display.db`。该文件被忽略且不提交；生产写为
0。只访问了固定 R2 root 下的 `players.csv.gz`，没有访问历史 valuation 表或其他 URL。

## 展示口径

- 整队：`LATEST_COMPLETE_SNAPSHOT_AT_OR_BEFORE_AS_OF`，先按已审核的 API-Football →
  canonical team → Transfermarkt club 身份链选队，再取 as-of 之前最新完整注册名单快照，
  逐球员取最新 as-of valuation；任一球员缺值即整队值 `INCOMPLETE`。
- 确认首发：复用 `derive_lineup_change_features()` 的 `confirmed_xi_value_eur`，必须 11 名
  首发全部映射且全部有 as-of valuation；与整队值分开显示。
- 时间：整队显示 valuation snapshot 的 `captured_at`；确认首发显示其 valuation
  `captured_at`。lineup 缺失不阻断整队展示。

## Competition 与覆盖率

从 `config/competitions/` 逐文件实测：共 14 个 profile，其中 13 个国内联赛 profile
全部 `enabled=false`；唯一 `enabled=true` 的 profile 是 `world_cup_2026`。因此“11 个启用
联赛”不是当前仓库事实。

| enabled competition | snapshot 球员映射 | fixture 双方可算 | 原因 |
|---|---:|---:|---|
| `world_cup_2026` | `0 (不可计算)` | `0/0 (不可计算)` | `players.csv.gz` 是球员当前俱乐部快照；本地隔离库没有已审核的国家队 → Transfermarkt club 身份链，也没有 fixture authority。现有 48 队静态二手身价文件不是本次 R2 player snapshot 产物，未混入覆盖率。 |

未把 disabled profile 纳入“启用联赛”分母。当前无法诚实声称任何 enabled competition 的
球员映射命中率或 fixture 双方覆盖率大于 0；缺少分母时写“不可计算”，不伪造 0% 或默认
身价。管道和展示已接通，但当前 enabled scope 的身份数据仍未 materialize。

## 模型与治理边界

- `calibrate_lambdas` 改动 0；`squad_value_log_weight` 改动 0。
- `CALIBRATION_VERSION`、模型参数、ledger/白名单、migration、部署、GitHub 改动均为 0。
- 当前身价没有回填历史比赛，也没有参与拟合、回算或准入。
- 生产写 0；API-Football Provider 调用 0。
