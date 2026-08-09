# Dashboard Freshness Contract

```text
AUTHORITY = W2_DASHBOARD_P1_FRESHNESS_CONTRACT_V1
BASE_MAIN_SHA = f0fe9d332d05a84f1ef04be86fd9fb44b69d69e3
UNIVERSAL_STALE_THRESHOLD = FORBIDDEN
NO_CALL_ON_READ = true
```

Provider refresh authority describes the confirmed upstream contract. It does
not authorize W2 collection or Scheduler changes.

| FRESHNESS_DOMAIN | Provider refresh authority | Read-model source | Availability | Dashboard status semantics | NO_CALL_ON_READ |
|---|---:|---|---|---|---|
| `FIXTURES` | ~15s | checkpoint fixture identity/kickoff/status and page update time | `AVAILABLE` | source-bound `AVAILABLE`; missing source time is `SOURCE_AS_OF_NOT_PROJECTED` | `true` |
| `EVENTS` | ~15s | no final DayView domain timestamp | `NOT_AVAILABLE` | `SOURCE_AS_OF_NOT_PROJECTED`; never inferred from page time | `true` |
| `STATISTICS` | ~1m | per-card `data_refresh.statistics_status/captured_at` when present | `PARTIAL` | source status preserved; absent is `NOT_AVAILABLE` | `true` |
| `PLAYERS` | ~1m | no final DayView domain timestamp | `NOT_AVAILABLE` | `SOURCE_AS_OF_NOT_PROJECTED` | `true` |
| `LINEUPS` | ~15m | per-card `data_refresh.lineups_status/captured_at` | `PARTIAL_1_OF_13_VERIFIED` | `READY`, `PROVIDER_EMPTY`, `NOT_REQUESTED`, or source value; absence is `NOT_AVAILABLE` | `true` |
| `ODDS_PREMATCH` | ~3h | `freshness.odds_last_confirmed_at` and Round-3 current snapshot freshness | `AVAILABLE_WHEN_OBSERVED` | snapshot `COMPLETE/STALE`; zero/one/multi truth remains separate | `true` |
| `ODDS_LIVE` | ~5s | intentionally excluded | `FORBIDDEN_AS_BENCHMARK` | no timestamp/value in final model | `true` |
| `INJURIES` | ~4h | per-card `data_refresh.injuries_status/captured_at` when present | `PARTIAL` | source status preserved; absent is `NOT_AVAILABLE` | `true` |
| `PREDICTIONS` | ~1h | no checkpoint/DayView API-Football Prediction projection | `PARTIAL_NOT_PROJECTED` | `NOT_AVAILABLE` + explicit reason | `true` |
| `STANDINGS` | ~1h | no final DayView domain timestamp | `NOT_AVAILABLE` | `SOURCE_AS_OF_NOT_PROJECTED` | `true` |
| `TEAMS_STATISTICS` | ~12h / ~2 daily | no final DayView domain timestamp | `NOT_AVAILABLE` | `SOURCE_AS_OF_NOT_PROJECTED` | `true` |
| `PAGE_PROJECTION` | internal projection time only | DayView `freshness.page_updated_at` | `AVAILABLE` | must never be labeled odds or domain capture time | `true` |

## Domain entry contract

Every `freshness.domains.*` entry contains:

```text
domain
availability
status
source
source_as_of
provider_refresh_authority
readiness_semantics
no_call_on_read = true
```

An absent `source_as_of` is not replaced with `generated_at`. `NOT_AVAILABLE`
is a truthful projection state, not an incident unless the existing readiness
contract independently marks the match incomplete.

## Market Memory

```text
0 snapshots -> NO_TIMELINE_EVIDENCE
1 snapshot  -> ONE_OBSERVATION_NOT_A_TREND
2+ snapshots -> DISCRETE_REAL_PATH
```

Every point must come from the existing persisted Round-3 timeline. The
adapter preserves capture identity, captured time, canonical line, bookmaker
count, prices and probabilities. It creates no points and performs no
interpolation.

```text
CANONICAL_CLOSE = NOT_OBTAINABLE_FROM_CURRENT_PROVIDER
CURRENT_PRICE_REFERENCE = LAST_AVAILABLE_PREMATCH_SNAPSHOT
ANONYMOUS_LIVE_ODDS_AS_BENCHMARK = FORBIDDEN
```

## Lineup boundary

```text
WHITELIST_COVERAGE_VERIFIED = 1/13
COVERAGE_VERIFIED_ON = chinese_super_league
OTHER_12 = UNVERIFIED
FIRST_APPEARANCE_TIME = UNMEASURED
```

Optional External Intelligence is separately `NOT_CONNECTED` and never makes
match readiness incomplete.

## V4.1 time presentation

V4.1 publishes raw time authority rather than authored relative labels:

```text
generated_at
kickoff_utc
latest_snapshot_at
freshness_max_age_seconds
next_eval_at
checkpoint_generated_at
```

The client derives countdowns and ages from these values across timezone and
football-day boundaries. `next_eval_at <= generated_at` is displayed as
expired, never as a next evaluation. Market `READY` remains source-bound;
`STALE` and `READY` cannot coexist for the same public market. A global model
quality checkpoint is `AVAILABLE` only when its timestamp is current and all
required probability metrics exist. A timestamp beyond the boundary is
`STALE`; a current timestamp with missing required metrics is `INCOMPLETE`; no
usable timestamp is `NOT_AVAILABLE`. All non-available states fail closed and
`NOT_AVAILABLE` never displays a misleading source timestamp. None of these
reads refreshes Provider data or changes Scheduler cadence.
