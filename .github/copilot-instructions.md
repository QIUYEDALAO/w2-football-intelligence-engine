# W2 Copilot / Codex Current Instructions

Before acting, read from `origin/context/current`:

1. `CURRENT_CONTEXT.md`
2. `CURRENT_STATE.yaml`
3. `CURRENT_PRODUCT_DESIGN.md`
4. `CURRENT_TASK_CHECKLIST.md`
5. `NEXT_ACTION.md`
6. `ROUND_2_OWNER_AUTHORIZATION.md`
7. `ROUND_2_CODEX_EXECUTION.md`
8. `ROUND_2_ACCEPTANCE_CRITERIA.md`
9. `ROUND_2_DAY0_RECEIPT.md`
10. `ROUND_1_FINAL_RECEIPT.md`
11. `AI_PROJECT_CONTEXT.md`
12. `AI_QUANT_PROJECT_CONTEXT.md`
13. `AGENTS.md`
14. `QUANT_AGENTS.md`

Use latest trusted `origin/main` as code baseline and `origin/context/current` as current task authority.

```text
PRODUCT = W2 Football Intelligence
PROGRAM = W2_FOOTBALL_MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
ROUND_1 = PASS
ROUND_2 = AUTHORIZED_IN_PROGRESS
ACTIVE_NEXT_ACTION = W2_MI_R2_B_FOURTEEN_DAY_READ_ONLY_OBSERVATION
ROUND_3 = NOT_STARTED
```

## Current authorized work

Round 2 audits a 17-competition union without runtime league expansion.

```text
ACTIVE_WHITELIST_COUNT = 13
NET_NEW_AUDIT_ONLY_COUNT = 4
AUDIT_UNION_COUNT = 17
```

Net-new audit-only IDs:

```text
belgian_pro_league
turkish_super_lig
greek_super_league
scottish_premiership
```

They must remain outside runtime CompetitionRegistry whitelist membership, Scheduler, future-refresh, DayView and public product selection.

## R2-A result

R2-A is complete in `ROUND_2_DAY0_RECEIPT.md`. The merged audit tooling passed
its 17-row zero-call dry-run. Day-0 made 17 `/leagues` calls; all rows stopped at
`PLAN_RESTRICTED`, so no deeper calls were eligible.

## Controlled Provider audit authorization

After the R2-A tooling gates pass, controlled Provider calls are explicitly authorized only through the Round 2 audit path.

```text
ALLOW_CONTROLLED_PROVIDER_AUDIT_CALLS = true
DAY0_EVIDENCE_ONLY_CALLS_PER_COMPETITION = 4
DAY0_THEORETICAL_MAX = 68
ROUND2_DAILY_AUDIT_HARD_CAP = 80
ROUND2_CUMULATIVE_AUDIT_HARD_CAP = 200
ROUND2_MIN_PROVIDER_DAILY_REMAINING = 20
REQUEST_INTERVAL_SECONDS_MIN = 10
AUTOMATIC_RETRY = false
STOP_ON_FIRST_QUOTA_WARNING = true
```

The four net-new Provider league IDs must come from exact Provider evidence. Do not guess them.

If quota/plan/identity/schema/hard-cap stops the batch, preserve evidence and resume within the authorized limits. Do not increase limits or modify production policy to finish.

## R2-B

The active 14-calendar-day observation window is:

```text
START = 2026-08-08T01:53:55.509495+00:00
END = 2026-08-22T01:53:55.509495+00:00
```

Do not repeat Day-0 calls during R2-B.

Use existing W2 persisted captures/read models and already-authorized production collection for temporal evidence.

```text
NEW_PERSISTENT_COLLECTION_FOR_NET_NEW = false
```

If temporal evidence is absent, record `TEMPORAL_EVIDENCE_INSUFFICIENT`.

Round 2 may compute descriptive freshness/overround/movement/bookmaker distributions where real samples exist, but must not freeze Round 3 thresholds.

## R2-C

At observation end, produce exactly 17 final capability rows with truthful ready/partial/blocked/insufficient outcomes.

No automatic promotion, enablement, Scheduler addition or DayView addition is authorized.

```text
promotion_authorized = false
```

for every row.

## Fail-closed continuation

```text
FAIL_CLOSED = DO_NOT_ADVANCE_PAST_FAILED_GATE
FAIL_CLOSED != ABANDON_ROUND_2
```

Bounded audit-tooling remediation and audit-batch resume inside the authorized scope/budgets do not require new owner authorization.

New owner authorization is required only for scope expansion, budget increases, runtime whitelist changes, production Provider/Scheduler changes, persistent collection expansion, Round 3 or recommendation-gate changes.

## Permanent guards

```text
MODEL_MARKET_DIVERGENCE != MARKET_OPPORTUNITY
HIGH_OVERROUND != HIGH_VALUE
HIGH_OVERROUND != HIGH_INFORMATION
RecommendationDecisionV4 = DIAGNOSTIC_INPUT_NOT_PRODUCT_AUTHORITY
BETTING_EDGE_CLAIM = FORBIDDEN
ACTIVE_WHITELIST = 13_UNCHANGED
PRODUCTION_PROVIDER_POLICY_CHANGE = false
PRODUCTION_PROVIDER_ALLOWLIST_CHANGE = false
PRODUCTION_SCHEDULER_POLICY_CHANGE = false
ROUND_3 = NOT_STARTED
H_RESULT_ACCESS = PERMANENTLY_CLOSED
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
REAL_MONEY = NOT_AUTHORIZED
```
