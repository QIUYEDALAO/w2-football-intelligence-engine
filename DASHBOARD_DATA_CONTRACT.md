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

## Public status semantics

Every public condition added by this remediation carries a required
`public_semantics` object. `scope` is exactly `MATCH`, `SELECTED_DAY`,
`CROSS_DAY_CUMULATIVE`, or `GLOBAL`. `cause` is nullable only when no gap or
waiting condition exists; otherwise it is exactly `NOT_YET_DUE`,
`AWAITING_COLLECTION`, `INSUFFICIENT`, `UNAVAILABLE`, `UNASSESSED`,
`LABEL_MISSING`, `IDENTITY_UNRESOLVED`, or `AMBIGUOUS`. Unknown values fail
schema validation. Public copy and severity derive from this pair; raw domain
states remain separately auditable and cannot override it.

## Envelope, runtime and read proof

| FIELD | SOURCE | AVAILABILITY | FRESHNESS_DOMAIN | READINESS_SEMANTICS | NO_CALL_ON_READ |
|---|---|---|---|---|---|
| `schema_version` | P2 schema constant | `AVAILABLE` | `NONE` | exact v1 literal | `true` |
| `generated_at`, `date`, `timezone`, `window` | existing DayView envelope | `AVAILABLE` | `PAGE_PROJECTION` | selected-day workspace is exactly `window=today`; multi-day windows fail closed at request and response schema boundaries | `true` |
| `football_day_timezone`, `football_day_cutoff_hour`, `football_day_start_utc`, `football_day_end_utc` | existing football-day boundary projected through Dashboard -> DayView | `AVAILABLE` | `FIXTURES` | exact configured timezone/cutoff and half-open UTC window; frontend does not reconstruct | `true` |
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
| `runtime.market_price_attention_threshold_ratio` | Dashboard priority contract | `AVAILABLE` | `NONE` | exactly `0.02`; price-only movement below 2% remains factual evidence but does not enter priority | `true` |
| `runtime.candidate`, `formal`, `lock`, `production` | frozen environment/product authority | `AVAILABLE` | `NONE` | all `OFF` | `true` |

## Navigation, Attention and match identity

