# ARCH-P1-04D M3 canonical simulation read authority

> M3 only switches public simulation reads. It does not delete `pricing_shadow`,
> legacy pick, legacy shim/adapter, or frozen artifacts, and it does not modify
> staging/production data.

## Read authority

All reachable public simulation consumers call
`canonical_public_simulation(card)` and read only `card["simulation"]`:

| Path | Consumer |
|---|---|
| Public/Dashboard | `ReadModelService._dashboard_card_from_matchday` |
| Dashboard scorelines | `dashboard.scorelines._simulation_from_card` |
| DayView projection/count | `day_view._simulation_projection` / `_scoreline_simulations` |
| Formal recommendation | `analysis_calculator.run_simulation_from_card` |
| Formal snapshot evidence | `formal_results._simulation_evidence` |

`pricing_shadow.simulation` remains readable only inside
`simulation_reconciliation.py` for full-object hash comparison. The retained
`run_simulation_from_shadow` compatibility helper has zero runtime callers in
`src`; M3 does not delete it.

## Fail-closed matrix

```text
MATCH                = canonical top-level object
TOP_LEVEL_ONLY       = canonical top-level object
BOTH_UNAVAILABLE     = no public simulation
LEGACY_ONLY          = FAIL_CLOSED
MISMATCH             = FAIL_CLOSED
UNKNOWN_STATE        = FAIL_CLOSED
```

The static reachability guard
`tests/unit/test_public_simulation_read_authority.py` verifies every public
consumer uses the canonical reader, contains no `pricing_shadow` simulation
read, and the retained shadow deserializer has zero runtime callers.

## Reconciliation result

```text
PUBLIC_PRICING_SHADOW_READS = 0
REACHABLE_LEGACY_ONLY = 0
REACHABLE_MISMATCH = 0
RECOMMENDATION_TIER_DELTA = 0
PICK_IDENTITY_DELTA = 0
SCORELINE_OUTPUT_HASH_DELTA = 0
FORMAL_OUTPUT_DELTA = 0
PROVIDER_CALLS = 0
DB_WRITES = 0
```

Parity is covered with equal canonical/shadow full objects and a canonical-only
variant. Recommendation, pick/non-pick identity, scoreline reference/readiness,
and formal fields are identical. Mismatch and legacy-only variants are rejected
before a public response or formal snapshot can be produced.

## Verification

```text
FOCUSED = 75 passed
FULL_PYTEST = 1642 passed / 4 skipped
RUFF = PASS
MYPY = PASS
STAGE1_CONTRACTS = PASS
TRACKED_OUTPUT_GUARD = PASS
CHECK_W2_ALL = PASS
CREDENTIAL_PATTERN_CHECK = PASS
STAGING_OR_PRODUCTION_MUTATION = 0
M4 = NOT_STARTED
```
