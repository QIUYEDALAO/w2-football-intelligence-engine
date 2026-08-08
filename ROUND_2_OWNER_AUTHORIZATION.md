# W2 MI Round 2 — Owner Authorization

Current owner authority for Round 2.

```text
OWNER_AUTHORIZATION_ID = W2_MI_R2_TERMINAL_EARLY_CLOSURE_20260808
OWNER_DECISION = APPROVED_CLOSE_WITH_CURRENT_TERMINAL_EVIDENCE
PRODUCT = W2 Football Intelligence
TASK = W2_MI_R2_FIRST_DIVISION_PROVIDER_CAPABILITY_AUDIT
ROUND_1 = PASS
ROUND_2 = AUTHORIZED_R2_C_NOW
ROUND_3 = NOT_STARTED
WAIT_14_DAYS = false
```

Newest amendment and highest-priority Round 2 authority:

```text
ROUND_2_TERMINAL_CLOSURE_AUTHORIZATION.md
```

It supersedes the earlier requirement that R2-B must remain open for 14 elapsed calendar days.

## Evidence already established

```text
AUDIT_UNION = 17
R2_A = COMPLETE
AUDIT_TOOLING_PR = 494
AUDIT_TOOLING_MERGE_SHA = b04dcc7e521dce413740bcf754b1a45755a3e83e
DAY0_PROVIDER_CALLS = 17
DAY0_PLAN_RESTRICTED_ROWS = 17
DAY0_FIXTURES_CALLS = 0
DAY0_ODDS_CALLS = 0
DAY0_DEEPER_PROBES = 0
ACTIVE_WHITELIST = 13_UNCHANGED
```

The Provider blocker is a plan/access restriction. Waiting does not change that capability fact without a Provider-plan/access change, which is not authorized.

The first persisted-evidence snapshot is also sufficient to classify current temporal evidence as insufficient/degraded rather than waiting for time passage.

## Immediate authorization

Codex is authorized to execute R2-C immediately.

```text
ALLOW_R2_C_NOW = true
REQUIRE_14_DAY_ELAPSED_TIME = false
ALLOW_FINAL_READ_ONLY_FREEZE_SNAPSHOT = true
DEFAULT_NEW_PROVIDER_CALLS = 0
ALLOW_WAIT_FOR_NEXT_DAILY_SNAPSHOT = false
STOP_ROUND2_HEARTBEAT_AFTER_FINAL_RECEIPT = true
```

No new owner authorization is required to close Round 2 under this amendment.

## Final matrix

Produce exactly 17 rows. Preserve real blockers and missing evidence.

Every row:

```text
promotion_authorized = false
```

Missing temporal evidence must be:

```text
TEMPORAL_EVIDENCE_INSUFFICIENT
```

not a fabricated distribution and not a reason to wait.

## Permanent boundaries

```text
ACTIVE_WHITELIST = 13_UNCHANGED
NET_NEW_RUNTIME_PROMOTIONS = 0
PROVIDER_POLICY_CHANGE = false
PROVIDER_ALLOWLIST_CHANGE = false
SCHEDULER_POLICY_CHANGE = false
NEW_PERSISTENT_COLLECTION = false
MODEL_MARKET_DIVERGENCE_AS_OPPORTUNITY = FORBIDDEN
BETTING_EDGE_CLAIM = FORBIDDEN
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
ROUND_3 = NOT_STARTED
```

Round 2 may close as:

```text
ROUND_2 = PASS_WITH_TERMINAL_PROVIDER_PLAN_RESTRICTION
NEXT = AWAIT_OWNER_POST_R2_CAPABILITY_DECISION
```

Only if all revised acceptance criteria in `ROUND_2_ACCEPTANCE_CRITERIA.md` pass.