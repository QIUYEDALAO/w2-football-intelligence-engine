# W2 MI Round 2 — Binding Acceptance Criteria

Current acceptance standard for `W2_MI_R2_FIRST_DIVISION_PROVIDER_CAPABILITY_AUDIT`.

Newest owner authorities:

```text
ROUND_2_TERMINAL_CLOSURE_AUTHORIZATION.md
REPOSITORY_HYGIENE_POLICY.md
```

```text
REQUIRE_14_ELAPSED_DAYS = false
ALLOW_TERMINAL_EVIDENCE_EARLY_CLOSURE = true
TASK_PASS_REQUIRES_REPOSITORY_HYGIENE_PASS = true
```

Round 2 PASS means the audit is complete, truthful, safe, non-promotional and leaves no known unnecessary task debris behind.

## A. Source and completed R2-A identity

Required:

```text
ROUND_1 = PASS
AUDIT_TOOLING_PR_NUMBER = 494
AUDIT_TOOLING_MERGE_SHA = b04dcc7e521dce413740bcf754b1a45755a3e83e
DRY_RUN_ROWS = 17
DRY_RUN_PROVIDER_CALLS = 0
ROUND_3 = NOT_STARTED
```

## B. Audit universe and runtime isolation — hard gate

Required:

```text
EXISTING_WHITELIST_COUNT = 13
NET_NEW_AUDIT_ONLY_COUNT = 4
AUDIT_UNION_COUNT = 17
ACTIVE_WHITELIST_BEFORE = 13
ACTIVE_WHITELIST_AFTER = 13
ACTIVE_WHITELIST_IDENTITY_DIFF = EMPTY
NET_NEW_ACTIVE_WHITELIST_ADDITIONS = 0
NET_NEW_SCHEDULER_ADDITIONS = 0
NET_NEW_DAYVIEW_ADDITIONS = 0
AUDIT_CANDIDATE_RUNTIME_REACHABILITY = 0
```

## C. Day-0 evidence integrity — hard gate

Required preserved evidence:

```text
DAY0_ACTUAL_PROVIDER_CALLS = 17
LEAGUES_ENDPOINT_CALLS = 17
FIXTURES_ENDPOINT_CALLS = 0
ODDS_ENDPOINT_CALLS = 0
DEEPER_CAPABILITY_PROBE_CALLS = 0
PLAN_RESTRICTED_ROWS = 17
LEDGER_RECORDS = 17
LEDGER_DUPLICATE_PROVIDER_CALL_INDEXES = 0
AUTOMATIC_RETRY = false
```

Every Provider call must have exactly one sanitized ledger record. No credential material may appear in Git/context/artifacts.

## D. Terminal-blocker early closure — hard gate

The former requirement to wait until 2026-08-22 is removed.

Required:

```text
TERMINAL_PROVIDER_BLOCKER_ROWS = 17
TERMINAL_PROVIDER_BLOCKER = PLAN_RESTRICTED
WAITING_ALONE_CAN_CHANGE_PROVIDER_PLAN_ACCESS = false
NEW_PROVIDER_PLAN_OR_POLICY_CHANGE_AUTHORIZED = false
NEW_PERSISTENT_COLLECTION_AUTHORIZED = false
```

Do not block R2-C because 14 days have not elapsed.

## E. Persisted temporal evidence truth — hard gate

Use the already collected R2-B snapshot and optionally one final read-only freeze snapshot.

Current evidence baseline:

```text
DAYVIEW_CARDS = 64
DATA_INCOMPLETE = 64
CURRENT_ODDS_CARDS = 0
WITHIN_WINDOW_QUOTE_ROWS = 0
READINESS_ROWS = 5
READINESS_404_ROWS = 12
SAMPLED_ODDS_TIMELINES = 4
TIMELINE_ITEMS = 0
```

Rule:

```text
NO_REAL_TEMPORAL_SAMPLE => TEMPORAL_EVIDENCE_INSUFFICIENT
```

No fabricated freshness, overround, movement, bookmaker or readiness distributions.

## F. Final 17-row capability matrix — hard gate

Exactly 17 unique rows are required. Each row must truthfully include Provider identity/plan, fixtures/results, AH/OU, bookmaker, lineup/injury/statistics, schema, temporal evidence, call cost, blockers/warnings, current/recommended capability state and:

```text
promotion_authorized = false
```

