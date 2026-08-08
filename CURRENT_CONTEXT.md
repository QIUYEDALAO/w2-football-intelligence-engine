# W2 Current Context

This is the mutable current authority for W2. It is maintained directly on `context/current` without a context PR/CI/deployment.

## Read order

1. `CURRENT_STATE.yaml`
2. `CURRENT_PRODUCT_DESIGN.md`
3. `CURRENT_TASK_CHECKLIST.md`
4. `NEXT_ACTION.md`
5. `ROUND_2_OWNER_AUTHORIZATION.md`
6. `ROUND_2_CODEX_EXECUTION.md`
7. `ROUND_2_ACCEPTANCE_CRITERIA.md`
8. `ROUND_2_DAY0_RECEIPT.md`
9. `ROUND_2_OBSERVATION_LOG.md`
10. `ROUND_1_FINAL_RECEIPT.md`
11. `AI_PROJECT_CONTEXT.md`
12. `AI_QUANT_PROJECT_CONTEXT.md`
13. `AGENTS.md`
14. `QUANT_AGENTS.md`
15. `.github/copilot-instructions.md`

## Current decision

```text
PRODUCT = W2 Football Intelligence
PROGRAM = W2_FOOTBALL_MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
ROUND_1 = PASS
ROUND_2 = AUTHORIZED_IN_PROGRESS
ACTIVE_NEXT_ACTION = W2_MI_R2_B_FOURTEEN_DAY_READ_ONLY_OBSERVATION
ROUND_3 = NOT_STARTED
```

Round 1 final delivery evidence is frozen in `ROUND_1_FINAL_RECEIPT.md`.

Round 2 owner authorization is `ROUND_2_OWNER_AUTHORIZATION.md`.

## Round 2 mission

Audit Provider and persisted W2 evidence across a 17-competition universe without turning the audit into runtime league expansion.

```text
EXISTING_ACTIVE_WHITELIST = 13
NET_NEW_AUDIT_ONLY = 4
AUDIT_UNION = 17
```

Existing 13:

```text
chinese_super_league
allsvenskan
eliteserien
premier_league
la_liga
bundesliga
serie_a
ligue_1
brasileirao_serie_a
argentina_primera
mls
eredivisie
primeira_liga
```

Net-new audit-only candidates:

```text
belgian_pro_league
turkish_super_lig
greek_super_league
scottish_premiership
```

The four net-new candidates are not runtime whitelist members.

```text
NET_NEW_RUNTIME_STATE = AUDIT_CANDIDATE_ONLY
ACTIVE_WHITELIST_DURING_R2 = 13
```

Do not add them to CompetitionRegistry runtime whitelist, Scheduler, future-refresh, DayView or public cards in Round 2.

## Round 2 phases

```text
R2_A = AUDIT_FOUNDATION_AND_DAY0_BASELINE
R2_B = FOURTEEN_DAY_READ_ONLY_OBSERVATION
R2_C = FINAL_CAPABILITY_DECISION
```

Current phase:

```text
R2_A = COMPLETE_WITH_TRUTHFUL_PLAN_RESTRICTIONS
R2_B = ACTIVE_UNTIL_2026-08-22T01:53:55.509495+00:00
R2_C = BLOCKED_UNTIL_R2_B_WINDOW_COMPLETE
```

R2-A audit tooling was delivered in PR `#494` and merged as
`b04dcc7e521dce413740bcf754b1a45755a3e83e`. PR/CI Provider calls were zero.
The 17-row dry-run recorded 68 planned calls, zero actual calls and zero business
writes.

The authorized Day-0 audit then made exactly one `/leagues` request for each of
the 17 audit rows. Every request was recorded once and returned a truthful
`PROVIDER_PLAN_RESTRICTED` result. No fixtures, odds or deeper capability calls
were eligible. See `ROUND_2_DAY0_RECEIPT.md`.

R2-B read-only snapshots are recorded in `ROUND_2_OBSERVATION_LOG.md`. The first
snapshot found zero within-window quote rows; pre-window last-known quotes remain
reference-only and cannot satisfy temporal evidence acceptance.

