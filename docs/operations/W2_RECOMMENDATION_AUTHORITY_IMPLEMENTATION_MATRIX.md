# W2 recommendation authority implementation matrix

Baseline: `ae28912470def2ca0b47fa1897c2581cb51d9f50`

| Scope | Classification | Baseline evidence | Required closure |
|---|---|---|---|
| `market_batch_audit` | `VERIFIED_TEST_ONLY` | 6 direct test calls; 0 production-reachable callers | Delete symbol and its test-only assertions |
| `_ah_pair` | `VERIFIED_TEST_ONLY` | Only called by `market_batch_audit`; 0 production-reachable callers | Delete with parent selector |
| `_pair` in `matchday/intake_v2.py` | `VERIFIED_TEST_ONLY` | Only called by `market_batch_audit`; 0 production-reachable callers | Delete with parent selector |
| `enrichment_status` | `VERIFIED_TEST_ONLY` | 3 direct calls in one unit test; 0 production-reachable callers | Delete symbol and dedicated test |
| `_lineup_response_status` | `VERIFIED_TEST_ONLY` | Only called by `enrichment_status`; 0 production-reachable callers | Delete with parent policy |
| Public direction | `VERIFIED_ACTIVE` | Direction can be written by multi-market bookmaker intent, market-candidate projection, and Formal reselection | One V4 authority consumes one `AuthoritativeRecommendationInput`; diagnostics cannot select a public direction |
| Public decision authority | `VERIFIED_ACTIVE` | V3 has two constructible projectors and DayView can rebuild a current pick | V4 is the only current-public authority; V3 is history/read-only |
| Legacy recommendation | `NOT_REPRODUCED` | Current non-Formal legacy recommendation projection strips actionable direction fields before publication | Keep display/history/settlement only and add a regression proving it cannot create a current public pick |
| V3 identity | `VERIFIED_ACTIVE` | V3 does not require season, kickoff identity, serializer/schema identities, or model input manifest identity; a minimal fixture/market/selection payload can become `ANALYSIS_PICK` | Introduce V4 with every required identity field and fail closed on omission |
| V3 hashing | `VERIFIED_ACTIVE` | `recommendation_decision_v3.py` uses local `json.dumps(sort_keys=True)` SHA writers | Preserve historical V3; all V4 hashes use `canonical_sha256` and a dedicated domain |
| Formal fair odds | `VERIFIED_ACTIVE_CAPABILITY_OFF` | Formal computes `1 / effective_probability` after independent HOME/AWAY selection | Consume the V4-selected candidate and `fair_decimal_odds(settlement_distribution)` |
| Analysis admission | `VERIFIED_ACTIVE` | Effective settlement scalar minus proportional-devig probability is gated at 5pp | Keep probability delta diagnostic only; gate on cash-flow-equivalent price edge, EV, and EV-minus-SE |
| Lineup readiness | `VERIFIED_ACTIVE` | Analysis accepts two non-empty `startXI`; repository separately checks 11+11, 22 unique IDs, fixture teams, pre-kickoff identity and replay conflicts | One pure authoritative validator used by all four paths |
| Dashboard risk | `VERIFIED_ACTIVE` | One high/medium/low field mixes event, data, model, runtime and lineup states; generic medium falls back to “lineup unconfirmed” | Four explicit axes with reason-code/display parity |
| Existing complete real-fixture bundle | `NOT_REPRODUCED` | No checked-in or locally discovered bundle yet proves raw-to-card byte-identical replay | Export a private production bundle or report exact missing fields before the bounded canary rule applies |

Baseline scoped counts:

- `PUBLIC_DIRECTION_WRITER_COUNT = 3`
- `PUBLIC_DECISION_AUTHORITY_COUNT = 2`
- `LEGACY_RECOMMENDATION_PUBLIC_CONSUMER_COUNT = 0`
- `PRODUCTION_REACHABLE_DEAD_SYMBOL_CALLER_COUNT = 0`
- `DIRECT_TEST_ONLY_CALL_SITE_COUNT = 9`
- `UNIQUE_DIRECT_TEST_ONLY_CALLER_FUNCTION_COUNT = 7`

Not reproduced: complete production quote candidates are not devoid of provenance, and Boss Console is not devoid of every risk subfield. The defects are that V3 does not enforce that provenance and the public headline/filter still collapses unrelated risk domains.

## Implemented closure

| Contract | Final result |
|---|---|
| Public direction writer | `1` — V4 selected candidate |
| Public decision authority | `1` — `w2.recommendation_decision.v4` |
| Legacy current-public consumers | `0`; V3 is history/settlement only |
| Required immutable identity | `21/21` fields with single-field mutation coverage |
| Formal pricing | Five-state cash-flow fair odds; independent oracle `PASS` |
| Analysis admission | EV, EV-minus-SE and cash-flow price edge; legacy 5pp delta diagnostic only |
| Lineup readiness | One validator consumed by all four paths; numeric adjustment `OFF` |
| Dashboard risk | Four independent axes with backend/frontend parity `PASS` |
| Dead code | Six symbols and nine direct test-only call sites removed; production callers removed `0` |
| Real fixture replay | Saved four-endpoint sequence, network `0`, Provider `0`, byte-identical twice |

Replay evidence is recorded in
`W2_RECOMMENDATION_AUTHORITY_REAL_FIXTURE_REPLAY_RECEIPT_20260804.md`; the private raw bundle is not
tracked.
