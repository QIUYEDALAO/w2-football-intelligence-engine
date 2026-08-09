# W2 Codex Execution Receipt

```text
AUTHORITY = W2_CODEX_EXECUTION_RECEIPT_LATEST
STATUS = COMPLETE_TERMINAL
EXECUTION_TASK = W2_DASHBOARD_OWNER_13IN_TRUTH_READABILITY_REMEDIATION_V1
TERMINAL_GATE = DASHBOARD_OWNER_13IN_TRUTH_READABILITY_ACCEPTANCE_PASS
EXACT_ORIGIN_MAIN_SHA = 5f8066187acc323d23ac4d73da7115100a58aa48
EXACT_CONTEXT_BASE_SHA = 99cd1ed778594f01f4739b96c274fba25e2c6008
EXACT_IMPLEMENTATION_BASE_SHA = 62cf3efc6676d23688c3b6268ca822025b3c9148
EXACT_IMPLEMENTATION_HEAD_SHA = 1661157040a2b84f99934f2858f842b8ccbd350e
PR_NUMBER_OR_NONE = 502,503
PR_STATE = MERGED,MERGED
PR_502_HEAD = b260af16567b91e7a9b8c93cb7fa7af93501d466
PR_502_MERGE = ae2c14d7ed27c2272fbd399729040df3b640d0cf
PR_503_HEAD = 1661157040a2b84f99934f2858f842b8ccbd350e
PR_503_MERGE = 5f8066187acc323d23ac4d73da7115100a58aa48
CI_RUN_IDS = 31315499729,31316484178,31316964353
CI_TERMINAL_STATUS = PASS
RELEASE_REQUIRED = PASS_EXACT_HEAD_502_AND_503
CHANGED_FILES = 12_LISTED_BELOW
TEST_EVIDENCE = PASS_LISTED_BELOW
RUNTIME_OR_READ_EVIDENCE = PASS_LISTED_BELOW
FINAL_DEPLOYED_SOURCE_SHA = 1661157040a2b84f99934f2858f842b8ccbd350e
PROVIDER_CALLS = 0
DB_BUSINESS_WRITES = 0
SCHEDULER_OR_CADENCE_CHANGED = false
WHITELIST_CHANGED = false
MODEL_OR_THRESHOLD_CHANGED = false
PHASE_0_5_REEXECUTED = false
ROUND_4_STATUS = NOT_STARTED
CANDIDATE_STATUS = OFF
FORMAL_STATUS = OFF
LOCK_STATUS = OFF
PRODUCTION_STATUS = OFF
P6_STATUS = NOT_AUTHORIZED
REPOSITORY_HYGIENE = PASS
UNRESOLVED_ITEMS = NONE_WITHIN_AUTHORIZED_SCOPE
NEXT_GATE = DASHBOARD_OWNER_13IN_TRUTH_READABILITY_ACCEPTANCE_PASS_STOP
```

## Result

PR #502 closed D13-01 through D13-13 against the real unified Dashboard read
model. It preserved the existing architecture and added only the source-bound
identity, statistical-readiness, exclusion-explainability and presentation
fields required by the Owner authority. It also reflowed the cockpit for the
seven required laptop/desktop viewports and localized primary truth states.

The first deployed 1280x720 real-data inspection correctly detected a remaining
overflow: persisted market prices are aggregate objects shaped as
`{median,min,max}`, but the generic UI renderer exposed the object text. PR #503
was a bounded three-file correction that renders the persisted median, keeps
the object as source truth, and closes the remaining raw primary labels. No
read-time Provider call, simulation, interpolation, or business write was
introduced.

## Changed files

```text
DASHBOARD_DATA_CONTRACT.md
apps/web/e2e/decision-contract.spec.ts
apps/web/src/components/IntelligenceConsole.tsx
apps/web/src/intelligence.css
apps/web/src/lib/labels.ts
apps/web/src/types/intelligenceWorkspace.ts
examples/dashboard_intelligence_workspace.v1.json
src/w2/api/repository.py
src/w2/api/schemas.py
src/w2/dashboard/workspace.py
tests/contract/test_dashboard_intelligence_workspace_contract.py
tests/unit/test_dashboard_intelligence_workspace.py
```

PR #503 touched only:

```text
apps/web/e2e/decision-contract.spec.ts
apps/web/src/components/IntelligenceConsole.tsx
apps/web/src/lib/labels.ts
```

## Contract and test evidence