## Provider audit authorization

```text
ALLOW_CONTROLLED_PROVIDER_AUDIT_CALLS = true
ALLOW_PRODUCTION_REFRESH_CALLS_FOR_R2 = false
AUTOMATIC_RETRY = false
ROUND2_AUDIT_DAILY_HARD_CAP = 80
ROUND2_AUDIT_CUMULATIVE_HARD_CAP = 200
ROUND2_MIN_PROVIDER_DAILY_REMAINING = 20
REQUEST_INTERVAL_SECONDS_MIN = 10
```

Existing evidence-only contract is the Day-0 first probe:

```text
EVIDENCE_ONLY_PLANNED_CALLS_PER_COMPETITION = 4
DAY0_TARGET_COUNT = 17
DAY0_THEORETICAL_MAX = 68
```

Quota/plan/identity/schema blockers are valid outcomes. Do not raise limits to force completion.

The four net-new Provider league IDs must be observed from deterministic `/leagues` identity evidence; never guessed.

## Fourteen-day observation

The exact observation window starts when the first successful Day-0 baseline is captured:

```text
ROUND2_OBSERVATION_START_UTC = 2026-08-08T01:53:55.509495+00:00
ROUND2_OBSERVATION_END_UTC = 2026-08-22T01:53:55.509495+00:00
```

Temporal evidence comes from existing persisted W2 captures/read models and already-authorized production collection. Round 2 does not authorize a new persistent polling scheduler for audit-only candidates.

If a league lacks sufficient temporal evidence, record `TEMPORAL_EVIDENCE_INSUFFICIENT` rather than generating more data.

## Capability outputs

Permitted product capability vocabulary remains:

```text
REGISTERED
COVERAGE_MONITORING
MARKET_INTELLIGENCE_READY
MODEL_DIAGNOSTICS_READY
DEGRADED
```

The four net-new candidates remain `AUDIT_CANDIDATE_ONLY` as current runtime state.

No Round 2 result automatically authorizes promotion, enablement or scheduling.

## Permanent product guards

```text
MODEL_MARKET_DIVERGENCE != MARKET_OPPORTUNITY
RecommendationDecisionV4 = DIAGNOSTIC_INPUT_NOT_PRODUCT_AUTHORITY
BETTING_EDGE_CLAIM = FORBIDDEN
HIGH_OVERROUND != HIGH_VALUE
HIGH_OVERROUND != HIGH_INFORMATION
```

Round 2 may produce descriptive overround/movement/freshness distributions for Round 3 planning. It must not freeze Round 3 alert thresholds or create an opportunity score.

## Fail-closed continuation

```text
FAIL_CLOSED = DO_NOT_ADVANCE_PAST_FAILED_GATE
FAIL_CLOSED != ABANDON_ROUND_2
```

Bounded Round 2 audit-tooling remediation and audit-batch resume within the approved budgets do not require another owner authorization.

A new owner authorization is required for active whitelist changes, production Provider/Scheduler changes, persistent collection expansion, Round 3, recommendation gates or budget increases.

## Permanent stop lines

```text
ACTIVE_WHITELIST = 13_UNCHANGED
PRODUCTION_PROVIDER_POLICY_CHANGE = false
PRODUCTION_PROVIDER_ALLOWLIST_CHANGE = false
PRODUCTION_SCHEDULER_POLICY_CHANGE = false
NEW_PERSISTENT_COLLECTION_FOR_NET_NEW = false
ROUND_3 = NOT_STARTED
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
H_RESULT_ACCESS = PERMANENTLY_CLOSED
SIGNAL_LEDGER_FOR_EXECUTION = NOT_AUTHORIZED
PORTFOLIO = NOT_AUTHORIZED
RISK_KELLY = NOT_AUTHORIZED
TWO_LEG_PARLAY = NOT_AUTHORIZED
REAL_MONEY = NOT_AUTHORIZED
```
