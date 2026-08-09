# Dashboard Data Contract

```text
AUTHORITY = W2_DASHBOARD_P1_DATA_CONTRACT_V1
SCHEMA_VERSION = w2.dashboard-intelligence-workspace.v1
BASE_MAIN_SHA = f0fe9d332d05a84f1ef04be86fd9fb44b69d69e3
READ_AUTHORITY = READ_MODEL_CHECKPOINT_PLUS_PURE_EXISTING_PROJECTIONS
NO_CALL_ON_READ = true
```

`AVAILABILITY` is one of `AVAILABLE`, `AVAILABLE_WHEN_EVIDENCE_EXISTS`,
`PARTIAL`, `NOT_AVAILABLE`, `NOT_CONNECTED`, `NOT_DEFINED`, or `NOT_PROVEN`.
All fields below are required in the schema; nullable values represent the
declared availability/readiness state and never authorize fabrication.

## Envelope, runtime and read proof

| FIELD | SOURCE | AVAILABILITY | FRESHNESS_DOMAIN | READINESS_SEMANTICS | NO_CALL_ON_READ |
|---|---|---|---|---|---|
| `schema_version` | P2 schema constant | `AVAILABLE` | `NONE` | exact v1 literal | `true` |
| `generated_at`, `date`, `timezone`, `window` | existing DayView envelope | `AVAILABLE` | `PAGE_PROJECTION` | source values preserved | `true` |
| `source` | P2 adapter constant | `AVAILABLE` | `NONE` | checkpoint + pure projections only | `true` |
| `selected_fixture_id` | first frozen Attention/Match order row or null | `AVAILABLE` | `FIXTURES` | null when no matches | `true` |
| `read_contract.provider_calls` | DayView read invariant | `AVAILABLE` | `NONE` | must equal 0 | `true` |
| `read_contract.db_writes` | DayView read invariant | `AVAILABLE` | `NONE` | must equal 0 | `true` |
| `read_contract.would_write_checkpoint` | DayView read invariant | `AVAILABLE` | `NONE` | must be false | `true` |
| `read_contract.no_call_on_read` | schema constant + tests | `AVAILABLE` | `NONE` | must be true | `true` |
| `runtime.product` | approved P0 product contract | `AVAILABLE` | `NONE` | Intelligence + Diagnostics | `true` |
| `runtime.public_dashboard_authority` | approved P0 contract | `AVAILABLE` | `NONE` | new workspace only | `true` |
| `runtime.active_whitelist_count` | exact runtime authority | `AVAILABLE` | `NONE` | exactly 13 | `true` |
| `runtime.free_bridge_mode` | frozen context | `AVAILABLE` | `NONE` | `SHADOW_ONLY` | `true` |
| `runtime.candidate`, `formal`, `lock`, `production` | frozen environment/product authority | `AVAILABLE` | `NONE` | all `OFF` | `true` |

## Navigation, Attention and match identity

| FIELD | SOURCE | AVAILABILITY | FRESHNESS_DOMAIN | READINESS_SEMANTICS | NO_CALL_ON_READ |
|---|---|---|---|---|---|
| `navigation` | `build_date_navigation` output | `AVAILABLE` | `FIXTURES` | existing date/replay semantics preserved | `true` |
| `attention[].fixture_id`, `kickoff_utc` | DayView card identity | `AVAILABLE` | `FIXTURES` | only real cards | `true` |
| `attention[].intelligence_state` | `build_intelligence_projection` | `AVAILABLE` | `PAGE_PROJECTION` | frozen seven-state precedence | `true` |
| `attention[].reason_codes` | `intelligence_reason_codes` | `AVAILABLE` | relevant source domains | empty only for impossible invalid state; stable has explicit code | `true` |
| `attention[].affected_domains` | existing intelligence state/reason evidence | `AVAILABLE` | relevant source domains | deterministic EVENT/DATA/MODEL/COLLECTION/MARKET domain projection; no new signal | `true` |
| `attention[].factual_summary` | existing intelligence state + reason codes | `AVAILABLE` | `PAGE_PROJECTION` | factual source-code summary only; no recommendation language | `true` |
| `attention[].readiness_status` | DayView `data_status` | `AVAILABLE` | relevant source domains | existing readiness value preserved | `true` |
| `attention[].readiness_context` | Decision/Data Readiness `reason_code`, `missing_fields`, `stale_fields`, `action` | `AVAILABLE` | relevant source domains | source blockers/context preserved; no frontend reconstruction | `true` |
| `attention[].next_eval_at` | Decision Contract | `AVAILABLE_WHEN_EVIDENCE_EXISTS` | relevant source domains | null when source has no next evaluation | `true` |
| `attention[].risks` | DayView `risk_dimensions` | `AVAILABLE` | relevant source domains | exact `EVENT_RISK`/`DATA_RISK`/`MODEL_RISK`/`COLLECTION_RISK`; no extra/missing axis | `true` |
| `matches[].fixture_id`, `competition_id`, `competition_name` | DayView card identity | `AVAILABLE` | `FIXTURES` | missing identity fails existing DayView contract | `true` |
| `matches[].kickoff_utc`, `home_team_name`, `away_team_name`, `status` | DayView card identity | `AVAILABLE_WHEN_EVIDENCE_EXISTS` | `FIXTURES` | null only when existing source lacks optional display name/status | `true` |
| `matches[].intelligence_state`, `intelligence_reason_codes`, `risks` | existing intelligence projection | `AVAILABLE` | relevant source domains | exact seven states and exact four production-shaped risk axes; fail closed | `true` |

