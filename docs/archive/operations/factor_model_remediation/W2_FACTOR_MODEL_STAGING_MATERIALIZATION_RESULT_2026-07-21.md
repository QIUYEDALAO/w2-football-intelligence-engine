# W2 FACTOR-MODEL-STAGING-MATERIALIZATION Result

Generated: 2026-07-21

## GitHub Context

- PR: #370
- Remote head checked with `git ls-remote`: `749a8411d1ad5657d380b095b96fa7a0af69279b`
- Base integration branch checked with `git ls-remote`: `d6dcf92e5c65e43420c139b8108e0156c5b6f235`
- This file is a GitHub context sync artifact only.
- No production deploy was performed.
- No PR merge or CI requirement is implied by this context update.

## Execution Scope

Staging execution was performed against the real staging PostgreSQL and controlled provider environment.

Controls:

- `W2_PROVIDER_SCHEDULER_ENABLED=false`
- `W2_PROVIDER_CALLS_DISABLED=true` after execution
- No scheduler container observed running
- Recommendations written: `0`
- Recommendation locks written: `0`
- OFFICIAL manifests written: `0`

## Materialization Results

| Item | Result |
| --- | ---: |
| Allsvenskan provider team identities | 16 |
| Provider team crosswalks | 16 |
| READY fixture identities | 14 |
| Canonical match history rows | 102 |
| Distinct historical fixtures | 51 |
| Rating snapshots | 16 |
| Team xG match rows | 28 |
| Rolling xG snapshots | 1 |
| H2H endpoint captures | 2 |
| H2H historical meetings per smoke fixture | 5 / 5 |
| Odds endpoint captures | 2 |
| Recommendations delta | 0 |
| Locks delta | 0 |
| OFFICIAL delta | 0 |

## Provider Captures

| Checkpoint | Endpoint | Captures | Response Count Sum |
| --- | --- | ---: | ---: |
| CONTROLLED_FACTOR_MODEL_REMEDIATION | fixtures | 16 | 80 |
| CONTROLLED_FACTOR_MODEL_REMEDIATION | h2h | 2 | 10 |
| CONTROLLED_FACTOR_MODEL_REMEDIATION | statistics | 41 | 82 |
| CONTROLLED_FACTOR_MODEL_REMEDIATION_ODDS | odds | 2 | 2 |

Last observed provider quota after successful odds capture: `daily_remaining=7424`.

## Smoke Fixtures

| Provider Fixture | Canonical Fixture | Home Provider Team | Away Provider Team | Identity Status |
| --- | --- | --- | --- | --- |
| 1494218 | api_football:1494218 | 2172 | 364 | PROVIDER_PRIMARY_READY |
| 1494224 | api_football:1494224 | 2241 | 2166 | PROVIDER_PRIMARY_READY |

## Per-Team History for Smoke Teams

| Provider Team | Canonical History Rows | Rating Snapshot |
| --- | ---: | --- |
| 2166 | 10 | READY |
| 2172 | 10 | READY |
| 2241 | 10 | READY |
| 364 | 10 | READY |

F3 rest/fitness inputs are materialized for both smoke fixtures because all four smoke teams have recent canonical history.

F7 rating snapshots are materialized for all four smoke teams.

## xG / F9 Status

Provider statistics were probed and real xG rows were written where the provider exposed xG fields.

Smoke-team xG match availability:

| Team | xG Match Rows |
| --- | ---: |
| 2172 | 3 |
| 364 | 1 |
| 2241 | 2 |
| 2166 | 0 |

Only one rolling xG snapshot could be produced:

| Team | Fixture | Match Count | Rolling xG For | Rolling xG Against |
| --- | --- | ---: | ---: | ---: |
| 2172 | 1494218 | 3 | 1.12 | 2.45 |

F9 is therefore not READY for the two-fixture smoke recommendation chain.

Source blocker:

```text
XG_SAMPLE_INSUFFICIENT_FOR_SMOKE_FIXTURES
```

This is not a proxy xG result. No proxy xG was generated.

## Odds / Market Evidence Status

Provider odds were captured for both smoke fixtures.

| Provider Fixture | Total Odds Observations | 1X2 | AH | OU |
| --- | ---: | ---: | ---: | ---: |
| 1494218 | 945 | 90 | 372 | 483 |
| 1494224 | 975 | 81 | 384 | 510 |

Direct repository reads returned latest fixture-scoped odds:

| Fixture Query | Latest Reader Rows |
| --- | ---: |
| 1494218 | 315 |
| 1494224 | 325 |
| api_football:1494218 | 315 |
| api_football:1494224 | 325 |

However, `ReadModelService.public_analysis_card_bounded` still produced:

```text
data_status=BLOCKED
decision=SKIP
decision_tier=NOT_READY
market_observations=0
AH model_probability=NOT_READY
OU model_probability=NOT_READY
```

Observed authority/read-model issue:

```text
READ_MODEL_FACTOR_PROJECTION_NOT_CONSUMING_MATERIALIZED_STAGING_FACTS
```

The repository can read odds rows, but the public analysis card still does not project them into readiness/model probability. This prevents market probability, model probability, delta, EV, uncertainty, and V3 NO_EDGE/ANALYSIS_PICK from being computed.

## Final Verdict

The staging materialization partially succeeded:

- Team identity: READY
- Canonical match history: READY
- F3 input materialization: READY for smoke fixtures
- F6 H2H: READY for smoke fixtures
- F7 rating snapshots: READY for smoke fixtures
- Provider odds evidence: CAPTURED
- F9 rolling xG: BLOCKED by insufficient provider xG sample for smoke fixtures
- Model probability: NOT_COMPUTABLE
- Market probability in public analysis card: NOT_COMPUTABLE
- V3 outcome: NOT_READY / SKIP only

Final state:

```text
ANALYSIS_CHAIN_STAGING_EXECUTION_FAILED
FORMAL_DISABLED
LOCK_DISABLED
PRODUCTION_DISABLED
MANUAL_APPROVAL_REQUIRED
```

The failure is not missing provider credentials and not absence of odds data. The remaining blocker is that the already materialized staging facts are not fully consumed by the public analysis/model probability read chain, and F9 has insufficient smoke-team rolling xG coverage.
