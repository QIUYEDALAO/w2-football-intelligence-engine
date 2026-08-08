# W2 AI Project Context

Current authority is `origin/context/current`.

```text
PRODUCT = W2 Football Intelligence
PROGRAM = W2_FOOTBALL_MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
ROUND_1 = PASS
ROUND_2 = AUTHORIZED_IN_PROGRESS
ACTIVE_NEXT_ACTION = W2_MI_R2_B_FOURTEEN_DAY_READ_ONLY_OBSERVATION
ROUND_3 = NOT_STARTED
```

Read:

```text
ROUND_2_OWNER_AUTHORIZATION.md
ROUND_2_CODEX_EXECUTION.md
ROUND_2_ACCEPTANCE_CRITERIA.md
ROUND_2_DAY0_RECEIPT.md
ROUND_2_OBSERVATION_LOG.md
ROUND_1_FINAL_RECEIPT.md
```

## Round 2 universe

Existing active whitelist remains 13:

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

Audit-only candidates:

```text
belgian_pro_league
turkish_super_lig
greek_super_league
scottish_premiership
```

```text
AUDIT_UNION = 17
ACTIVE_WHITELIST = 13_UNCHANGED
NET_NEW_RUNTIME_STATE = AUDIT_CANDIDATE_ONLY
```

The four net-new candidates must stay outside runtime whitelist/Scheduler/future-refresh/DayView.

## Current R2-B work

R2-A is complete in `ROUND_2_DAY0_RECEIPT.md`. PR `#494` delivered the audit
foundation and zero-call 17-row dry-run. Day-0 recorded one `/leagues` request
for each row; all 17 were plan-restricted, so no deeper calls were eligible.

```text
ROUND2_OBSERVATION_START_UTC = 2026-08-08T01:53:55.509495+00:00
ROUND2_OBSERVATION_END_UTC = 2026-08-22T01:53:55.509495+00:00
```

Use only existing persisted evidence and authorized production collection.
Do not repeat Day-0 calls or create a new collection schedule during R2-B.

## R2-B/R2-C

The Day-0 evidence capture started the 14-calendar-day observation window above.

Temporal evidence comes from existing persisted W2 captures/read models and already-authorized production collection. No new persistent polling for net-new candidates is authorized.

At the end, produce exactly 17 truthful capability rows. Insufficient evidence is valid and blocks readiness claims.

No row is automatically enabled/promoted.

## Permanent guards

```text
MODEL_MARKET_DIVERGENCE != MARKET_OPPORTUNITY
HIGH_OVERROUND != HIGH_VALUE
HIGH_OVERROUND != HIGH_INFORMATION
RecommendationDecisionV4 = DIAGNOSTIC_INPUT_NOT_PRODUCT_AUTHORITY
BETTING_EDGE_CLAIM = FORBIDDEN
ACTIVE_WHITELIST = 13_UNCHANGED
PRODUCTION_PROVIDER_POLICY_CHANGE = false
PRODUCTION_SCHEDULER_POLICY_CHANGE = false
ROUND_3 = NOT_STARTED
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
H_RESULT_ACCESS = PERMANENTLY_CLOSED
```

For bounded Round 2 failures, fail closed at the gate, fix inside the authorized audit scope, and continue. New owner authorization is required only for scope expansion or permanent-stop-line changes.