## Readiness and product layers per match

| FIELD | SOURCE | AVAILABILITY | FRESHNESS_DOMAIN | READINESS_SEMANTICS | NO_CALL_ON_READ |
|---|---|---|---|---|---|
| `matches[].readiness.status` | DayView `data_status` | `AVAILABLE` | relevant source domains | existing DataStatus value | `true` |
| `matches[].readiness.reason_code`, `reason_codes` | Decision Contract + intelligence reasons | `AVAILABLE_WHEN_EVIDENCE_EXISTS` | relevant domains | explicit blocker/reason, never recommendation | `true` |
| `matches[].readiness.missing_fields`, `stale_fields` | Decision/Data Readiness | `AVAILABLE` | relevant domains | source lists preserved | `true` |
| `matches[].readiness.action`, `next_eval_at` | Decision Contract | `AVAILABLE_WHEN_EVIDENCE_EXISTS` | relevant domains | next observation/evaluation only | `true` |
| `matches[].readiness.provider_budget_status` | Decision/DayView freshness | `AVAILABLE_WHEN_EVIDENCE_EXISTS` | `PAGE_PROJECTION` | `UNKNOWN` allowed; no quota call | `true` |
| `matches[].readiness.lineup_status`, `lineup_expectation` | `data_refresh` + lineup requirement | `PARTIAL` | `LINEUPS` | 1/13 coverage limitation retained | `true` |
| `matches[].market_fact.status`, `main_line` | Round-3 current AH/OU snapshot | `AVAILABLE_WHEN_EVIDENCE_EXISTS` | `ODDS_PREMATCH` | fact only; null when no current snapshot | `true` |
| `matches[].market_fact.current_odds`, `market_probabilities` | DayView market fields | `AVAILABLE_WHEN_EVIDENCE_EXISTS` | `ODDS_PREMATCH` | observed values only | `true` |
| `matches[].market_fact.price_reference` | approved P0 constant | `AVAILABLE` | `ODDS_PREMATCH` | `LAST_AVAILABLE_PREMATCH_SNAPSHOT` | `true` |
| `matches[].market_fact.canonical_close_status` | approved P0 constant | `AVAILABLE` | `ODDS_PREMATCH` | `NOT_OBTAINABLE_FROM_CURRENT_PROVIDER` | `true` |
| `matches[].w2_analysis.status` | P2 semantic adapter | `AVAILABLE` | `PAGE_PROJECTION` | `ANALYSIS_REFERENCE` | `true` |
| `matches[].w2_analysis.proof_status` | approved P0 constant | `NOT_PROVEN` | `NONE` | never recommendation confidence | `true` |
| `matches[].w2_analysis.decision_tier`, `analysis_state`, `reason_codes` | DayView diagnostic fields | `AVAILABLE` | relevant domains | compatibility tier is diagnostic input only | `true` |
| `matches[].w2_analysis.model_view` | canonical DayView simulation | `AVAILABLE_WHEN_EVIDENCE_EXISTS` | `PAGE_PROJECTION` | pass-through status/payload, no simulation | `true` |
| `matches[].w2_analysis.model_market_relation` | Model Lab diagnostics | `AVAILABLE_WHEN_EVIDENCE_EXISTS` | `ODDS_PREMATCH` | outside range is warning, not opportunity | `true` |
| `matches[].formal_recommendation.status`, `reason` | approved P0/runtime authority | `AVAILABLE` | `NONE` | fixed `OFF` + `PRODUCT_AUTHORITY_DISABLED` | `true` |

## Market Radar, Model Lab and scoreline

