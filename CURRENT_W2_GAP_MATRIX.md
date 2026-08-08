# Current W2 Gap Matrix

```text
AUTHORITY = W2_DASHBOARD_P1_CURRENT_GAP_MATRIX_V1
BASE_MAIN_SHA = f0fe9d332d05a84f1ef04be86fd9fb44b69d69e3
P1_CONCLUSION = NO_UNRESOLVED_SOURCE_FRESHNESS_READINESS_CONFLICT
P2_ENTRY = AUTHORIZED
```

| Gap | Evidence at latest main | Product impact | P2 closure | Not authorized |
|---|---|---|---|---|
| No final unified schema/API | Existing `/dashboard`, `/dashboard/day-view`, `/performance` and replay surfaces are separate | P3/P4 lack one stable contract | Add one `w2.dashboard-intelligence-workspace.v1` read model and endpoint | UI/P3 implementation |
| No deterministic unified sample | Existing tests use component-specific fixtures | Review cannot inspect one final payload | Commit one sample validated by the Pydantic schema | Synthetic runtime data |
| Probability Brier omitted from current public performance response | `performance:cohort:*` payload contains `model_brier`, `market_brier`, delta; `PerformanceCalibrationResponse` omits them | Probability Validation is incomplete | Read and project existing checkpoint values | Recompute metrics on API reads |
| Validation data is split from DayView | DayView embeds a bounded forward-ledger projection; detailed probability fields remain checkpoint-only | Final payload lacks one validation block | Join read-only projections in the unified adapter | New scoring engine |
| API-Football Prediction not projected | `predictions` table/model exists, but no current checkpoint/DayView field binds a provider prediction | Three-party Model Lab cannot truthfully show a value | Emit `NOT_AVAILABLE` + `API_FOOTBALL_PREDICTION_NOT_PROJECTED` | Provider call or direct unbounded query |
| Freshness is not one normalized domain map | Page/odds timestamps and per-card enrichment statuses are distributed | UI could incorrectly apply one stale rule | Add domain entries with source/as-of/status/authority and explicit unavailable states | Universal stale threshold or cadence change |
| External Intelligence not connected | No Weather/News/Sentiment/Advanced-xG source | Reserved panels have no data | Emit `NOT_CONNECTED`, optional and non-blocking | Connect providers |
| Lineup coverage is not proven for 12/13 leagues | Owner evidence verifies only Chinese Super League | Global lineup claims would be false | Carry `1_OF_13_VERIFIED` and per-card status | Probe Provider or claim 13/13 |
| Replay is not in the Dashboard API | Pure replay front door exists and is tested | Unified payload lacks historical evidence summary | Invoke existing pure replay adapter over the same DayView | New replay engine |
| Final Attention/replay field binding is incomplete | Existing intelligence/readiness evidence and replay `decision_summary` already exist | P3 would otherwise reconstruct approved semantics | Bind affected domains/factual summary/readiness/next evaluation and preserve `decision_summary` | New intelligence or replay engine |
| Final state/risk schema is not fail-closed | Production already defines exact seven states and four uppercase risk axes | Invalid/lowercase/market risk fixtures can pass | Lock the schema to production enums/axes and add negative contract tests | Second risk model or new signals |
| Final scoreline names weaken source semantics | Existing seeded projection emits 10,000 samples and explicit unconditional probability | Generic probability can become ambiguous | Preserve `sample_count` + `unconditional_probability`; READY requires 10,000 | Simulation or probability derivation on read |
| Legacy performance includes public CLV surfaces | `/performance` and legacy adapters carry CLV fields | Final product would violate P0 if copied wholesale | Whitelist only approved probability/directional/league fields | Delete or redesign legacy endpoint in P2 |
| Legacy DayView fields include old recommendation semantics | `decision_tier`, `lock_eligible`, recommendations remain compatibility inputs | Direct exposure could restore old product authority | Translate to W2 Analysis/Readiness and fixed Formal OFF blocks | Rebuild Boss L1/L2 or old ranking |
| No endpoint-level unified no-call proof | DayView/performance paths have separate zero-write tests | Owner Review B needs exact new endpoint evidence | Repeated-read test asserts stable payload, zero Provider calls/writes | Runtime/provider probe |

## P1 resolution decision

All P2-required fields have either:

1. an existing bounded source to reuse; or
2. an approved explicit unavailable/status representation.

No conflict requires Provider access, a migration, Scheduler/cadence change,
whitelist expansion, model work, threshold work, Phase 0.5, Round 4, or P3.
