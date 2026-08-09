# NEXT ACTION

```text
ACTIVE_NEXT_ACTION = EXECUTE_DASHBOARD_OWNER_13IN_TRUTH_READABILITY_REMEDIATION
CURRENT_GATE = DASHBOARD_OWNER_13IN_REMEDIATION_ACTIVE
AUTHORITY = DASHBOARD_OWNER_13IN_TRUTH_READABILITY_REMEDIATION.md
BASE_MAIN = 62cf3efc6676d23688c3b6268ca822025b3c9148
PR_501 = MERGED_DEPLOYED_BUT_OWNER_UX_PASS_REVOKED
TRACK_A = TRACK_A_CLOSED_PASS
ROUND_4 = NOT_STARTED
P6 = NOT_AUTHORIZED
TERMINAL_TARGET = DASHBOARD_OWNER_13IN_TRUTH_READABILITY_ACCEPTANCE_PASS
```

## Why this workstream is reopened

PR #501 passed technical CI/deployment, but real 13-inch Owner inspection exposed conclusion-trust and readability defects that the previous deterministic screenshot gates did not catch.

The previous `DASHBOARD_OWNER_VISUAL_UX_ACCEPTANCE_PASS` is not the final Owner verdict. It is superseded by the current bounded remediation authority.

## Binding read order

```text
1. CODEX_EXECUTION_PROTOCOL.md
2. CURRENT_STATE.yaml
3. NEXT_ACTION.md
4. DASHBOARD_OWNER_13IN_TRUTH_READABILITY_REMEDIATION.md
5. DASHBOARD_DATA_CONTRACT.md
6. DASHBOARD_INTELLIGENCE_WORKSPACE_PRODUCT_SPEC.md
7. current unified workspace implementation on origin/main
8. current performance checkpoint/read-model projection code
9. current competition registry / identity authority
10. PR #501 evidence only as historical implementation evidence, not acceptance authority
```

## Execute continuously

Close all D13-01 through D13-13 findings in one continuous task. Ordinary in-scope implementation, test, responsive, localization, read-model adapter, identity-resolution, visual and deployment failures must be fixed and revalidated without intermediate Owner relay.

Highest-priority requirements:

```text
D13-01 league names, not raw numeric provider IDs
D13-02 no past timestamp labelled 下次评估
D13-03 n=5/no-probability-evidence cannot show authoritative 可用 80.0%
D13-04 directional accuracy cannot dominate when probability metrics are unavailable
D13-05 exclusion reason distribution visible for excluded validation cohort
D13-06 13-inch layout reflows instead of using 6-9px primary text
D13-07 no overlap/sticky-cover/nested-scroll geometry break
```

Then close D13-08 through D13-13 consistency/rendering findings.

Do not solve D13-03 by arbitrarily changing `MIN_DECISIVE_SAMPLES_FOR_RATE=5`. Keep stored tracking truth and add a stricter public display-readiness gate grounded in probability-primary evidence. Do not call Provider to solve budget/identity/readability problems.

## Responsive acceptance

Test at least:

```text
1280x720
1280x800
1366x768
1440x900
1512x982
1536x1024
1920x1080
```

Assertions must include representative computed font sizes, expected column/reflow behavior, scroll affordances, panel non-overlap, sticky-header clearance, and readable primary values. `No horizontal overflow` alone is insufficient.

## Truth acceptance

Add deterministic cases for:

```text
numeric provider league IDs
past next_eval_at
small decisive sample + percentage + missing Brier/calibration
probability metrics unavailable + directional accuracy available
large excluded cohort + exclusion-reason distribution
repeated market statuses
unavailable scoreline
provider budget UNKNOWN with zero Provider call
ADVISORY / MARKET_NOT_READY / IDENTITY_NOT_READY
ISO date display
separate health and provider-budget labels
```

## Merge and VPS deployment

When all local/focused/full gates pass:

1. exact-head Full CI + `RELEASE_REQUIRED` PASS;
2. merge exact accepted head automatically;
3. deploy through `LOCAL_OCI_RELAY_PRIMARY` only;
4. warm-switch and verify exact Web/API identity, six-service health, unified endpoint, real-data/real-empty state, provider_calls=0, db business writes=0 and unchanged runtime stop lines;
5. perform laptop-sized visual/readability smoke when the available browser environment can access the deployed page; never fabricate a visual PASS if it cannot.

## Stop

Stop only at one of:

```text
DASHBOARD_OWNER_13IN_TRUTH_READABILITY_ACCEPTANCE_PASS
DASHBOARD_OWNER_13IN_REMEDIATION_BLOCKED_SOURCE_EVIDENCE
DASHBOARD_OWNER_13IN_REMEDIATION_ROLLED_BACK
```

Even on PASS:

```text
ROUND_4_START = NOT_AUTHORIZED
P6_EXECUTION = NOT_AUTHORIZED
NEW_PROVIDER_OR_PLAN = NOT_AUTHORIZED
MANUAL_PROVIDER_PROBE = FORBIDDEN
SCHEDULER_OR_CADENCE_CHANGE = NOT_AUTHORIZED
ACTIVE_WHITELIST_CHANGE = NOT_AUTHORIZED
MODEL_FACTOR_THRESHOLD_RETRAINING = NOT_AUTHORIZED
EXTERNAL_INTELLIGENCE_ACTIVATION = NOT_AUTHORIZED
PHASE_0_5_REEXECUTION = FORBIDDEN
H_RESULT_ACCESS = PERMANENTLY_CLOSED
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
REAL_MONEY = NOT_AUTHORIZED
IMAGE_TRANSPORT = LOCAL_OCI_RELAY_PRIMARY
```
