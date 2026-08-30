# Gate 0B Execution Receipt

状态：`PASS_READ_ONLY_ZERO_WRITE`

证据日期：`2026-08-30`

证据交接：`docs/review_packages/GATE_0B_AND_U2_COHORT_HANDOFF.md`

执行身份：Claude Code 完成生产只读核对；Codex 本轮仅按交接单整理文档，没有重连 VPS、重跑查询或导出数据。

## 1. Overall

```text
GATE_0B = COMPLETE
PRODUCTION_AUTHORITY = ea557bb8 / schema 0070_notification_delivery_routing
ORIGIN_MAIN_3b7f87db = HISTORICAL_STATIC_SNAPSHOT_NOT_AUTHORITY
PROVIDER_CALLS = 0
BUSINESS_WRITES = 0
PRODUCTION_EXPORTS = 0
DEPLOYMENTS = 0
U2_EXECUTIONS = 0
```

## 2. Production Runtime Identity

| field | read-only result |
|---|---|
| host | `root@45.207.194.97`, label `HK112037094063` |
| uptime at audit | 8 days |
| release | `ea557bb8ff64e06add91bbe32814fe073ec64642` |
| schema | `0070_notification_delivery_routing` |
| API | healthy, exact image revision |
| worker | healthy, exact image revision |
| scheduler | healthy, exact image revision |
| Web | healthy, exact image revision |
| four-service revision parity | PASS |

生产 `ea557bb8 / 0070` 是运行权威。`origin/main@3b7f87db / 0051_apply_seven_day_collection_policy` 是选择性静态快照，落后生产 19 个 migration。

## 3. Static Conclusion Survival

基线权威更正与结论存活性是两个必须同时记录的事实：

| file | `3b7f87db` vs `ea557bb8` | conclusion | disposition |
|---|---|---|---|
| `src/w2/strategy/calibration.py` | byte-identical | `BASELINE_PRIOR` 硬编码系数、无拟合证据 | `SURVIVES` |
| `src/w2/domain/five_state_pricing.py` | byte-identical | 量化前 `EV/S` 身份；经 fair-odds 量化后代码层仅近似 | `SURVIVES` |
| `src/w2/models/independent.py` | byte-identical | 离线 comparator 与生产公式错配 | `SURVIVES` |
| `src/w2/backtest/free_tier_2024.py` | byte-identical | 历史 U1 输入可得性与五联赛 Understat 范围 | `SURVIVES_AS_HISTORICAL_STATIC_CONCLUSION` |
| `src/w2/markets/analysis_evidence.py` | changed `+34` | 0.05 语义登记册 | `PENDING_RECHECK_ON_PRODUCTION_BASELINE` |
| `src/w2/prematch/lifecycle.py` | changed `+339` | 0.05 语义登记册 | `PENDING_RECHECK_ON_PRODUCTION_BASELINE` |

三个关键常量在两基线的出现次数一致：

```text
MIN_MARKET_ANCHOR_DIVERGENCE = 3 + 0
ACTIVE_DELTA_THRESHOLD = 0 + 6
probability_delta_admission_gate = 1 + 0
```

这支持“登记册大概未发生实质语义变化”作为重核线索，但不是生产基线重核 PASS。

## 4. Historical Cache Availability

```text
local runtime/w2_understat_xg/understat_*.json = absent
production runtime/w2_understat_xg/understat_*.json = absent
local raw_dirs/fixtures_*.json = absent
production raw_dirs/fixtures_*.json = absent
```

2026-07 Understat 回测 cohort 无法按原 cache 复现。本轮没有重新获取 Understat 数据。

## 5. Production XG Cohort Metadata

| `team_xg_match` field | read-only result |
|---|---:|
| team rows | 19,004 |
| fixtures | 9,502 |
| xG non-null | 19,004 / 19,004 = 100% |
| kickoff minimum | 2024-02-22 |
| kickoff maximum | 2026-08-29 |
| 2024 rows | 2,963 |
| 2025 rows | 4,181 |
| 2026 rows | 2,358 |
| source system | `api_football_statistics` 100% |

该样本是 9,502 场，相对原 1,510 场约为 6.3 倍，但数据源从 Understat 改为 API-Football statistics。上表只是生产只读汇总元数据；本轮没有导出 fixture IDs 或数据行，所以 cohort 尚未冻结。

## 6. Production Formula Static Verification

Gate 0B 后续对生产镜像进行了静态代码核验，五个系数的当前生产效果均已查清：

| coefficient | production effect | verified evidence |
|---|---|---|
| `elo_gap_weight = 0.28` | rolling-xG proxy 使 `raw_delta` 放大 14%；不是独立信号，也不是死代码 | `analysis_calculator.py:3107,4674-4692` |
| `squad_value_log_weight = 0.18` | 当前 11 个启用联赛全部为零贡献 | `_team_value_mapping` 只读 competition-scoped `team_values` artifact；生产 artifact 仅有 `world_cup_2026`，与启用联赛交集为空 |
| `lineup_adjustment_weight = 0.08` | 当前生产构造路径恒为零贡献 | 唯一 `SimulationInputs` 构造点未填五个 lineup 字段；dataclass 默认全零/False；capability manifest 为 `NOT_IMPLEMENTED` |
| `home_advantage_goals = 0.12` | 唯一真实加性常数 | `LambdaCalibrationParams` 与 `calibrate_lambdas` |
| `dixon_coles_rho = 0.0` | 默认关闭，`tau_correction` 为空操作 | 默认参数与 score-matrix 构造 |