| FIELD | SOURCE | AVAILABILITY | FRESHNESS_DOMAIN | READINESS_SEMANTICS | NO_CALL_ON_READ |
|---|---|---|---|---|---|
| `matches[].market_radar.schema_version` | existing radar schema | `AVAILABLE_WHEN_EVIDENCE_EXISTS` | `ODDS_PREMATCH` | source version preserved | `true` |
| `matches[].market_radar.markets.{ASIAN_HANDICAP,TOTALS}.status` | Round-3 market | `AVAILABLE` | `ODDS_PREMATCH` | `READY/INSUFFICIENT` | `true` |
| `.snapshot_state`, `snapshot_count`, `observation_count` | Round-3 market/timeline | `AVAILABLE` | `ODDS_PREMATCH` | exact 0/1/2+ semantics | `true` |
| `.main_line`, `bookmaker_count`, `prices`, `probabilities`, `freshness` | Round-3 current snapshot | `AVAILABLE_WHEN_EVIDENCE_EXISTS` | `ODDS_PREMATCH` | null/empty when no current snapshot | `true` |
| `.timeline_points`, `movement`, `reason_codes` | persisted Round-3 timeline/movement | `AVAILABLE` | `ODDS_PREMATCH` | no interpolation or synthetic points | `true` |
| `matches[].model_lab.schema_version` | existing Model Lab schema | `AVAILABLE_WHEN_EVIDENCE_EXISTS` | `PAGE_PROJECTION` | source version preserved | `true` |
| `matches[].model_lab.w2_model` | existing simulation/model diagnostics | `AVAILABLE_WHEN_EVIDENCE_EXISTS` | `PAGE_PROJECTION` | diagnostic only | `true` |
| `matches[].model_lab.market` | existing market diagnostics | `AVAILABLE_WHEN_EVIDENCE_EXISTS` | `ODDS_PREMATCH` | fact/reference only | `true` |
| `matches[].model_lab.api_football_prediction` | absent checkpoint projection | `NOT_AVAILABLE` | `PREDICTIONS` | explicit reason; never fetched on read | `true` |
| `matches[].model_lab.relation` | existing Model Lab market statuses | `AVAILABLE_WHEN_EVIDENCE_EXISTS` | `ODDS_PREMATCH` | no opportunity semantics | `true` |
| `matches[].model_lab.historical_validation` | frozen Phase 0.5 context | `AVAILABLE` | `NONE` | `NO_EDGE`, `NOT_PROVEN`, no rerun | `true` |
| `matches[].scoreline_reference.label`, `proof_status` | approved P0 semantics | `AVAILABLE` | `NONE` | `MODEL_SCORELINE_REFERENCE`, `NOT_PROVEN` | `true` |
| `matches[].scoreline_reference.status`, `simulations_completed` | existing `scoreline_projection` | `AVAILABLE_WHEN_EVIDENCE_EXISTS` | `PAGE_PROJECTION` | `READY` requires exactly 10,000 completed seeded simulations; no simulation on read | `true` |
| `matches[].scoreline_reference.top3[].scoreline`, `sample_count`, `unconditional_probability` | existing `scoreline_projection.top3` | `AVAILABLE_WHEN_EVIDENCE_EXISTS` | `PAGE_PROJECTION` | explicit unconditional probability; generic/conditional probability is not substituted | `true` |
| `matches[].evidence.card_hash`, `artifact_hash`, `source`, `source_event_at`, `decision_role` | DayView/frozen projection identity | `AVAILABLE_WHEN_EVIDENCE_EXISTS` | `PAGE_PROJECTION` | traceability only | `true` |

## Validation, league performance, records and replay

