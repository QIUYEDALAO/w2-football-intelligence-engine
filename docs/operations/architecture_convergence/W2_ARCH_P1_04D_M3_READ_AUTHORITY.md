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

## Remaining compatibility-chain reachability

The retained compatibility code is no longer selected by the public runtime:

```text
LEGACY_PICK_RUNTIME_REACHABLE = 0
LEGACY_SHIM_RUNTIME_REACHABLE = 0
LEGACY_ADAPTER_RUNTIME_REACHABLE = 0
```

- current and fallback cards carry an explicit canonical `decision_tier` before
  decision-contract projection;
- frozen cards consume their stored canonical `decision_contract`;
- Dashboard selects only `primary_market` or the stored contract pick and never
  calls `_public_market_is_legacy_pick`;
- Dashboard recommendation projection fails closed without `decision_tier` and
  has no `legacy_decision_view` caller in `src`;
- the adapter's retained pre-LMM fallback (`_legacy_decision_tier`) is guarded
  by explicit canonical tier input and records zero activations across current,
  frozen, fallback, Dashboard, DayView, and formal probes.

Contradictory legacy-only fields do not change recommendation, decision tier,
pick/non-pick identity, scoreline reference, or formal output on a canonical
card. A pre-LMM pick without canonical selection now fails closed; no retained
compatibility function is deleted in M3.

The same fixed-as-of canonical current and fallback probes were executed against
`d92f25d74577c1b6bd1181e7915a1eb5ea329082` and this change. Their selected
public business payloads are byte-equal:

```text
RECOMMENDATION_TIER_DELTA = 0
PICK_IDENTITY_DELTA = 0
SCORELINE_OUTPUT_HASH_DELTA = 0
FORMAL_OUTPUT_DELTA = 0
```

## Verification

```text
FOCUSED = 90 passed
FULL_PYTEST = 1645 passed / 4 skipped
RUFF = PASS
MYPY = PASS
STAGE1_CONTRACTS = PASS
TRACKED_OUTPUT_GUARD = PASS
CHECK_W2_ALL = PASS
CREDENTIAL_PATTERN_CHECK = PASS
STAGING_OR_PRODUCTION_MUTATION = 0
M4 = NOT_STARTED
```
