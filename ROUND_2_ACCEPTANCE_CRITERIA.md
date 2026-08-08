# W2 MI Round 2 — Binding Acceptance Criteria

Current acceptance standard for `W2_MI_R2_FIRST_DIVISION_PROVIDER_CAPABILITY_AUDIT`.

Newest owner override:

```text
ROUND_2_TERMINAL_CLOSURE_AUTHORIZATION.md
```

This file supersedes the former mandatory 14-calendar-day completion gate.

```text
REQUIRE_14_ELAPSED_DAYS = false
ALLOW_TERMINAL_EVIDENCE_EARLY_CLOSURE = true
```

Round 2 PASS means the audit is complete, truthful, safe and non-promotional. It does not require Provider capability to be good.

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

Every Provider call must have exactly one sanitized ledger record. No secret material may appear in Git/context/artifacts.

## D. Terminal-blocker early closure — hard gate

The old rule requiring observation through 2026-08-22 is removed.

Early closure is valid when all of the following are true:

```text
TERMINAL_PROVIDER_BLOCKER_ROWS = 17
TERMINAL_PROVIDER_BLOCKER = PLAN_RESTRICTED
WAITING_ALONE_CAN_CHANGE_PROVIDER_PLAN_ACCESS = false
NEW_PROVIDER_PLAN_OR_POLICY_CHANGE_AUTHORIZED = false
NEW_PERSISTENT_COLLECTION_AUTHORIZED = false
```

For this Round 2 instance these conditions are already satisfied by Day-0 evidence.

Do not mark R2-C blocked merely because 14 days have not elapsed.

## E. Persisted temporal evidence truth — hard gate

Use the already collected R2-B snapshot and optionally one final read-only freeze snapshot.

Current evidence baseline includes:

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

Acceptance rule:

```text
NO_REAL_TEMPORAL_SAMPLE => TEMPORAL_EVIDENCE_INSUFFICIENT
```

Fail if missing evidence is converted into fabricated freshness, overround, movement, bookmaker or readiness distributions.

There is no minimum elapsed-day requirement.

## F. Final 17-row capability matrix — hard gate

Exactly 17 unique rows are required.

Each row must include:

```text
canonical audit ID
display name
current runtime membership
audit-only candidate flag
provider identity status
provider plan status
provider league ID if verified
future fixture status
result fixture status
AH status
OU status
bookmaker depth status
lineup status
injury status
statistics status
schema status
temporal evidence status
Provider call cost
blockers
warnings
current capability state
recommended future capability state
promotion_authorized
```

For unsupported Provider fields after `PLAN_RESTRICTED`, use truthful NOT_AUDITED/PLAN_RESTRICTED semantics.

For absent temporal evidence use `TEMPORAL_EVIDENCE_INSUFFICIENT`.

Every row must satisfy:

```text
promotion_authorized = false
```

## G. Allowed final audit outcomes

Allowed outcomes include:

```text
PLAN_RESTRICTED
TEMPORAL_EVIDENCE_INSUFFICIENT
DEGRADED
CAPABILITY_PARTIAL
CAPABILITY_CONFIRMED
IDENTITY_REVIEW_REQUIRED
SCHEMA_UNSAFE
PROVIDER_QUOTA_BLOCKED
```

Do not invent CAPABILITY_CONFIRMED where the evidence does not support it.

## H. Runtime and safety invariants — hard gate

Required final evidence:

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
```

## I. Product semantic invariants — hard gate

Required:

```text
PRODUCT = W2 Football Intelligence
PRODUCT_SEMANTICS = INTELLIGENCE_FIRST
MODEL_MARKET_DIVERGENCE != MARKET_OPPORTUNITY
RecommendationDecisionV4 = DIAGNOSTIC_INPUT_NOT_PRODUCT_AUTHORITY
BETTING_EDGE_CLAIM = FORBIDDEN
HIGH_OVERROUND_AS_VALUE = FORBIDDEN
HIGH_OVERROUND_AS_INFORMATION = FORBIDDEN
OPPORTUNITY_SCORE = FORBIDDEN
```

## J. Heartbeat/time-gate cleanup

The daily `w2-mi-round-2` heartbeat must no longer be required for acceptance.

If Codex controls it, final closure must stop/disable it.

Required final status:

```text
WAITING_FOR_NEXT_DAILY_SNAPSHOT = false
WAITING_FOR_2026_08_22 = false
```

## K. Final receipt — hard gate

Create `ROUND_2_FINAL_RECEIPT.md` with at least:

```text
ROUND2_INITIAL_MAIN_SHA
ROUND2_EXECUTION_BASE_SHA
AUDIT_TOOLING_PR_NUMBER
AUDIT_TOOLING_FINAL_HEAD_SHA
AUDIT_TOOLING_MERGE_SHA
PR_FAST/FULL_RC/MAIN_PROMOTION evidence
ACTIVE_WHITELIST_BEFORE
ACTIVE_WHITELIST_AFTER
ACTIVE_WHITELIST_IDENTITY_DIFF
AUDIT_UNION_COUNT
DAY0_ACTUAL_PROVIDER_CALLS
ROUND2_CUMULATIVE_PROVIDER_CALLS
PLAN_RESTRICTED_ROWS
FINAL_17_ROW_CAPABILITY_MATRIX
TEMPORAL_EVIDENCE_SUMMARY
PROVIDER_POLICY_DIFF
PROVIDER_ALLOWLIST_DIFF
SCHEDULER_POLICY_DIFF
NEW_PERSISTENT_COLLECTION_JOBS
NEW_ENABLED_LEAGUES
NEW_SCHEDULED_LEAGUES
NEW_DAYVIEW_LEAGUES
HEARTBEAT_FINAL_STATUS
CANDIDATE
FORMAL
LOCK
PRODUCTION
ROUND_3
```

## L. Completion

Expected final state if all gates pass:

```text
ROUND_2 = PASS_WITH_TERMINAL_PROVIDER_PLAN_RESTRICTION
ACTIVE_WHITELIST = 13_UNCHANGED
AUDIT_UNION = 17_COMPLETE_WITH_TRUTHFUL_OUTCOMES
NET_NEW_AUDIT_CANDIDATES = 4_NOT_ENABLED
WAIT_14_DAYS = false
ROUND_3 = NOT_STARTED
NEXT = AWAIT_OWNER_POST_R2_CAPABILITY_DECISION
```

After PASS, stop. Do not start Round 3 or any league enablement automatically.