| FIELD | SOURCE | AVAILABILITY | FRESHNESS_DOMAIN | READINESS_SEMANTICS | NO_CALL_ON_READ |
|---|---|---|---|---|---|
| `navigation` | `build_date_navigation` output | `AVAILABLE` | `FIXTURES` | existing date/replay semantics preserved | `true` |
| `attention[].fixture_id`, `kickoff_utc` | DayView card identity | `AVAILABLE` | `FIXTURES` | only real cards | `true` |
| `attention[].intelligence_state` | `build_intelligence_projection` | `AVAILABLE` | `PAGE_PROJECTION` | frozen seven-state precedence | `true` |
| `attention[].reason_codes` | `intelligence_reason_codes` | `AVAILABLE` | relevant source domains | empty only for impossible invalid state; stable has explicit code | `true` |
| `attention[].affected_domains` | existing intelligence state/reason evidence | `AVAILABLE` | relevant source domains | deterministic EVENT/DATA/MODEL/COLLECTION/MARKET domain projection; no new signal | `true` |
| `attention[].factual_summary` | canonical match factual-summary authority | `AVAILABLE` | `ODDS_PREMATCH` | same causal evidence/conclusion/recovery statement as the match; no recommendation language | `true` |
| `attention[].readiness_status` | DayView `data_status` | `AVAILABLE` | relevant source domains | existing readiness value preserved | `true` |
| `attention[].readiness_context` | Decision/Data Readiness `reason_code`, `missing_fields`, `stale_fields`, `action` | `AVAILABLE` | relevant source domains | source blockers/context preserved; no frontend reconstruction | `true` |
| `attention[].next_eval_at` | Decision Contract | `AVAILABLE_WHEN_EVIDENCE_EXISTS` | relevant source domains | null when source has no next evaluation | `true` |
| `attention[].risks` | DayView `risk_dimensions` | `AVAILABLE` | relevant source domains | exact `EVENT_RISK`/`DATA_RISK`/`MODEL_RISK`/`COLLECTION_RISK`; no extra/missing axis | `true` |
| `attention[].risks.COLLECTION_RISK.assessment_status`, `evidence_basis`, `source_as_of` | persisted terminal/capture assessment evidence | `AVAILABLE_WHEN_EVIDENCE_EXISTS` | `ODDS_PREMATCH` | `OK` requires current persisted assessment; missing evidence is `UNASSESSED`, not green and not incident | `true` |
| `attention[].risks.MODEL_RISK.assessment_status`, `evidence_basis` | persisted model/simulation assessment evidence | `AVAILABLE_WHEN_EVIDENCE_EXISTS` | `MODEL` | missing readiness evidence is `UNASSESSED`, not green and not incident; evidence-backed disagreement remains assessed risk | `true` |
| `matches[].fixture_id`, `competition_id`, `competition_name` | DayView card identity | `AVAILABLE` | `FIXTURES` | missing identity fails existing DayView contract | `true` |
| `matches[].kickoff_utc`, `home_team_name`, `away_team_name`, `status` | DayView card identity | `AVAILABLE_WHEN_EVIDENCE_EXISTS` | `FIXTURES` | null only when existing source lacks optional display name/status | `true` |
| `matches[].outcome.is_finished` | DayView fixture status | `AVAILABLE` | `FIXTURES` | exact fact derived from existing finished statuses (`FT/AET/PEN/FINISHED`); no new status enum | `true` |
| `matches[].outcome.is_tracked`, `is_recorded` | Decision Contract `outcome_tracked` plus replay front-door card/summary | `AVAILABLE` | `PAGE_PROJECTION` | persisted facts only; recorded outcomes cannot be attached to unfinished matches | `true` |
| `matches[].outcome.public_semantics` | persisted fixture status/kickoff plus `generated_at` and the three outcome facts above | `AVAILABLE` | `FIXTURES` / `PAGE_PROJECTION` | exact `MATCH` truth table: unfinished before the existing kickoff+3h result window = `NOT_YET_DUE`; stale unfinished status after that window = `AWAITING_COLLECTION`; missing time or unknown/postponed/cancelled status = `UNASSESSED`; finished+recorded = null; finished+tracked+unrecorded = `AWAITING_COLLECTION`; finished+untracked = `UNASSESSED` | `true` |
| `matches[].next_market_collection_at` | earliest future non-test/non-namespaced persisted checkpoint plan containing `odds` | `AVAILABLE_WHEN_SCHEDULED` | `ODDS_PREMATCH` | factual collection schedule only; null when no future odds checkpoint exists; never derived from or substituted for `readiness.next_eval_at` | `true` |
| `matches[].{home,away}_team_label.public_semantics` | canonical/reviewed team identity adapter | `AVAILABLE` | `FIXTURES` | `MATCH + LABEL_MISSING` keeps the known raw name readable and adds a non-fault translation badge; only `IDENTITY_UNRESOLVED`/`AMBIGUOUS` may use an identity placeholder | `true` |
| `matches[].intelligence_state`, `intelligence_reason_codes`, `risks` | existing intelligence projection | `AVAILABLE` | relevant source domains | exact seven states and exact four production-shaped risk axes; fail closed | `true` |

## Readiness and product layers per match

