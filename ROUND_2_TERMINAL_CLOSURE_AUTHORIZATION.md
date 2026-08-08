# W2 MI Round 2 — Terminal Early Closure Authorization

This file is the newest owner authority for Round 2 and **supersedes any older wording that makes 14 elapsed calendar days a mandatory completion gate**.

```text
OWNER_AUTHORIZATION_ID = W2_MI_R2_TERMINAL_EARLY_CLOSURE_20260808
OWNER_DECISION = APPROVED_CLOSE_WITH_CURRENT_TERMINAL_EVIDENCE
ROUND_1 = PASS
ROUND_2 = AUTHORIZED_R2_C_NOW
ROUND_3 = NOT_STARTED
WAIT_14_DAYS = false
```

## Why the time gate is removed

Day-0 produced the same terminal Provider blocker for every audit row:

```text
AUDIT_UNION_COUNT = 17
DAY0_ACTUAL_PROVIDER_CALLS = 17
LEAGUES_ENDPOINT_CALLS = 17
PLAN_RESTRICTED_ROWS = 17
FIXTURES_CALLS = 0
ODDS_CALLS = 0
DEEPER_PROBE_CALLS = 0
```

The blocker is plan/access restriction, not a time-varying sampling condition. Waiting alone cannot make the current account expose fixtures, odds, lineups, injuries or statistics for these rows without a change to Provider plan/access, which is outside Round 2 authorization.

The first R2-B read-only snapshot also established that current persisted temporal evidence is insufficient/degraded:

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

Therefore additional elapsed time is not required to classify the current evidence truthfully.

## Binding replacement rule

```text
OLD_RULE: R2_B_MUST_LAST_14_CALENDAR_DAYS
NEW_RULE: R2_B_MAY_CLOSE_NOW_WHEN_TERMINAL_EXTERNAL_BLOCKER_IS_COMPLETE_AND_WAITING_CANNOT_ADD_AUTHORIZED_CAPABILITY_EVIDENCE
```

For this Round 2 instance the terminal condition is already satisfied.

Codex must **not** wait until 2026-08-22 merely to satisfy time passage.

## Immediate action

```text
ACTIVE_NEXT_ACTION = W2_MI_R2_C_FINAL_CAPABILITY_DECISION_NOW
```

Codex must:

1. re-fetch latest `origin/main` and `origin/context/current`;
2. verify PR #494 merge and Day-0 evidence identities;
3. take at most one final read-only persisted-evidence snapshot if needed to freeze current evidence;
4. make zero new Provider calls unless required solely to verify an already-recorded audit ledger inconsistency; default Provider calls = 0;
5. do not wait for another daily snapshot;
6. stop/disable the `w2-mi-round-2` heartbeat after final receipt if Codex controls it;
7. build the final 17-row capability matrix now;
8. classify every unsupported temporal field as `TEMPORAL_EVIDENCE_INSUFFICIENT` rather than waiting or fabricating data;
9. preserve `PLAN_RESTRICTED` for all 17 Provider capability rows unless newer real evidence proves otherwise;
10. set `promotion_authorized = false` for every row;
11. produce `ROUND_2_FINAL_RECEIPT.md`;
12. update `CURRENT_STATE.yaml`, `NEXT_ACTION.md`, task/agent context to `ROUND_2 = PASS` only if all revised acceptance criteria pass;
13. stop before Round 3 and await owner decision.

## Revised completion semantics

Round 2 PASS means the audit was completed truthfully, not that Provider capabilities were good.

Expected current evidence outcome:

```text
PROVIDER_CAPABILITY_AUDIT = 17_PLAN_RESTRICTED
TEMPORAL_EVIDENCE = INSUFFICIENT_OR_DEGRADED_AS_OBSERVED
ACTIVE_WHITELIST = 13_UNCHANGED
NET_NEW_RUNTIME_PROMOTIONS = 0
PROVIDER_POLICY_DIFF = EMPTY
PROVIDER_ALLOWLIST_DIFF = EMPTY
SCHEDULER_POLICY_DIFF = EMPTY
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
ROUND_3 = NOT_STARTED
```

Allowed final Round 2 state:

```text
ROUND_2 = PASS_WITH_TERMINAL_PROVIDER_PLAN_RESTRICTION
NEXT = AWAIT_OWNER_POST_R2_CAPABILITY_DECISION
```

## No lowering of evidence standards

This amendment does not authorize:

```text
fake temporal samples
invented distributions
provider-plan changes
new persistent collection
new scheduler jobs
active whitelist changes
new league enablement
threshold freezing
Round 3
betting edge/opportunity semantics
```

If evidence is absent, say `TEMPORAL_EVIDENCE_INSUFFICIENT`.

This file takes precedence over any older Round 2 sentence that says `do not finish R2-B before the exact end timestamp` or otherwise treats 14 elapsed days as mandatory.