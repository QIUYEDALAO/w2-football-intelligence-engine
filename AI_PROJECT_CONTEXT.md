# W2 AI Project Context

Current mutable authority is maintained on branch `context/current`.

## Current program

```text
PRODUCT = W2 Football Intelligence
PROGRAM = W2_FOOTBALL_MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
OWNER_DECISION = APPROVED_CONTINUE_UNTIL_ACCEPTED
ACTIVE_NEXT_ACTION = W2_MI_R1_PRODUCT_SEMANTICS_AND_STATUS_REFRAME
ACTIVE_RUNTIME_PR = 493
ROUND_1_STATUS = IN_PROGRESS_REMEDIATION
```

Read `ROUND_1_OWNER_CONTINUATION_AUTHORIZATION.md` for explicit owner continuation authority, `ROUND_1_CODEX_EXECUTION.md` for execution, and `ROUND_1_ACCEPTANCE_CRITERIA.md` for acceptance.

Phase 0.5 is closed with `NO_EDGE`; H is permanently closed under that protocol.

Permanent product rule:

```text
MODEL_MARKET_DIVERGENCE != MARKET_OPPORTUNITY
RecommendationDecisionV4 = DIAGNOSTIC_INPUT_NOT_PRODUCT_AUTHORITY
```

## League correction

Current active whitelist baseline is 13 and must not change in Round 1:

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

The European `5 + 6` grouping is not a replacement whitelist. `Eredivisie` and `Primeira Liga` are already in the baseline 13. The future net-new candidates are only:

```text
Belgian Pro League
Turkish Super Lig
Greek Super League
Scottish Premiership
```

Future Round 2 candidate union:

```text
13 EXISTING + 4 NET_NEW = 17
```

Round 1 performs zero league additions and zero new Provider calls initiated by Round 1.

## Round 1

One bounded API/Web runtime change in PR #493:

- intelligence-first public product;
- seven deterministic intelligence states;
- four independent risk dimensions;
- `MARKET_STABLE`/zero alerts as valid output;
- V4 diagnostic-only product role;
- divergence guard across API/read-model/Web/browser;
- market facts independent from V4 pick/no-pick state;
- public shell: Market Overview / Match Intelligence / Data & Operations Summary;
- existing 13 whitelist unchanged;
- current Scheduler/Provider policy preserved.

## Delivery authorization — no attempt cap

```text
ONE_RUNTIME_PR = PR_493_ONLY
ALLOW_NEW_PR_FAST_AFTER_SOURCE_CHANGE = true
ALLOW_REPLACEMENT_EXACT_HEAD_FULL_RC_AFTER_FAILED_RC = true
ALLOW_REPEAT_PR_FAST_AND_FULL_RC_UNTIL_FINAL_SUCCESS = true
FAILED_PR_FAST_OR_RC_ATTEMPTS_CONSUME_FINAL_SUCCESS_SLOT = false
FAILED_FULL_RC_RUN_31151557970_IS_FINAL_RC = false
ONE_SUCCESSFUL_FINAL_EXACT_HEAD_FULL_RC = true
ONE_FINAL_MERGE = true
ONE_FINAL_ACCEPTED_DEPLOYMENT = true
```

The words `one final exact-head Full RC` mean **one successful final RC**, not only one attempt.

Every new source head requires a new PR Fast. After that exact head is green, a replacement exact-head Full RC is explicitly authorized. If it fails for an in-scope reason, preserve the evidence, repair PR #493 and repeat until success. No additional owner authorization is required.

```text
FAIL_CLOSED = DO_NOT_ADVANCE_PAST_FAILED_GATE
FAIL_CLOSED != STOP_WORK_AND_WAIT_FOR_OWNER
```

Current failed RC `31151557970` remains historical failure evidence and does not satisfy or consume the final successful RC requirement.

Round 1 ends only after successful final RC + merge commit + same-source deployment + public API/browser acceptance + all acceptance gates PASS.

## Later rounds

Round 2 is blocked until Round 1 PASS and explicit owner authorization. Its future candidate universe is 17, not 11.

Round 3 remains blocked and must require:

```text
OVERROUND_PERCENTILE = REQUIRED_ALERT_COVARIATE
```

## Permanent boundaries

```text
BETTING_EDGE_CLAIM = FORBIDDEN
MODEL_DIVERGENCE_AS_OPPORTUNITY = FORBIDDEN
SIGNAL_LEDGER_FOR_EXECUTION = NOT_AUTHORIZED
PORTFOLIO = NOT_AUTHORIZED
RISK_KELLY = NOT_AUTHORIZED
TWO_LEG_PARLAY = NOT_AUTHORIZED
REAL_MONEY = NOT_AUTHORIZED

PERSISTENT_SCHEDULER = ON_CONTROLLED
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
```