| FIELD | SOURCE | AVAILABILITY | FRESHNESS_DOMAIN | READINESS_SEMANTICS | NO_CALL_ON_READ |
|---|---|---|---|---|---|
| `matches[].readiness.status` | DayView `data_status` | `AVAILABLE` | relevant source domains | existing DataStatus value | `true` |
| `matches[].readiness.reason_code`, `reason_codes` | Decision Contract + intelligence reasons | `AVAILABLE_WHEN_EVIDENCE_EXISTS` | relevant domains | explicit blocker/reason, never recommendation | `true` |
| `matches[].readiness.missing_fields`, `stale_fields` | Decision/Data Readiness | `AVAILABLE` | relevant domains | source lists preserved | `true` |
| `matches[].readiness.action`, `next_eval_at` | Decision Contract | `AVAILABLE_WHEN_EVIDENCE_EXISTS` | relevant domains | next decision/readiness evaluation only; never presented as Provider collection | `true` |
| `matches[].readiness.provider_budget_status` | Decision/DayView freshness | `AVAILABLE_WHEN_EVIDENCE_EXISTS` | `PAGE_PROJECTION` | `UNKNOWN` allowed; no quota call | `true` |
| `matches[].readiness.lineup_status`, `lineup_expectation` | `data_refresh` + lineup requirement | `PARTIAL` | `LINEUPS` | 1/13 coverage limitation retained | `true` |
| `matches[].market_fact.status`, `main_line` | canonical public market-evidence readiness over the Round-3 current AH/OU snapshot | `AVAILABLE_WHEN_EVIDENCE_EXISTS` | `ODDS_PREMATCH` | exact `READY/STALE/INSUFFICIENT`; stale memory is never ready; fact only | `true` |
| `matches[].market_fact.source_status` | unmodified Round-3 source status | `AVAILABLE` | `ODDS_PREMATCH` | technical audit only; never a second public readiness authority | `true` |
| `matches[].market_fact.current_odds`, `market_probabilities` | DayView market fields | `AVAILABLE_WHEN_EVIDENCE_EXISTS` | `ODDS_PREMATCH` | observed values only | `true` |
| `matches[].market_fact.price_reference` | approved P0 constant | `AVAILABLE` | `ODDS_PREMATCH` | `LAST_AVAILABLE_PREMATCH_SNAPSHOT` | `true` |
| `matches[].market_fact.canonical_close_status` | approved P0 constant | `AVAILABLE` | `ODDS_PREMATCH` | `NOT_OBTAINABLE_FROM_CURRENT_PROVIDER` | `true` |
| `matches[].w2_analysis.status` | P2 semantic adapter | `AVAILABLE` | `PAGE_PROJECTION` | `ANALYSIS_REFERENCE` | `true` |
| `matches[].w2_analysis.proof_status` | approved P0 constant | `NOT_PROVEN` | `NONE` | never recommendation confidence | `true` |
| `matches[].w2_analysis.decision_tier`, `analysis_state`, `reason_codes` | DayView diagnostic fields | `AVAILABLE` | relevant domains | compatibility tier is diagnostic input only | `true` |
| `matches[].w2_analysis.model_view` | canonical DayView simulation | `AVAILABLE_WHEN_EVIDENCE_EXISTS` | `PAGE_PROJECTION` | pass-through status/payload, no simulation | `true` |
| `matches[].w2_analysis.model_view.source_status`, `matches[].model_lab.w2_model.source_status` | existing simulation status | `AVAILABLE_WHEN_EVIDENCE_EXISTS` | `PAGE_PROJECTION` | source status retained; public status is `PRIOR_ONLY` when calibration is `BASELINE_PRIOR` | `true` |
| `matches[].w2_analysis.model_market_relation` | Model Lab diagnostics | `AVAILABLE_WHEN_EVIDENCE_EXISTS` | `ODDS_PREMATCH` | outside range is warning, not opportunity | `true` |
| `matches[].formal_recommendation.status`, `reason` | approved P0/runtime authority | `AVAILABLE` | `NONE` | fixed `OFF` + `PRODUCT_AUTHORITY_DISABLED` | `true` |

## Market Radar, Model Lab and scoreline

