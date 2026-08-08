# W2 Market Intelligence Agent Instructions

Current authority is `origin/context/current`.

Required current files:

```text
CURRENT_CONTEXT.md
CURRENT_STATE.yaml
CURRENT_PRODUCT_DESIGN.md
CURRENT_TASK_CHECKLIST.md
NEXT_ACTION.md
ROUND_2_OWNER_AUTHORIZATION.md
ROUND_2_CODEX_EXECUTION.md
ROUND_2_ACCEPTANCE_CRITERIA.md
ROUND_1_FINAL_RECEIPT.md
```

```text
PRODUCT = W2 Football Intelligence
ROUND_1 = PASS
ROUND_2 = AUTHORIZED_IN_PROGRESS
ACTIVE_NEXT_ACTION = W2_MI_R2_AUDIT_FOUNDATION_AND_DAY0_BASELINE
ROUND_3 = NOT_STARTED
```

Phase 0.5 remains closed with `NO_EDGE`; do not reopen H.

## Round 2 audit union

```text
ACTIVE_WHITELIST = 13_UNCHANGED
AUDIT_ONLY_NET_NEW = 4
AUDIT_UNION = 17
```

Audit-only candidates:

```text
belgian_pro_league
turkish_super_lig
greek_super_league
scottish_premiership
```

Do not add them to runtime registry/Scheduler/future-refresh/DayView.

## R2-A

Build the audit foundation first, with Provider calls = 0 during development/CI.

Required capabilities:

- separate audit-only descriptor authority;
- deterministic Provider identity resolution;
- no fuzzy/guessed league IDs;
- existing audit modes preserved;
- 17-row zero-call dry-run;
- sanitized cumulative Provider audit ledger;
- multi-day resume without budget reset;
- hard quota reserve and no retry.

After tooling acceptance, controlled Provider audit calls are owner-authorized:

```text
DAY0_THEORETICAL_MAX = 68
DAILY_AUDIT_HARD_CAP = 80
CUMULATIVE_AUDIT_HARD_CAP = 200
MIN_PROVIDER_DAILY_REMAINING = 20
REQUEST_INTERVAL_SECONDS_MIN = 10
AUTOMATIC_RETRY = false
```

Blockers such as quota, plan, identity ambiguity and unsafe schema are valid evidence. Do not bypass them.

## R2-B

The first successful Day-0 baseline starts a 14-day observation window.

Use existing persisted captures/read models and already-authorized production collection. No new persistent polling for audit-only candidates.

Collect descriptive market evidence where real samples exist:

```text
freshness
overround
movement
bookmaker depth/confirmation
missingness
Provider/schema incidents
```

Do not freeze Round 3 thresholds.

## R2-C

Final output is exactly 17 truthful capability rows. A row may be confirmed, partial, blocked, degraded or insufficient-evidence.

Product capability vocabulary:

```text
REGISTERED
COVERAGE_MONITORING
MARKET_INTELLIGENCE_READY
MODEL_DIAGNOSTICS_READY
DEGRADED
```

Net-new current runtime state remains:

```text
AUDIT_CANDIDATE_ONLY
```

No automatic promotion/enablement.

## Hard guards

```text
MODEL_MARKET_DIVERGENCE != MARKET_OPPORTUNITY
HIGH_OVERROUND != HIGH_VALUE
HIGH_OVERROUND != HIGH_INFORMATION
BETTING_EDGE_CLAIM = FORBIDDEN
ACTIVE_WHITELIST = 13_UNCHANGED
PRODUCTION_PROVIDER_POLICY_CHANGE = false
PRODUCTION_SCHEDULER_POLICY_CHANGE = false
ROUND_3 = NOT_STARTED
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
REAL_MONEY = NOT_AUTHORIZED
```

For bounded in-scope failures, fix and continue under the existing Round 2 authorization; do not ask for owner approval again unless scope or a permanent stop line must change.