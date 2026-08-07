# W2 Market Intelligence — AI Handoff

Current authority is `context/current`.

## Current decision

```text
PRODUCT_NAME = W2 Football Intelligence
PROGRAM = W2_FOOTBALL_MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
OWNER_DECISION = APPROVED_CONTINUE_UNTIL_ACCEPTED
ACTIVE_NEXT_ACTION = AWAIT_OWNER_ROUND_2_AUTHORIZATION
ACTIVE_RUNTIME_PR = 493
ROUND_1_STATUS = PASS
ROUND_2_STATUS = NOT_STARTED
```

Phase 0.5 is closed with `NO_EDGE`; H is permanently closed. Round 1 is accepted; no new code task is authorized.

All later PR #493 remediation language is historical only. Do not resume it.

Permanent evidence guard:

```text
MODEL_MARKET_DIVERGENCE != MARKET_OPPORTUNITY
```

V4 product role:

```text
RecommendationDecisionV4 = DIAGNOSTIC_INPUT_NOT_PRODUCT_AUTHORITY
```

## League baseline correction

Current active whitelist baseline:

```text
COUNT = 13
ROUND_1_CHANGE = FORBIDDEN
```

The 13 identities are:

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

The European `5 + 6` grouping is not a replacement whitelist. Only four members are net-new relative to the current 13:

```text
Belgian Pro League
Turkish Super Lig
Greek Super League
Scottish Premiership
```

Future candidate union:

```text
13 + 4 = 17
```

Do not add/audit/call/schedule these four during Round 1.

## Round 1 execution

Read in this order for continuation/delivery authority:

```text
ROUND_1_OWNER_CONTINUATION_AUTHORIZATION.md
ROUND_1_CODEX_EXECUTION.md
ROUND_1_ACCEPTANCE_CRITERIA.md
```

Implement/finish one bounded API/Web semantic refactor in PR #493 only. Required public states:

```text
MARKET_STABLE
MARKET_MOVEMENT
MARKET_ANOMALY
MODEL_MARKET_DISAGREEMENT
DATA_INCOMPLETE
MODEL_DIAGNOSTIC_WARNING
COLLECTION_INCIDENT
```

Required risk dimensions:

```text
EVENT_RISK
DATA_RISK
MODEL_RISK
COLLECTION_RISK
```

Preserve current 13 whitelist, current Provider/Scheduler policy and historical V4/settlement evidence.

## Delivery — explicit continuation authority

```text
ONE_RUNTIME_PR = PR_493_ONLY
ALLOW_REMEDIATION_COMMITS_IN_PR_493 = true
ALLOW_NEW_PR_FAST_AFTER_SOURCE_CHANGE = true
ALLOW_REPLACEMENT_EXACT_HEAD_FULL_RC_AFTER_FAILED_RC = true
ALLOW_REPEAT_PR_FAST_AND_FULL_RC_UNTIL_FINAL_SUCCESS = true
FAILED_ATTEMPTS_CONSUME_FINAL_SUCCESS_SLOT = false
FAILED_FULL_RC_31151557970_IS_FINAL_RC = false
ONE_SUCCESSFUL_FINAL_EXACT_HEAD_FULL_RC = true
ONE_FINAL_MERGE = true
ONE_FINAL_ACCEPTED_DEPLOYMENT = true
```

There is **no one-attempt limit** on PR Fast or Full RC during bounded Round 1 remediation.

A source-changing remediation must obtain a new exact-head PR Fast success and then run a new replacement exact-head Full RC. If that RC fails for an in-scope reason, continue fixing PR #493 and repeat. No additional owner authorization is required.

```text
FAIL_CLOSED = DO_NOT_ADVANCE_PAST_FAILED_GATE
FAIL_CLOSED != ABANDON_ROUND_1
```

Only the final successful RC on the final accepted head can authorize merge/deployment.

Stop only after final RC success, merge commit, same-source deployment, public API/browser acceptance and all Round 1 acceptance criteria PASS.

## Hard boundaries

```text
BETTING_EDGE_CLAIM = FORBIDDEN
SIGNAL_LEDGER_FOR_EXECUTION = NOT_AUTHORIZED
PORTFOLIO = NOT_AUTHORIZED
RISK_KELLY = NOT_AUTHORIZED
TWO_LEG_PARLAY = NOT_AUTHORIZED
REAL_MONEY = NOT_AUTHORIZED

CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
```
