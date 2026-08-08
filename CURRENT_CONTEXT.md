# W2 Current Context

This is the mutable current authority for W2 on `context/current`.

## Read order

```text
1. ROUND_2_TERMINAL_CLOSURE_AUTHORIZATION.md
2. CURRENT_STATE.yaml
3. NEXT_ACTION.md
4. ROUND_2_OWNER_AUTHORIZATION.md
5. ROUND_2_CODEX_EXECUTION.md
6. ROUND_2_ACCEPTANCE_CRITERIA.md
7. ROUND_2_DAY0_RECEIPT.md
8. ROUND_2_OBSERVATION_LOG.md
9. ROUND_2_ACCEPTANCE_EVIDENCE_INDEX.md
10. ROUND_1_FINAL_RECEIPT.md
11. CURRENT_TASK_CHECKLIST.md
12. AGENTS.md
13. QUANT_AGENTS.md
14. .github/copilot-instructions.md
```

## Current decision

```text
PRODUCT = W2 Football Intelligence
ROUND_1 = PASS
ROUND_2 = AUTHORIZED_R2_C_NOW
ACTIVE_NEXT_ACTION = W2_MI_R2_C_FINAL_CAPABILITY_DECISION_NOW
WAIT_14_DAYS = false
ROUND_3 = NOT_STARTED
```

The owner has explicitly removed the former mandatory 14-day elapsed-time gate.

Newest authority:

```text
ROUND_2_TERMINAL_CLOSURE_AUTHORIZATION.md
```

Any older wording that says R2-B must remain open until `2026-08-22T01:53:55.509495Z` is superseded.

## Why Round 2 can close now

R2-A / Day-0 already established:

```text
AUDIT_UNION = 17
AUDIT_TOOLING_PR = 494
AUDIT_TOOLING_MERGE_SHA = b04dcc7e521dce413740bcf754b1a45755a3e83e
DAY0_PROVIDER_CALLS = 17
DAY0_PLAN_RESTRICTED_ROWS = 17
FIXTURES_CALLS = 0
ODDS_CALLS = 0
DEEPER_PROBE_CALLS = 0
ACTIVE_WHITELIST = 13_UNCHANGED
```

The blocker is Provider plan/access, not elapsed time.

R2-B snapshot 1 also showed current persisted evidence is insufficient/degraded:

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

Therefore missing temporal evidence must be classified now as `TEMPORAL_EVIDENCE_INSUFFICIENT`; it must not trigger waiting or invented samples.

## Immediate R2-C

Codex must now:

```text
VERIFY EVIDENCE
-> OPTIONAL ONE FINAL READ-ONLY FREEZE SNAPSHOT
-> FINAL 17-ROW CAPABILITY MATRIX
-> ROUND_2_FINAL_RECEIPT.md
-> STOP HEARTBEAT IF CONTROLLED
-> UPDATE CURRENT CONTEXT TO ROUND_2 PASS
-> STOP BEFORE ROUND_3
```

Default new Provider calls for R2-C = 0.

Every final row:

```text
promotion_authorized = false
```

## Audit universe

```text
EXISTING_RUNTIME_WHITELIST = 13
NET_NEW_AUDIT_ONLY = 4
AUDIT_UNION = 17
```

The four net-new candidates remain `AUDIT_CANDIDATE_ONLY` and may not enter CompetitionRegistry runtime whitelist, Scheduler, future-refresh, DayView or public cards.

## Permanent product guards

```text
MODEL_MARKET_DIVERGENCE != MARKET_OPPORTUNITY
RecommendationDecisionV4 = DIAGNOSTIC_INPUT_NOT_PRODUCT_AUTHORITY
BETTING_EDGE_CLAIM = FORBIDDEN
HIGH_OVERROUND != HIGH_VALUE
HIGH_OVERROUND != HIGH_INFORMATION
ACTIVE_WHITELIST = 13_UNCHANGED
PROVIDER_POLICY_CHANGE = false
PROVIDER_ALLOWLIST_CHANGE = false
SCHEDULER_POLICY_CHANGE = false
NEW_PERSISTENT_COLLECTION_FOR_NET_NEW = false
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
ROUND_3 = NOT_STARTED
H_RESULT_ACCESS = PERMANENTLY_CLOSED
```

Expected final Round 2 state if revised acceptance passes:

```text
ROUND_2 = PASS_WITH_TERMINAL_PROVIDER_PLAN_RESTRICTION
NEXT = AWAIT_OWNER_POST_R2_CAPABILITY_DECISION
```