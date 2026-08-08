# NEXT ACTION

Current action:

```text
ACTIVE_NEXT_ACTION = W2_MI_R2_AUDIT_FOUNDATION_AND_DAY0_BASELINE
ROUND_1 = PASS
ROUND_2 = AUTHORIZED_IN_PROGRESS
ROUND_2_PHASE = R2_A_AUDIT_FOUNDATION_AND_DAY0_BASELINE
ROUND_3 = NOT_STARTED
```

## Required authority read order

Read from `origin/context/current` in this order:

1. `CURRENT_CONTEXT.md`
2. `CURRENT_STATE.yaml`
3. `CURRENT_PRODUCT_DESIGN.md`
4. `CURRENT_TASK_CHECKLIST.md`
5. `NEXT_ACTION.md`
6. `ROUND_2_OWNER_AUTHORIZATION.md`
7. `ROUND_2_CODEX_EXECUTION.md`
8. `ROUND_2_ACCEPTANCE_CRITERIA.md`
9. `ROUND_1_FINAL_RECEIPT.md`
10. `AI_PROJECT_CONTEXT.md`
11. `AI_QUANT_PROJECT_CONTEXT.md`
12. `AGENTS.md`
13. `QUANT_AGENTS.md`
14. `.github/copilot-instructions.md`

Use latest trusted `origin/main` as code baseline. Round 2 initial main is:

```text
f7860813646ce9718931dff331c09ce2fe7a71ba
```

Re-resolve main before editing and record any advancement separately.

## Immediate R2-A objective

Build and validate the audit foundation required to inspect the 17-competition union without changing runtime whitelist membership.

Required first sequence:

```text
1. audit current main + current runtime authorities
2. create one bounded Round 2 audit-tooling PR
3. add audit-only descriptor support for the four net-new candidates outside runtime whitelist discovery
4. add deterministic Provider-backed identity resolution; no guessed league IDs
5. preserve existing evidence-only/coverage/enablement audit modes
6. add cumulative quota ledger + 20-call Provider reserve guard
7. prove dry-run union count = 17 and Provider calls = 0
8. complete required PR/CI validation
9. only after tooling acceptance, run controlled Day-0 evidence-only Provider baseline
10. record exact observation start timestamp and start the 14-day R2-B evidence window
```

## Audit universe

Existing active whitelist remains exactly 13:

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
```

The four net-new candidates must not be added to CompetitionRegistry runtime whitelist, Scheduler, future-refresh, DayView or public cards in Round 2.

## Provider authorization

Controlled Provider calls are explicitly owner-authorized under `ROUND_2_OWNER_AUTHORIZATION.md` after R2-A tooling gates pass.

```text
ALLOW_CONTROLLED_PROVIDER_AUDIT_CALLS = true
ALLOW_PRODUCTION_REFRESH_CALLS_FOR_R2 = false
AUTOMATIC_RETRY = false
ROUND2_AUDIT_DAILY_HARD_CAP = 80
ROUND2_AUDIT_CUMULATIVE_HARD_CAP = 200
ROUND2_MIN_PROVIDER_DAILY_REMAINING = 20
REQUEST_INTERVAL_SECONDS_MIN = 10
```

Day-0 evidence-only theoretical maximum:

```text
17 * 4 = 68 calls
```

If quota, identity, plan or schema hard-stop fires, stop that gate, preserve evidence and resume within the same Round 2 authorization. Do not raise limits or ask for a new owner authorization unless scope must expand.

## Round 2 phases

```text
R2_A = AUDIT_FOUNDATION_AND_DAY0_BASELINE
R2_B = FOURTEEN_DAY_READ_ONLY_OBSERVATION
R2_C = FINAL_17_ROW_CAPABILITY_DECISION
```

The 14-day window uses existing persisted W2 captures and existing authorized production collection for temporal evidence. Round 2 does not authorize a new persistent polling schedule for the four audit-only candidates.

Insufficient evidence is a valid audited result; it must block readiness claims rather than trigger extra collection.

## Permanent boundaries

```text
ACTIVE_WHITELIST_CHANGE = false
PRODUCTION_PROVIDER_POLICY_CHANGE = false
PRODUCTION_PROVIDER_ALLOWLIST_CHANGE = false
PRODUCTION_SCHEDULER_POLICY_CHANGE = false
NEW_PERSISTENT_COLLECTION_FOR_NET_NEW = false
ROUND_3 = NOT_STARTED
BETTING_EDGE_CLAIM = FORBIDDEN
MODEL_MARKET_DIVERGENCE_AS_OPPORTUNITY = FORBIDDEN
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
```

Detailed execution authority: `ROUND_2_CODEX_EXECUTION.md`.

Binding acceptance authority: `ROUND_2_ACCEPTANCE_CRITERIA.md`.

Do not begin Round 3 or enable/promote any league automatically after Round 2.