# W2 Codex Execution Receipt

```text
AUTHORITY = W2_CODEX_EXECUTION_RECEIPT_LATEST
STATUS = COMPLETE_TERMINAL
EXECUTION_TASK = W2_DASHBOARD_OWNER_CANONICAL_IDENTITY_COLLECTION_SEMANTICS_REMEDIATION_V1
TERMINAL_GATE = DASHBOARD_OWNER_CANONICAL_TRUTH_ACCEPTANCE_PASS
EXACT_ORIGIN_MAIN_SHA = 14a25727c77b5ede3a1731ec2487e08fa2be4eab
EXACT_CONTEXT_BASE_SHA = f9b5ee8d92aa716aaffbb3389094f4ec52082cc4
EXACT_IMPLEMENTATION_BASE_SHA = 5f8066187acc323d23ac4d73da7115100a58aa48
EXACT_IMPLEMENTATION_HEAD_SHA = 9edfae3a0fe7222aa109d7523ed1071e32b90d6c
EXACT_SOURCE_TREE_SHA = a03b6c0cef04e15561a61ac8638ca6a3add594e5
PR_NUMBER_OR_NONE = 504
PR_STATE = MERGED
PR_MERGE_SHA = 14a25727c77b5ede3a1731ec2487e08fa2be4eab
CI_RUN_ID = 31319648134
PROMOTION_RUN_ID = 31320139830
CI_TERMINAL_STATUS = PASS
RELEASE_REQUIRED = PASS_EXACT_HEAD
CHANGED_FILES = 17_LISTED_BELOW
TEST_EVIDENCE = PASS_LISTED_BELOW
RUNTIME_OR_READ_EVIDENCE = PASS_LISTED_BELOW
FINAL_DEPLOYED_SOURCE_SHA = 9edfae3a0fe7222aa109d7523ed1071e32b90d6c
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
NEXT_GATE = DASHBOARD_OWNER_CANONICAL_TRUTH_ACCEPTANCE_PASS_STOP
```

## Result

PR #504 closed D14-01 through D14-08 against the existing unified Dashboard
read model. It canonicalizes persisted performance identity before public
projection, deduplicates fixture evidence, fails closed on ambiguous
aggregate-only overlap, separates tournament evidence, and preserves technical
source aliases/checkpoint identities.

Collection health now requires persisted current evidence; absent evidence is
explicitly unassessed and proven incidents remain source-bound. Baseline-prior
model evidence is public `PRIOR_ONLY`, homogeneous Attention is collapsible,
the shared football-day boundary is projected, and record-only reasons remain
distinct from the undefined market-direction benchmark.

## Changed files

```text
DASHBOARD_DATA_CONTRACT.md
apps/web/e2e/decision-contract.spec.ts
apps/web/src/components/IntelligenceConsole.tsx
apps/web/src/intelligence.css
apps/web/src/lib/labels.ts
apps/web/src/types/intelligenceWorkspace.ts
docs/operations/architecture_convergence/W2_ARCHITECTURE_CONVERGENCE_MASTER_CHECKLIST.md
examples/dashboard_intelligence_workspace.v1.json
src/w2/api/repository.py
src/w2/api/schemas.py
src/w2/dashboard/day_view.py
src/w2/dashboard/intelligence.py
src/w2/dashboard/workspace.py
tests/contract/test_dashboard_intelligence_workspace_contract.py
tests/unit/test_dashboard_intelligence_workspace.py
tests/unit/test_market_intelligence_projection.py
tests/unit/test_performance_api.py
```

## Contract and test evidence

```text
focused backend/unit/contract = 74 passed
post-failure focused regression = 90 passed
Web E2E = 34 passed
TypeScript typecheck = PASS
Web build = PASS
Ruff = PASS
MyPy = PASS
secret scan = PASS
tracked generated outputs = PASS
W2 all-stage checks = PASS
repository diff/hygiene checks = PASS
PR_FAST_REQUIRED @ exact head = PASS
FULL_CI_RELEASE_REQUIRED @ exact head = PASS
```

