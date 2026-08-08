# W2 AI Project Context

Current authority is `origin/context/current`.

```text
PRODUCT = W2 Football Intelligence
PROGRAM = W2_FOOTBALL_MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
ROUND_1 = PASS
ROUND_2 = AUTHORIZED_IN_PROGRESS
ACTIVE_NEXT_ACTION = W2_MI_R2_AUDIT_FOUNDATION_AND_DAY0_BASELINE
ROUND_3 = NOT_STARTED
```

Read:

```text
ROUND_2_OWNER_AUTHORIZATION.md
ROUND_2_CODEX_EXECUTION.md
ROUND_2_ACCEPTANCE_CRITERIA.md
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

## Current R2-A work

Codex must create one bounded audit-tooling PR that:

- supports 13 registered + 4 audit-only descriptors;
- keeps audit-only descriptors outside runtime CompetitionRegistry discovery;
- resolves net-new Provider identity deterministically from real `/leagues` evidence;
- forbids fuzzy/guessed identity;
- preserves existing audit modes;
- adds persistent sanitized cumulative audit-call accounting;
- enforces daily cap 80, cumulative cap 200, Provider remaining reserve 20, interval >=10s and no automatic retry;
- proves dry-run 17 rows with Provider calls 0;
- performs zero Provider calls during PR development/CI.

After tooling acceptance, owner-authorized controlled audit calls may run through the Round 2 audit path.

Day-0 starts with evidence-only semantics:

```text
4 planned calls per competition
17 targets
68 theoretical max for first complete baseline
```

Do not raise limits to complete the batch.

## R2-B/R2-C

The first successful Day-0 baseline starts a 14-calendar-day observation window.

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