| FIELD | SOURCE | AVAILABILITY | FRESHNESS_DOMAIN | READINESS_SEMANTICS | NO_CALL_ON_READ |
|---|---|---|---|---|---|
| `validation.probability.status`, `sample_count` | global `performance:cohort:all` window | `AVAILABLE` | `PAGE_PROJECTION` | `AVAILABLE/SAMPLE_BUILDING/INSUFFICIENT` | `true` |
| `validation.probability.model_brier`, `market_brier`, `model_minus_market_brier` | existing cohort checkpoint metrics | `AVAILABLE_WHEN_EVIDENCE_EXISTS` | `PAGE_PROJECTION` | null when cohort insufficient | `true` |
| `validation.probability.model_log_loss`, `market_log_loss`, `model_minus_market_log_loss` | existing cohort checkpoint metrics | `AVAILABLE_WHEN_EVIDENCE_EXISTS` | `PAGE_PROJECTION` | null when cohort insufficient | `true` |
| `validation.probability.model_calibration_error`, `market_calibration_error` | existing ECE metrics | `AVAILABLE_WHEN_EVIDENCE_EXISTS` | `PAGE_PROJECTION` | null when cohort insufficient | `true` |
| `validation.probability.model_reliability_bins`, `market_reliability_bins` | existing checkpoint bins | `AVAILABLE` | `PAGE_PROJECTION` | real bin counts only | `true` |
| `validation.probability.checkpoint_metadata` | checkpoint key/hash/time | `AVAILABLE_WHEN_EVIDENCE_EXISTS` | `PAGE_PROJECTION` | missing checkpoint => `INSUFFICIENT` | `true` |
| `validation.directional.status`, `validation_n`, `decisive_n`, `correct`, `wrong`, `push`, `void`, `direction_accuracy`, `effective_n` | global cohort canonical counts | `AVAILABLE` | `PAGE_PROJECTION` | secondary hierarchy; accuracy null below source gate | `true` |
| `validation.directional.source_status`, `probability_evidence_ready` | canonical directional rate status + same-cohort Brier/LogLoss/ECE readiness | `AVAILABLE` | `PAGE_PROJECTION` | public `AVAILABLE` fails closed unless primary probability evidence is ready; source status remains auditable | `true` |
| `validation.directional.market_direction_benchmark` | approved P0 constant | `NOT_DEFINED` | `NONE` | never zero/estimated | `true` |
| `validation.league_performance[]` fields | `performance:cohort:league:*` | `AVAILABLE_WHEN_EVIDENCE_EXISTS` | `PAGE_PROJECTION` | `AVAILABLE/SAMPLE_BUILDING/INSUFFICIENT` | `true` |
| `validation.league_performance[].source_league`, `competition_id`, `canonical_competition_id`, `competition_name`, `identity_status` | performance checkpoint identity resolved by existing `CompetitionRegistry` provider mapping | `AVAILABLE_WHEN_EVIDENCE_EXISTS` | `PAGE_PROJECTION` | legacy `competition_id` remains the source checkpoint key; unresolved numeric identity is explicit and never displayed bare | `true` |
| `validation.league_performance[].log_loss`, `source_statistical_status`, `probability_evidence_ready` | same league performance checkpoint | `AVAILABLE_WHEN_EVIDENCE_EXISTS` | `PAGE_PROJECTION` | public status requires source availability plus Brier/LogLoss/ECE; stored source status is unchanged | `true` |
| `validation.forward_validation_records` | bounded forward-ledger checkpoint adapter | `AVAILABLE_WHEN_EVIDENCE_EXISTS` | `PAGE_PROJECTION` | counts/outcomes/exclusions only; no CLV/ROI | `true` |
| `validation.forward_validation_records.excluded_share`, `excluded_by_reason` | persisted `validation_excluded_by_reason` / canonical exclusion distribution | `AVAILABLE` | `PAGE_PROJECTION` | source-bound counts; share is excluded/validation count; zero only for an empty denominator | `true` |
| `validation.history_replay.known_at`, `reason_summary`, `outcome_tracking_summary`, `card_hash_checks`, `replay_gaps` | existing replay front door over same DayView | `AVAILABLE` | `PAGE_PROJECTION` | existing history evidence preserved; read only | `true` |
| `validation.history_replay.decision_summary` | existing replay front-door `decision_summary` | `AVAILABLE` | `PAGE_PROJECTION` | exact total/tier/data-status/lock-eligible counts answer what W2 judged; no second replay engine | `true` |

League rows preserve the original `source_league`/`competition_id`, resolve
`canonical_competition_id`/`competition_name` with explicit `identity_status`, and expose
`validation_n`, `decisive_n`, `correct`, `wrong`, `push`, `void`, raw
`direction_accuracy`, `brier`, `log_loss`, `calibration`, public
`statistical_status`, `source_statistical_status`, and
`probability_evidence_ready`.

## External Intelligence, freshness and Data/Ops

| FIELD | SOURCE | AVAILABILITY | FRESHNESS_DOMAIN | READINESS_SEMANTICS | NO_CALL_ON_READ |
|---|---|---|---|---|---|
| `external_intelligence.{weather,news,sentiment,advanced_xg}.status` | approved P0 boundary | `NOT_CONNECTED` | `NONE` | optional and non-blocking | `true` |
| each external `.affects_match_readiness` | approved P0 boundary | `AVAILABLE` | `NONE` | always false while not connected | `true` |
| `freshness.domains.*` | `FRESHNESS_CONTRACT.md` sources | mixed, explicit | matching domain | never infer source time | `true` |
| `data_operations.read_model_source`, `checkpoint_key`, `degradation`, `counts`, `system_health`, `provider_budget_status` | DayView envelope | `AVAILABLE` | `PAGE_PROJECTION` | source truth preserved | `true` |

## Prohibited fields

The unified schema and recursive payload keys must exclude:

```text
roi
clv
expected_value
value_score
opportunity_score
lock_eligible
anonymous_live_odds_benchmark
market_pick
```

Existing legacy payloads may contain some of these keys; the P2 adapter uses
an allowlist and never passes legacy payloads wholesale.