The Full CI matrix included static contracts, four unit/contract shards, two
integration shards, migration upgrade/downgrade/upgrade, staging parity,
predeploy E2E, compose packaging, Web typecheck/build/full Playwright, immutable
image builds and image smoke.

## Deployment and runtime evidence

```text
IMAGE_TRANSPORT = LOCAL_OCI_RELAY_PRIMARY
PYTHON_IMAGE_DIGEST = sha256:01de96ce43c9b1e85593a2ad9946a4083d1717e3a560c530f5cc35a26899ef37
WEB_IMAGE_DIGEST = sha256:57f2a2c3d9b9fc05996292d7e76822c4649faed2d3cb54d9a5a9644f6ef1536a
PREHEAT_SECONDS = 219
WARM_SWITCH_SECONDS = 46
HEALTH = PASS
READY = PASS
RELEASE_SYNC = PASS
ROLLBACK = false
FINAL_RESULT = PASS
```

The final public Web and API report exact source
`9edfae3a0fe7222aa109d7523ed1071e32b90d6c` from main
`14a25727c77b5ede3a1731ec2487e08fa2be4eab`.

## Final deployed real-data acceptance

The deployed unified endpoint returned six real matches, five canonical
national-league rows and one separate World Cup tournament row. Canonical IDs
were unique. Public competition copy was Chinese with no raw slug or mixed
English primary label.

```text
schema = w2.dashboard-intelligence-workspace.v1
public_authority = NEW_INTELLIGENCE_WORKSPACE_ONLY
canonical_league_ids = allsvenskan,argentina_primera,brasileirao_serie_a,chinese_super_league,eliteserien
duplicate_canonical_league_ids = NONE
tournament_ids = world_cup_2026
collection_assessment_states = ASSESSED_INCIDENT,STALE,UNASSESSED
collection_green_without_current_evidence = false
baseline_prior_ready_violations = 0
only_record_reasons = PROBABILITY_QUALITY_NOT_READY,SAMPLE_INSUFFICIENT
market_direction_benchmark = NOT_DEFINED
football_day_timezone = Asia/Shanghai
football_day_cutoff_hour = 12
football_day_start_utc = 2026-08-09T04:00:00Z
football_day_end_utc = 2026-08-10T04:00:00Z
provider_calls = 0
db_writes = 0
would_write_checkpoint = false
no_call_on_read = true
```

In-app browser acceptance at 1280x720 over the real deployed page passed:

```text
client_width = 1280
scroll_width = 1280
horizontal_overflow = false
canonical_chinese_competition_names = PASS
raw_slug_primary_copy = false
mixed_english_primary_copy = false
tournament_separate_section = PASS
football_day_boundary_visible = PASS
only_record_probability_quality_visible = true
only_record_sample_insufficient_visible = true
market_direction_benchmark_not_defined_visible = true
read_contract_zero_call_zero_write_visible = true
```

Deterministic CI additionally passed 1280x720, 1366x768, 1512x982 and
1920x1080 viewport geometry and no-overlap coverage, plus alias dedupe,
ambiguous-overlap fail-closed, collection unassessed/current/incident,
baseline-prior and homogeneous Attention expand behavior.

## Finding closure

```text
D14_01 = CLOSED_PASS
D14_02 = CLOSED_PASS
D14_03 = CLOSED_PASS
D14_04 = CLOSED_PASS
D14_05 = CLOSED_PASS
D14_06 = CLOSED_PASS
D14_07 = CLOSED_PASS
D14_08 = CLOSED_PASS
```

## Frozen controls and stop

No Provider call, DB business write, migration addition/change, Scheduler/cadence change,
whitelist change, model/factor/threshold change, Phase0.5 re-execution,
external intelligence activation, Round4 start, P6 execution,
Candidate/Formal/Lock/Production enablement or real-money authority occurred.

The task stops at `DASHBOARD_OWNER_CANONICAL_TRUTH_ACCEPTANCE_PASS`. There is
no authorized next code phase.
