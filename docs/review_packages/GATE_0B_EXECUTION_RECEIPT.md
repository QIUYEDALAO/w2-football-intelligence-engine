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

## 6. Elo, Value and Runtime-Use Boundary

| source | read-only result |
|---|---:|
| `team_rating_snapshots` | 16 rows / 16 teams / only 2026-07-17 through 2026-07-20 |
| `team_value_asof_artifacts` | 0 rows |
| `player_valuation_observations` | 31,507 rows, player-level only |
| `transfermarkt_player_references` | 50,149 rows, player-level only |
| `dynamic_prematch_evaluations` | 5,733 rows; payload lacks calibration input fields |
| `model_forecast_capture` | 265 rows; payload lacks calibration input fields |
| `recommendation_locks` | 0 rows |

```text
INFERRED_FROM_SOURCE_TABLE_EMPTINESS_NOT_RUNTIME_VERIFIED
```

根据源表空/极稀疏，可以推断 Elo 和队级身价项对绝大多数生产历史 fixture 可能没有产生效果；但持久化 payload 不能直接证明每次运行的实际输入。因此该推断不是 runtime verification，任何引用都必须携带上述标记。

## 7. U2 Disposition

```text
COMPARATOR_IDENTITY = PRODUCTION_FORMULA_XG_ONLY
NEW_COHORT = team_xg_match_METADATA_ONLY_NOT_EXPORTED_NOT_FROZEN
CHALLENGER_REFIT_REQUIRED = TRUE
UNDERSTAT_COEFFICIENT_REUSE = FORBIDDEN
UNDERSTAT_TEMPERATURE_REUSE = FORBIDDEN
DIRECT_COMPARISON_TO_MINUS_0_026376_OR_MINUS_0_035368 = FORBIDDEN
U2_EXECUTION_COUNT = 0
```

换 cohort 后，challenger 必须在新 cohort 的训练前缀上重新拟合，且必须在查看任何 validation outcome 之前冻结 fitting rule、split、min-history、competition set、artifact schema 与 hash。未来新结果不得与 2026-07 的 `-0.026376` / `-0.035368` 直接比较。

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
FIVE_PERCENT_REGISTRY = PENDING_RECHECK_ON_PRODUCTION_BASELINE
U2_V2 = PREREGISTERED_DRAFT_NOT_ARMED
STOP = TRUE
```