Elo proxy 的效果由下式确定，不依赖独立 rating 表：

```text
raw_delta = (xgF_h + xgA_a)/2 - (xgF_a + xgA_h)/2

elo_h - elo_a
  = [(xgF_h - xgA_h) - (xgF_a - xgA_a)] * 100
  = 2 * raw_delta * 100

elo_delta
  = ((elo_h - elo_a) / 400) * 0.28
  = (2 * raw_delta * 100 / 400) * 0.28
  = 0.14 * raw_delta
```

所以生产在**当前启用联赛**上是纯 rolling-xG 模型：非中立场 `adjusted_delta = 1.14 * raw_delta + 0.12`，中立场移除 `+ 0.12`，随后进入 total/lambda clamp。`elo_gap_weight` 有效，是 xG delta 的 14% 放大器；死的是当前启用联赛的身价项与当前构造路径的首发项。身价结论受 competition artifact 可得性限定，不能外推到存在匹配 `team_values` artifact 的其他联赛。

### 6.1 Superseded Inference Retained for Audit Trail

以下 Gate 0B 原推论不删除，但其源表判断错误，已由上述生产镜像静态代码验证取代：

```text
SUPERSEDED_BY_STATIC_CODE_VERIFICATION
INFERRED_FROM_SOURCE_TABLE_EMPTINESS_NOT_RUNTIME_VERIFIED
```

根据源表空/极稀疏，可以推断 Elo 和队级身价项对绝大多数生产历史 fixture 可能没有产生效果；但持久化 payload 不能直接证明每次运行的实际输入。因此该推断不是 runtime verification，任何引用都必须携带上述标记。

更正理由：生产 Elo 从 rolling xG snapshot 确定性构造，不读取 `team_rating_snapshots`；生产身价从 competition-scoped 静态 `team_values` artifact 读取，不读取 `team_value_asof_artifacts`。原表计数仍是当时只读查询事实，但不能支持原来的生产输入效果推论。

## 7. U2 Disposition

```text
COMPARATOR_IDENTITY = PRODUCTION_FORMULA_XG_WITH_PROXY_ELO
PROXY_ELO_EFFECT = elo_delta/raw_delta = 0.14 (tolerance 1e-9; zero raw_delta requires zero elo_delta)
SQUAD_VALUE_NONE = MATCHES_CURRENT_ENABLED_LEAGUES
LINEUP_ZERO_AND_GATES_FALSE = MATCHES_PRODUCTION_CONSTRUCTION
NEW_COHORT = team_xg_match_METADATA_ONLY_NOT_EXPORTED_NOT_FROZEN
CHALLENGER_REFIT_REQUIRED = TRUE
UNDERSTAT_COEFFICIENT_REUSE = FORBIDDEN
UNDERSTAT_TEMPERATURE_REUSE = FORBIDDEN
DIRECT_COMPARISON_TO_MINUS_0_026376_OR_MINUS_0_035368 = FORBIDDEN
U2_EXECUTION_COUNT = 0
```

U2 对照必须按生产公式构造 proxy Elo；任意非零 `raw_delta` fixture 的 `elo_delta / raw_delta` 必须在 `1e-9` 容差内等于 `0.14`，零 `raw_delta` 时 `elo_delta` 必须为零，否则评分前 fail closed。换 cohort 后，challenger 必须在新 cohort 的训练前缀上重新拟合，且必须在查看任何 validation outcome 之前冻结 fitting rule、split、min-history、competition set、artifact schema 与 hash。未来新结果不得与 2026-07 的 `-0.026376` / `-0.035368` 直接比较。

## 8. Read-Only and Zero-Write Proof

Gate 0B 交接单记录的唯一命令类为：

```text
docker ps
docker inspect
psql -tAc SELECT
```

| protected action | count |
|---|---:|
| Provider calls | 0 |
| SQL DML/DDL | 0 |
| business writes | 0 |
| production data exports | 0 |
| deployments | 0 |
| U2 executions | 0 |
| challenger refits | 0 |

本 receipt 依据自包含 Gate 0B 交接记录整理；Codex 本轮未重新访问生产，不把文档整理冒充为第二次独立运行验证。

## 9. Final Gate

```text
GATE_0B_READ_ONLY = PASS
AUTHORITY_DIRECTION = CORRECTED
CORE_STATIC_CONCLUSIONS = SURVIVE_BY_BYTE_IDENTITY
PRODUCTION_FORMULA_STATIC_VERIFICATION = COMPLETE
FIVE_PERCENT_REGISTRY = PENDING_RECHECK_ON_PRODUCTION_BASELINE
U2_V2 = PREREGISTERED_DRAFT_NOT_ARMED
STOP = TRUE
```