| FIELD | SOURCE | AVAILABILITY | FRESHNESS_DOMAIN | READINESS_SEMANTICS | NO_CALL_ON_READ |
|---|---|---|---|---|---|
| `matches[].market_radar.schema_version` | existing radar schema | `AVAILABLE_WHEN_EVIDENCE_EXISTS` | `ODDS_PREMATCH` | source version preserved | `true` |
| `matches[].market_radar.markets.{ASIAN_HANDICAP,TOTALS}.status` | current snapshot plus source-bound freshness | `AVAILABLE` | `ODDS_PREMATCH` | sole public authority: `READY` iff current, `STALE` iff persisted but expired, otherwise `INSUFFICIENT` | `true` |
| `.source_status` | unmodified Round-3 market status | `AVAILABLE` | `ODDS_PREMATCH` | technical audit only; cannot override public status | `true` |
| `.snapshot_state`, `snapshot_count`, `observation_count`, `bookmaker_pair_count`, `quote_row_count` | Round-3 market/timeline | `AVAILABLE` | `ODDS_PREMATCH` | exact 0/1/2+ semantics; observation/quote rows are single-side rows, bookmaker pairs are summed across snapshots | `true` |
| `.main_line`, `bookmaker_count`, `prices`, `probabilities`, `freshness` | Round-3 current snapshot | `AVAILABLE_WHEN_EVIDENCE_EXISTS` | `ODDS_PREMATCH` | null/empty when no current snapshot | `true` |
| `.timeline_points`, `movement`, `reason_codes` | persisted Round-3 timeline/movement | `AVAILABLE` | `ODDS_PREMATCH` | exact four-class line/price-median contract; movement exposes from/to time, line and side-price deltas; no interpolation or synthetic points | `true` |
| `matches[].model_lab.schema_version` | existing Model Lab schema | `AVAILABLE_WHEN_EVIDENCE_EXISTS` | `PAGE_PROJECTION` | source version preserved | `true` |
| `matches[].model_lab.w2_model` | existing simulation/model diagnostics | `AVAILABLE_WHEN_EVIDENCE_EXISTS` | `PAGE_PROJECTION` | diagnostic only | `true` |
| `matches[].model_lab.market` | canonical public market-evidence readiness plus technical source status | `AVAILABLE_WHEN_EVIDENCE_EXISTS` | `ODDS_PREMATCH` | same public status as radar/fact; stale blocks current comparison | `true` |
| `matches[].model_lab.api_football_prediction` | absent checkpoint projection | `NOT_AVAILABLE` | `PREDICTIONS` | explicit reason; never fetched on read | `true` |
| `matches[].model_lab.relation` | existing Model Lab comparison statuses | `AVAILABLE_WHEN_EVIDENCE_EXISTS` | `ODDS_PREMATCH` | explicitly `模型比较状态`, never a second market-readiness authority; no opportunity semantics | `true` |
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
| `validation.directional.only_record_reason`, `market_direction_benchmark` | probability readiness plus approved P0 constant | mixed explicit | `PAGE_PROJECTION` / `NONE` | exact reason for record-only direction; market direction benchmark remains `NOT_DEFINED`, never zero/estimated | `true` |
| `validation.league_performance[]` fields | `performance:cohort:league:*` | `AVAILABLE_WHEN_EVIDENCE_EXISTS` | `PAGE_PROJECTION` | `AVAILABLE/SAMPLE_BUILDING/INSUFFICIENT` | `true` |
| `validation.league_performance[].source_league`, `competition_id`, `canonical_competition_id`, `competition_name`, `identity_status` | performance checkpoint identity resolved by existing `CompetitionRegistry` provider mapping | `AVAILABLE_WHEN_EVIDENCE_EXISTS` | `PAGE_PROJECTION` | `competition_id` is canonical when resolved; the original alias remains in `source_league`; unresolved identity is explicit and never displayed bare | `true` |
| `validation.league_performance[].source_aliases`, `source_checkpoint_keys`, `scope_group`, `aggregation_status` | canonical aggregation adapter over cohort and deduplicated `performance:fixture:*` evidence | `AVAILABLE` | `PAGE_PROJECTION` | at most one public row per canonical league; ambiguous aggregate-only overlap is `CONFLICT`, never percentage-averaged | `true` |
| `validation.league_performance[].log_loss`, `source_statistical_status`, `probability_evidence_ready` | same league performance checkpoint | `AVAILABLE_WHEN_EVIDENCE_EXISTS` | `PAGE_PROJECTION` | public status requires source availability plus Brier/LogLoss/ECE; stored source status is unchanged | `true` |
| `validation.league_performance[].only_record_reason`, `market_direction_benchmark` | canonical probability readiness and approved P0 constant | `AVAILABLE` | `PAGE_PROJECTION` / `NONE` | record-only reason is explicit; benchmark remains `NOT_DEFINED` | `true` |
| `validation.tournament_performance[]` | same canonical performance aggregation, tournament scope only | `AVAILABLE_WHEN_EVIDENCE_EXISTS` | `PAGE_PROJECTION` | World Cup/cup and other non-league evidence is retained outside national-league performance | `true` |
| `validation.forward_validation_records` | bounded forward-ledger checkpoint adapter | `AVAILABLE_WHEN_EVIDENCE_EXISTS` | `PAGE_PROJECTION` | counts/outcomes/exclusions only; no CLV/ROI | `true` |
| `validation.forward_validation_records.public_semantics` | bounded forward-ledger adapter | `AVAILABLE` | `PAGE_PROJECTION` | always `CROSS_DAY_CUMULATIVE`; these counts never share a statistic with selected-day replay/outcome gaps | `true` |
| `validation.forward_validation_records.excluded_share`, `excluded_by_reason` | persisted `validation_excluded_by_reason` / canonical exclusion distribution | `AVAILABLE` | `PAGE_PROJECTION` | source-bound counts; share is excluded/validation count; zero only for an empty denominator | `true` |
| `validation.history_replay.known_at`, `reason_summary`, `outcome_tracking_summary`, `card_hash_checks`, `replay_gaps` | existing replay front door over same DayView | `AVAILABLE` | `PAGE_PROJECTION` | existing history evidence preserved; outcome counts and exact fixture-id sets must agree with `matches[].outcome`; read only | `true` |
| `validation.history_replay.decision_summary` | existing replay front-door `decision_summary` | `AVAILABLE` | `PAGE_PROJECTION` | exact total/tier/data-status/lock-eligible counts answer what W2 judged; no second replay engine | `true` |
| `validation.history_replay.record_kind`, `status`, `replay_gaps`, `public_semantics` | `matches[].outcome` facts plus existing replay front door | `AVAILABLE` | `FIXTURES` / `PAGE_PROJECTION` | exact selected-day truth table: empty = `EMPTY/EMPTY/null/no gaps`; all unfinished remain `FORWARD_RECORD/FORWARD_RECORD` and derive `NOT_YET_DUE`, `AWAITING_COLLECTION`, or `UNASSESSED` from the same match time authority without `MISSING_OUTCOMES`; replay/mixed use `MISSING_OUTCOMES + AWAITING_COLLECTION` iff a finished tracked outcome is unrecorded | `true` |

