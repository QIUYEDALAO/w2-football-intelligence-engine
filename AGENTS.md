# W2 Repository Agent Instructions

Current task authority is `origin/context/current`.

Read before work:

1. `CURRENT_CONTEXT.md`
2. `CURRENT_STATE.yaml`
3. `CURRENT_PRODUCT_DESIGN.md`
4. `CURRENT_TASK_CHECKLIST.md`
5. `NEXT_ACTION.md`
6. `ROUND_2_OWNER_AUTHORIZATION.md`
7. `ROUND_2_CODEX_EXECUTION.md`
8. `ROUND_2_ACCEPTANCE_CRITERIA.md`
9. `ROUND_2_DAY0_RECEIPT.md`
10. `ROUND_2_OBSERVATION_LOG.md`
11. `ROUND_1_FINAL_RECEIPT.md`
12. `AI_PROJECT_CONTEXT.md`
13. `AI_QUANT_PROJECT_CONTEXT.md`
14. `QUANT_AGENTS.md`
15. `.github/copilot-instructions.md`

Use latest trusted `origin/main` as code baseline and `origin/context/current` as task authority.

```text
PRODUCT = W2 Football Intelligence
ROUND_1 = PASS
ROUND_2 = AUTHORIZED_IN_PROGRESS
ACTIVE_NEXT_ACTION = W2_MI_R2_B_FOURTEEN_DAY_READ_ONLY_OBSERVATION
ROUND_3 = NOT_STARTED
```

## Current Round 2 scope

Round 2 audits 17 competitions:

```text
13 existing active-whitelist competitions
+
4 audit-only candidates
```

Audit-only IDs:

```text
belgian_pro_league
turkish_super_lig
greek_super_league
scottish_premiership
```

They are **not runtime whitelist members** in Round 2.

```text
ACTIVE_WHITELIST = 13_UNCHANGED
AUDIT_CANDIDATE_RUNTIME_REACHABILITY = 0
```

Do not add the four to CompetitionRegistry runtime whitelist, Scheduler, future-refresh, DayView or public cards.

## Current phase

R2-A is complete in `ROUND_2_DAY0_RECEIPT.md`. PR `#494` is merged; its
17-row dry-run made zero Provider calls. Day-0 made 17 `/leagues` calls and all
17 rows stopped truthfully at `PLAN_RESTRICTED`; no deeper calls are eligible.

```text
R2_A = COMPLETE_WITH_TRUTHFUL_PLAN_RESTRICTIONS
R2_B = ACTIVE
ROUND2_OBSERVATION_START_UTC = 2026-08-08T01:53:55.509495+00:00
ROUND2_OBSERVATION_END_UTC = 2026-08-22T01:53:55.509495+00:00
```

## Controlled Provider audit authorization

After R2-A tooling acceptance, controlled real Provider calls are authorized only through the Round 2 audit path.

```text
DAY0_EVIDENCE_ONLY_PLANNED_PER_COMPETITION = 4
DAY0_THEORETICAL_MAX = 68
DAILY_AUDIT_HARD_CAP = 80
CUMULATIVE_AUDIT_HARD_CAP = 200
MIN_PROVIDER_DAILY_REMAINING = 20
REQUEST_INTERVAL_SECONDS_MIN = 10
AUTOMATIC_RETRY = false
STOP_ON_FIRST_QUOTA_WARNING = true
```

Do not use production future-refresh calls to satisfy Round 2 audit requirements.

Every Provider call requires exactly one sanitized ledger record.

HTTP 429, quota warning/exhaustion, plan restriction, schema unsafe, invalid key, payload error, endpoint authorization failure and hard caps remain fail-closed.

## R2-B/R2-C

The Day-0 evidence capture started the 14-calendar-day observation window shown
above. Do not repeat Day-0 calls during R2-B.

Use existing persisted W2 evidence and existing authorized production collection. No new persistent polling schedule for the four audit-only candidates.

If temporal evidence is insufficient, record it as insufficient.

At observation end, produce exactly 17 final capability rows. No automatic enablement/promotion.

## Continuation semantics

```text
FAIL_CLOSED = DO_NOT_ADVANCE_PAST_FAILED_GATE
FAIL_CLOSED != ABANDON_ROUND_2
```

Bounded audit-tooling remediation and audit-batch resume inside the owner-authorized scope/budgets do not require another owner approval.

Do not bypass blockers by raising budgets, enabling retries, widening production allowlists, modifying Scheduler or guessing identity.

## Permanent guards

```text
MODEL_MARKET_DIVERGENCE != MARKET_OPPORTUNITY
HIGH_OVERROUND != HIGH_VALUE
HIGH_OVERROUND != HIGH_INFORMATION
BETTING_EDGE_CLAIM = FORBIDDEN
RecommendationDecisionV4 = DIAGNOSTIC_INPUT_NOT_PRODUCT_AUTHORITY
PRODUCTION_PROVIDER_POLICY_CHANGE = false
PRODUCTION_SCHEDULER_POLICY_CHANGE = false
ROUND_3 = NOT_STARTED
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
H_RESULT_ACCESS = PERMANENTLY_CLOSED
REAL_MONEY = NOT_AUTHORIZED
```