Deterministic acceptance covers numeric Provider competition IDs, unresolved
identity fail-closed copy, stale `next_eval_at`, n=5 with no probability-quality
evidence, probability-primary degradation, exclusion counts/share/reasons,
deduplicated market states, unavailable scoreline wording, Provider budget not
read semantics, canonical enum localization, ISO date display, distinct health
and quota labels, and 13-inch geometry/readability.

Local evidence:

```text
focused D13 backend/unit/contract = 21 passed
CI-equivalent unit/contract shards = 20 + 747 + 567 + 1002 passed
integration shards = 12 + 71 passed
Web E2E after PR #502 = 49 passed
PR #503 focused Web regression = 31 passed
PR #503 full Web E2E = 49 passed
TypeScript typecheck = PASS
Web build = PASS
Ruff = PASS
MyPy = PASS
secret scan = PASS
tracked generated outputs = PASS
repository diff/hygiene checks = PASS
```

Exact-head GitHub evidence:

```text
PR_502_FULL_CI = 31315499729 @ b260af16567b91e7a9b8c93cb7fa7af93501d466 = PASS
PR_502_RELEASE_REQUIRED = PASS
PR_503_FULL_CI = 31316484178 @ 1661157040a2b84f99934f2858f842b8ccbd350e = PASS
PR_503_RELEASE_REQUIRED = PASS
MAIN_PROMOTION = 31316964353 @ 5f8066187acc323d23ac4d73da7115100a58aa48 = PASS
```

## Deployment and runtime evidence

The final images were transported only through the frozen local OCI relay
path, verified by digest, imported, and warm-switched. Six-service health,
ready, release-sync and rollback checks passed.

```text
IMAGE_TRANSPORT = LOCAL_OCI_RELAY_PRIMARY
PYTHON_IMAGE_DIGEST = sha256:4e3c0c2011a705021dd897716888e4063d0f0b3d7c124bcf2f86d25b5a7683f0
WEB_IMAGE_DIGEST = sha256:46ecabc17b3fb9e6f14b10e7e612c47a9fb8cafbb9dce6aa3ff6dc9100680778
PREHEAT_SECONDS = 210
WARM_SWITCH_SECONDS = 47
HEALTH = PASS
READY = PASS
RELEASE_SYNC = PASS
ROLLBACK = false
FINAL_RESULT = PASS
```

The final public Web and API both report exact source
`1661157040a2b84f99934f2858f842b8ccbd350e`. The unified endpoint returned
schema `w2.dashboard-intelligence-workspace.v1`, date `2026-08-09`, authority
`NEW_INTELLIGENCE_WORKSPACE_ONLY`, 10 real matches, 10 league rows, exact
13-league whitelist, `SHADOW_ONLY`, all four promotion states `OFF`,
`provider_calls=0`, `db_writes=0`, and `no_call_on_read=true`.

## Final deployed browser acceptance

The post-PR #503 in-app browser inspected the deployed page at 1280x720 using
real persisted payload data:

```text
inner_width = 1280
inner_height = 720
client_width = 1265
scroll_width = 1265
horizontal_overflow = false
persisted_market_price_median_visible = 1.89
raw_price_object_leak = false
raw_DATA_FIELD_STALE_primary_copy = false
raw_PRICE_MOVEMENT_primary_copy = false
raw_BLOCKED_DAY_primary_copy = false
zh_CN_数据字段已过期 = true
zh_CN_盘口变化 = true
zh_CN_当日阻塞 = true
```

The seven deterministic responsive cases remain covered at 1280x720,
1280x800, 1366x768, 1440x900, 1512x982, 1536x1024 and 1920x1080, including
computed primary font floors, intended reflow, panel geometry, sticky-header
clearance, nested scroll containment and horizontal overflow.

## Finding closure

```text
D13_01 = CLOSED_PASS
D13_02 = CLOSED_PASS
D13_03 = CLOSED_PASS
D13_04 = CLOSED_PASS
D13_05 = CLOSED_PASS
D13_06 = CLOSED_PASS
D13_07 = CLOSED_PASS
D13_08 = CLOSED_PASS
D13_09 = CLOSED_PASS
D13_10 = CLOSED_PASS
D13_11 = CLOSED_PASS
D13_12 = CLOSED_PASS
D13_13 = CLOSED_PASS
```

## Frozen controls and stop

No Provider call, DB business write, Scheduler/cadence change, whitelist
change, model/factor/threshold change, Phase0.5 re-execution, external
intelligence activation, Round4 start, P6 execution, Candidate/Formal/Lock/
Production enablement or real-money authority occurred.

The task stops at
`DASHBOARD_OWNER_13IN_TRUTH_READABILITY_ACCEPTANCE_PASS`. There is no
authorized next code phase.