Unsupported Provider fields after `PLAN_RESTRICTED` must remain NOT_AUDITED/PLAN_RESTRICTED. Missing temporal evidence must remain `TEMPORAL_EVIDENCE_INSUFFICIENT`.

## G. Runtime, safety and semantic invariants — hard gate

Required:

```text
ACTIVE_WHITELIST = 13_UNCHANGED
PROVIDER_POLICY_DIFF = EMPTY
PROVIDER_ALLOWLIST_DIFF = EMPTY
SCHEDULER_POLICY_DIFF = EMPTY
NEW_PERSISTENT_COLLECTION_JOBS = 0
NEW_ENABLED_LEAGUES = 0
NEW_SCHEDULED_LEAGUES = 0
NEW_DAYVIEW_LEAGUES = 0
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
H_RESULT_ACCESS = PERMANENTLY_CLOSED
ROUND_3 = NOT_STARTED
PRODUCT = W2 Football Intelligence
PRODUCT_SEMANTICS = INTELLIGENCE_FIRST
MODEL_MARKET_DIVERGENCE != MARKET_OPPORTUNITY
RecommendationDecisionV4 = DIAGNOSTIC_INPUT_NOT_PRODUCT_AUTHORITY
BETTING_EDGE_CLAIM = FORBIDDEN
HIGH_OVERROUND_AS_VALUE = FORBIDDEN
HIGH_OVERROUND_AS_INFORMATION = FORBIDDEN
OPPORTUNITY_SCORE = FORBIDDEN
```

## H. Repository hygiene — mandatory final hard gate

Before Round 2 may be declared PASS, execute `REPOSITORY_HYGIENE_POLICY.md`.

Required procedure:

1. enumerate files/assets added, changed, superseded or exposed as obsolete by Round 2;
2. classify each `KEEP`, `DELETE`, `RETAIN_FOR_EVIDENCE`, or `REVIEW_REQUIRED`;
3. prove deletion safety with repository references/imports/entrypoints/workflows/config/test/CI searches;
4. delete all provably dead task assets;
5. remove dead imports/exports/flags/tests/docs caused by those deletions;
6. rerun focused and repository-required checks after cleanup.

Specifically inspect:

```text
Round 2 temporary audit scaffolding
one-off debug helpers
tracked dry-run scratch outputs
superseded audit fixtures
obsolete observation-heartbeat glue
stale 14-day-only control artifacts
unused duplicate task/context entrypoints
```

Do not delete reusable league-audit tooling, migrations/history, final receipts, sanitized audit evidence required for traceability, CI/release scripts still used, or protected baselines.

Required final receipt fields:

```text
REPOSITORY_HYGIENE = PASS
DEAD_ASSETS_FOUND = <count>
DEAD_ASSETS_DELETED = <count>
OBSOLETE_CODE_LINES_REMOVED = <count when measurable>
RETAINED_FOR_EVIDENCE = <list/count>
UNRESOLVED_HYGIENE_ITEMS = 0
```

A known dead asset may not be silently left behind. If deletion safety is unresolved, record the exact dependency and do not claim hygiene PASS without justification.

## I. Heartbeat/time-gate cleanup

The daily `w2-mi-round-2` heartbeat is not required for acceptance. If Codex controls it, stop/disable it during closure.

```text
WAITING_FOR_NEXT_DAILY_SNAPSHOT = false
WAITING_FOR_2026_08_22 = false
```

## J. Final receipt — hard gate

Create `ROUND_2_FINAL_RECEIPT.md` containing source/PR/CI identities, Day-0 evidence, final 17-row matrix, temporal-evidence summary, runtime/safety diffs, heartbeat final state, and repository-hygiene evidence.

## K. Completion

Expected final state if all gates pass:

```text
ROUND_2 = PASS_WITH_TERMINAL_PROVIDER_PLAN_RESTRICTION
ACTIVE_WHITELIST = 13_UNCHANGED
AUDIT_UNION = 17_COMPLETE_WITH_TRUTHFUL_OUTCOMES
NET_NEW_AUDIT_CANDIDATES = 4_NOT_ENABLED
WAIT_14_DAYS = false
REPOSITORY_HYGIENE = PASS
ROUND_3 = NOT_STARTED
NEXT = AWAIT_OWNER_POST_R2_CAPABILITY_DECISION
```

After PASS, stop. Do not start Round 3 or any league enablement automatically.
