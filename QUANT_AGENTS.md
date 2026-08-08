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
ROUND_2_ACCEPTANCE_EVIDENCE_INDEX.md
ROUND_2_DAY0_RECEIPT.md
ROUND_2_OBSERVATION_LOG.md
ROUND_1_FINAL_RECEIPT.md
```

```text
PRODUCT = W2 Football Intelligence
ROUND_1 = PASS
ROUND_2 = AUTHORIZED_IN_PROGRESS
ACTIVE_NEXT_ACTION = W2_MI_R2_B_FOURTEEN_DAY_READ_ONLY_OBSERVATION
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

## R2-A result

R2-A is complete in `ROUND_2_DAY0_RECEIPT.md`. Day-0 produced 17 truthful
`PLAN_RESTRICTED` rows from 17 `/leagues` calls and made no deeper calls.

## R2-B

The active read-only observation window is:

```text
START = 2026-08-08T01:53:55.509495+00:00
END = 2026-08-22T01:53:55.509495+00:00
```

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