League rows preserve all `source_aliases` and `source_checkpoint_keys`, resolve
`canonical_competition_id`/`competition_name` with explicit `identity_status`, and expose
`validation_n`, `decisive_n`, `correct`, `wrong`, `push`, `void`, raw
`direction_accuracy`, `brier`, `log_loss`, `calibration`, public
`statistical_status`, `source_statistical_status`, and
`probability_evidence_ready`. Public UI uses canonical Chinese names; raw aliases and
checkpoint identities remain available only in technical details.

## External Intelligence, freshness and Data/Ops

| FIELD | SOURCE | AVAILABILITY | FRESHNESS_DOMAIN | READINESS_SEMANTICS | NO_CALL_ON_READ |
|---|---|---|---|---|---|
| `external_intelligence.{weather,news,sentiment,advanced_xg}.status` | approved P0 boundary | `NOT_CONNECTED` | `NONE` | optional and non-blocking | `true` |
| each external `.affects_match_readiness` | approved P0 boundary | `AVAILABLE` | `NONE` | always false while not connected | `true` |
| `freshness.domains.*` | `FRESHNESS_CONTRACT.md` sources | mixed, explicit | matching domain | never infer source time | `true` |
| `data_operations.read_model_source`, `checkpoint_key`, `degradation`, `counts`, `system_health`, `provider_budget_status` | DayView envelope | `AVAILABLE` | `PAGE_PROJECTION` | raw source truth preserved for technical detail | `true` |

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

