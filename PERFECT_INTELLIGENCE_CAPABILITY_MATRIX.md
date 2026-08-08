# Perfect Intelligence Capability Matrix

```text
AUTHORITY = W2_DASHBOARD_P1_PERFECT_CAPABILITY_MATRIX_V1
BASE_MAIN_SHA = f0fe9d332d05a84f1ef04be86fd9fb44b69d69e3
PRODUCT_SPEC = DASHBOARD_INTELLIGENCE_WORKSPACE_PRODUCT_SPEC.md@context/current
P1_SCOPE = EVIDENCE_AND_CONTRACT_ONLY
```

This matrix defines the truthful target capability for the final Intelligence
Workspace and the latest-main source that P2 may reuse. `TARGET` does not mean
that an unavailable capability may be fabricated.

| Capability | Perfect product behavior | Latest-main evidence/source | Current availability | P2 decision |
|---|---|---|---|---|
| One public workspace read model | One schema and payload serves Match Board, Inspector, diagnostics, validation, records and operations | No equivalent final schema/endpoint exists | `MISSING` | Build one adapter over existing read authorities |
| Match identity/day population | Real checkpoint-backed fixtures, football-day/date/window semantics | `ReadModelService.dashboard`, `ReadModelRepository.dashboard_latest_fixtures`, `src/w2/dashboard/date_window.py` | `AVAILABLE` | Reuse |
| Decision/readiness contract | Explicit data/lifecycle state, missing/stale fields, reason/action/next evaluation and budget status | `src/w2/domain/decision_contract.py`, `src/w2/readiness/data_gate.py`, `src/w2/dashboard/day_view.py` | `AVAILABLE` | Reuse; never rebuild |
| Seven-state Attention | Frozen precedence, real reason codes, kickoff and fixture-id tie-breakers | `src/w2/dashboard/intelligence.py`, `tests/unit/test_market_intelligence_projection.py` | `AVAILABLE` | Reuse |
| Four independent risks | Event/Data/Model/Collection dimensions remain independent | same sources as Attention | `AVAILABLE` | Reuse |
| Market facts | Current AH/OU main line, real quotes, bookmaker depth and probabilities | `src/w2/markets/round3_intelligence.py`, DayView `market_radar` | `AVAILABLE_WHEN_EVIDENCE_EXISTS` | Reuse |
| Market Memory | 0=no evidence, 1=observation not trend, 2+=discrete real path; never interpolate | Round-3 market radar and tests | `AVAILABLE_SPARSE` | Reuse exact zero/one/multi semantics |
| Model diagnostics | W2/market range diagnostics and explicit blockers | DayView `model_lab`, Round-3 tests | `AVAILABLE_WHEN_READY` | Reuse |
| API-Football Prediction benchmark | External-model benchmark only, never authority | `predictions` migration/model exists; no DayView/checkpoint projection is present | `PARTIAL_NOT_PROJECTED` | Expose explicit `NOT_AVAILABLE` with reason; no direct/provider read |
| Scoreline Top 3 | Existing 10,000-simulation, unconditional Top 3, `NOT_PROVEN` | `src/w2/dashboard/scorelines.py`, DayView `scoreline_reference` | `AVAILABLE_WHEN_SIMULATION_READY` | Reuse; never rebuild |
| Probability Validation | Brier, Log Loss, ECE and reliability for W2 and market baseline | `performance:cohort:*` checkpoint payloads from `finished_match_scoring_projection.py` | `AVAILABLE_IN_CHECKPOINT` | Project existing metrics; do not recompute |
| Directional Outcome | Correct/Wrong/PUSH/VOID/effective N; benchmark remains `NOT_DEFINED` | performance cohort canonical outcome counts | `AVAILABLE_IN_CHECKPOINT` | Project as secondary hierarchy |
| League Performance | Per-league validation/decisive/outcome/Brier/calibration/statistical status | `performance:cohort:league:*` checkpoints | `AVAILABLE_IN_CHECKPOINT` | Project existing cohort fields |
| Forward Validation Records | Counts, outcomes, exclusions, pending/sample state and checkpoint identity | `_dashboard_forward_ledger_from_checkpoints` and `performance:*` checkpoints | `AVAILABLE` | Reuse, omit CLV/ROI |
| History/replay | What was known, reason/outcome summaries and card-hash checks | `src/w2/replay/front_door.py`, date navigation | `AVAILABLE_PURE_FUNCTION` | Reuse against the same DayView |
| Domain freshness | Domain-specific status/as-of; unavailable domains remain explicit | DayView freshness, per-card `data_refresh`, market snapshot freshness | `PARTIAL` | Normalize without inventing timestamps |
| Lineup evidence | Truthful 1/13 verified coverage and per-card readiness | `data_refresh.lineups_status`, P0 evidence authority | `PARTIAL_1_OF_13_VERIFIED` | Expose limitation; no probe |
| External Intelligence | Weather/News/Sentiment/Advanced xG placeholders | No connected source/read model | `NOT_CONNECTED` | Return fixed optional-source state; never mark match incomplete |
| Data & Operations | Read source, checkpoint/degradation/freshness/counts and health | DayView envelope and degradation helpers | `AVAILABLE` | Reuse |
| No-call-on-read | Public reads issue no Provider call and no business write | DayView `provider_calls=0`, `db_writes=0`, API projection tests | `AVAILABLE_AND_TESTED` | Preserve and prove at endpoint level |
| Public CLV/ROI | Zero public reachability | Legacy performance surfaces contain CLV/ROI-era fields | `FORBIDDEN_IN_FINAL_MODEL` | Exclude from unified schema and payload |
| Formal authority | Candidate/Formal/Lock/Production remain OFF | environment policy, current context and product contract | `OFF` | Fixed OFF block with reason |

## Target quality rules

```text
REAL_SOURCE_OR_EXPLICIT_UNAVAILABLE
NO_RECOMPUTE_ON_READ
NO_PROVIDER_CALL_ON_READ
NO_DATABASE_BUSINESS_WRITE_ON_READ
NO_INTERPOLATION
NO_SYNTHETIC_SIGNAL
NO_PUBLIC_CLV
NO_PUBLIC_ROI
NO_MARKET_AS_PICK
NO_RECOMMENDATION_AUTHORITY
```

P2 may add only the missing unified adapter/schema/API/sample/tests. Every
other row above is reused or represented as explicitly unavailable.
