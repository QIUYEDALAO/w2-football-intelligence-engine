# NEXT ACTION

```text
ACTIVE_NEXT_ACTION = EXECUTE_SHADOW_CANDIDATE_INPUT_AUTHORITY_CONVERGENCE
CURRENT_GATE = SHADOW_CANDIDATE_INPUT_AUTHORITY_REMEDIATION_ACTIVE
AUTHORITY = SHADOW_CANDIDATE_INPUT_AUTHORITY_CONVERGENCE.md
BASE_MAIN = 001b1bae8e5276597dc506e0cd3cb40dbd180fb5
BASE_RELEASE = PR_517_MERGED_DEPLOYED
SC18_01_THROUGH_SC18_07 = OPEN
SHADOW_CANDIDATE = KEEP_ACTIVE_SHADOW_ONLY
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
ROUND_4 = NOT_STARTED
P6 = NOT_AUTHORIZED
TERMINAL_GATE = OWNER_SHADOW_CANDIDATE_INPUT_CHAIN_REREVIEW
```

## Binding correction

Do not continue treating natural evidence accumulation as the only remaining task.

PR #517 correctly activated the existing SHADOW/CANDIDATE ledger, settlement and validation loop, and the current zero-candidate result remains truthful. Owner postdeploy review has now exposed a bounded upstream input-authority problem that must be closed before any claim that the Formal approval threshold has been met:

- public labels still silently fall back to English;
- per-market radar evidence, exact candidate quote identity, match readiness and RecommendationDecisionV4 blockers are not presented under one coherent market-scoped authority;
- one failing market can dominate the public whole-match diagnosis while another market has usable evidence;
- Stage14 coverage remains unaudited/partial for multiple domains in at least some runtime competitions.

The competition-profile field `enabled: false` is not a valid standalone runtime diagnosis. In staging the effective state is the OR of profile, future-refresh and matchday policy authorities.

## Binding read order

```text
1. CODEX_EXECUTION_PROTOCOL.md
2. CURRENT_STATE.yaml
3. NEXT_ACTION.md
4. SHADOW_CANDIDATE_INPUT_AUTHORITY_CONVERGENCE.md
5. current main at 001b1bae8e5276597dc506e0cd3cb40dbd180fb5
6. RecommendationDecisionV4 and quote-identity contracts
7. Round3 Market Radar / Model Lab contracts
8. data-readiness and decision-adapter contracts
9. canonical team identity authority
10. existing Stage14 scripts and whitelist work order
11. PR #517 release evidence as deployment baseline, not final input-chain acceptance
```

## Execute continuously

In one continuous workstream from current `main`:

1. **SC18-01:** produce the source-bound, read-only authority trace for fixture `1493049` and comparison fixtures; identify exactly where `market` / `odds` becomes missing.
2. **SC18-02:** establish per-market observation, trend, cross-sectional, model-diagnostic and candidate-eligibility states; prove AH depth `1` cannot erase independent OU depth `7` evidence.
3. **SC18-03:** align Round3 radar, exact quote identity, selected market candidate and match readiness without converting radar medians into an executable quote or weakening RecommendationDecisionV4.
4. **SC18-04:** expose public `PARTIAL` market semantics and market-scoped blockers; do not use the first/worst relation as an unexplained whole-match diagnosis.
5. **SC18-05:** move public team-label authority to reviewed canonical identity/config data, create measurable missing-label inventories, and make every public status/reason Chinese-first. No silent raw-English fallback and no invented translation.
6. **SC18-06:** run the existing Stage14 audit for the exact active 13-competition scope and produce the full coverage matrix, including effective staging enable sources. Audit only; do not bypass or activate unsupported coverage.
7. **SC18-07:** add real-shape regressions, run focused/full tests and all repository gates, require exact-head Full CI and `RELEASE_REQUIRED`, merge automatically, deploy by Owner-local OCI relay, and perform live rereview.
8. Refresh `CURRENT_STATE.yaml`, `NEXT_ACTION.md` and the Round4 packet exact release identity only, then stop.

Ordinary implementation, fixture, localization, contract, test, CSS, CI and deployment-preparation failures are in scope:

```text
fix -> revalidate -> continue
```

No Owner relay is required between these steps. If Stage14 completion requires a new Provider/plan, new dataset, external-intelligence activation, cadence change, whitelist change, model/threshold change or manual data authority, produce an Owner decision packet but continue all independent work.

## Mandatory acceptance cases

```text
AH 1 bookmaker + OU 7 bookmakers
=> AH insufficient; OU independently represented; whole match PARTIAL

OU exact quote identity complete + AH incomplete
=> OU may proceed independently if all unchanged V4 model/identity gates pass

model simulation not ready
=> market evidence stays visible; candidate stays NOT_READY for MODEL reason

no exact executable quote identity
=> no candidate; radar aggregate must not be promoted into one

unmapped team public label
=> explicit auditable label/identity gap, not silent English success

unmapped public enum
=> CI failure or explicit Chinese fallback state; raw code only in technical details
```

## Evidence accumulation during remediation

The existing natural SHADOW/CANDIDATE schedule, forward ledger, settlement and validation loop stays active. Existing ledger evidence is retained.

Formal remains off. No affected candidate/input identity may be used to claim that the Formal evidence threshold has been met until the remediated exact release passes postdeploy rereview.

## Terminal classifications

```text
OWNER_SHADOW_CANDIDATE_INPUT_CHAIN_REREVIEW
SHADOW_CANDIDATE_INPUT_CHAIN_DEPLOYMENT_ROLLED_BACK
SHADOW_CANDIDATE_INPUT_CHAIN_SCOPE_BLOCKED_OWNER_DECISION_REQUIRED
```

If a critical postdeploy gate fails after merge, automatically roll back to `001b1bae8e5276597dc506e0cd3cb40dbd180fb5` and stop with evidence.

## Frozen stop lines

```text
NEW_PROVIDER_OR_PLAN = NOT_AUTHORIZED
MANUAL_PROVIDER_PROBE = FORBIDDEN
SCHEDULER_OR_CADENCE_CHANGE = NOT_AUTHORIZED
ACTIVE_WHITELIST_CHANGE = NOT_AUTHORIZED
MODEL_FACTOR_THRESHOLD_CHANGE = NOT_AUTHORIZED
MODEL_RETRAINING = NOT_AUTHORIZED
BOOKMAKER_DEPTH_THRESHOLD_CHANGE = NOT_AUTHORIZED
MARKET_DIRECTION_BENCHMARK_DEFINITION = NOT_AUTHORIZED
EXTERNAL_INTELLIGENCE_ACTIVATION = NOT_AUTHORIZED
PHASE_0_5_REEXECUTION = FORBIDDEN
H_RESULT_ACCESS = PERMANENTLY_CLOSED
ROUND_4_START = NOT_AUTHORIZED
P6_EXECUTION = NOT_AUTHORIZED
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
REAL_MONEY = OFF
READ_PROVIDER_CALLS = 0_REQUIRED
READ_DB_BUSINESS_WRITES = 0_REQUIRED
VPS_DIRECT_GHCR_BULK_IMAGE_PULL = FORBIDDEN_AS_PRIMARY_TRANSPORT
IMAGE_TRANSPORT = LOCAL_OCI_RELAY_PRIMARY
DELETE_PROTECTED_HISTORICAL_EVIDENCE = FORBIDDEN
```