## SC20 single public authority contract

The endpoint and schema version remain unchanged. Public presentation is derived
only from `public_semantics.scope`, `public_semantics.cause`, and the factual fields
below. Raw operations health is technical evidence and cannot choose public copy,
color, or layout.

| FIELD | SOURCE | AVAILABILITY | FRESHNESS_DOMAIN | READINESS_SEMANTICS | NO_CALL_ON_READ |
|---|---|---|---|---|---|
| `selected_fixture_id` | information-usefulness ranking over existing match facts | `AVAILABLE_WHEN_MATCH_FOCUS` | relevant match domains | non-null only when a response match has usable evidence; kickoff and fixture id are deterministic tie-breaks | `true` |
| `date_strip[].public_semantics` | persisted fixture inventory, collection plan and market evidence | `AVAILABLE` | `FIXTURES` / `ODDS_PREMATCH` | exact selected-day scope and cause; no second display state | `true` |
| `matches[].public_semantics` | selected-day cause plus match evidence facts | `AVAILABLE` | relevant source domains | exact match scope and cause; no public status fallback | `true` |
| `today_summary.*` | canonical matches plus one primary reason per prioritized match | `AVAILABLE` | `PAGE_PROJECTION` | primary counts sum exactly to priority match count; secondary reasons never double-count | `true` |
| `global_focus.*` | selected-day semantics, freshness, navigation and match counts | `AVAILABLE_WITHOUT_SELECTED_FIXTURE` | `FIXTURES` / `PAGE_PROJECTION` | factual summary without a second status enum; no fabricated match | `true` |
| `global_model_quality.*` | global performance checkpoint and its timestamp | `AVAILABLE_WHEN_CURRENT` | `PAGE_PROJECTION` | exact `AVAILABLE/STALE/INCOMPLETE/NOT_AVAILABLE`; only complete current metrics render | `true` |
| `matches[].priority_reason_primary`, `priority_reason_secondary[]` | existing intelligence, market, readiness and model relation fields | `AVAILABLE` | relevant source domains | primary is only eligible `STALE_MARKET_MEMORY/MARKET_MOVEMENT/MODEL_DIAGNOSTIC`; data/lineup/collection attention remains secondary and never increments priority counts | `true` |
| `matches[].factual_summary` | canonical persisted AH/OU status, timeline depth and freshness | `AVAILABLE` | `ODDS_PREMATCH` | one causal authority states evidence, allowed conclusion and existing scheduled recovery; no read-side Provider call | `true` |
| `matches[].risks.*.explanation` | canonical risk dimension and source reason codes | `AVAILABLE_WHEN_SOURCE_REASON_EXISTS` | relevant source domains | Chinese-first dimension-specific summary; raw codes remain technical detail only; absent evidence is not fabricated | `true` |
| `matches[].market_radar.markets.*.trend_evidence_status` | persisted timeline depth plus exact movement evidence | `AVAILABLE` | `ODDS_PREMATCH` | one snapshot can never claim trend | `true` |
| `matches[].market_radar.markets.*.cross_sectional_comparison_status` | current same-time bookmaker pairs and public freshness | `AVAILABLE` | `ODDS_PREMATCH` | may be available when trend is insufficient; stale pauses comparison | `true` |
| `matches[].market_radar.markets.*.latest_snapshot_at` | latest persisted timeline point | `AVAILABLE_WHEN_OBSERVED` | `ODDS_PREMATCH` | raw timestamp; client derives age | `true` |
| `matches[].market_radar.markets.*.freshness_max_age_seconds` | existing source freshness payload | `AVAILABLE_WHEN_SOURCE_DEFINES` | `ODDS_PREMATCH` | no new universal threshold and no threshold change | `true` |
