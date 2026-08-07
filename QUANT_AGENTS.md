# W2 Market Intelligence Agent Instructions

Read from branch `context/current` before acting:

1. `CURRENT_CONTEXT.md`
2. `CURRENT_STATE.yaml`
3. `CURRENT_PRODUCT_DESIGN.md`
4. `CURRENT_TASK_CHECKLIST.md`
5. `NEXT_ACTION.md`
6. `AI_QUANT_PROJECT_CONTEXT.md`

Context updates do not use PR or CI. Runtime changes use the normal guarded delivery process.

## Current task

```text
ACTIVE_NEXT_ACTION = W2_MI_R1_PRODUCT_SEMANTICS_AND_STATUS_REFRAME
PROGRAM = W2_FOOTBALL_MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
```

The Phase 0.5 quant hypothesis is closed with `NO_EDGE`. Do not reopen H or retune the failed model family.

## Round 1 scope

One bounded API/Web runtime change:

- reposition the public product as market intelligence and model diagnostics;
- implement deterministic intelligence states;
- split event/data/model/collection risk dimensions;
- render `MARKET_STABLE` and zero-alert days as valid results;
- prevent model divergence from producing opportunity/recommendation language;
- preserve current V4 calculations as diagnostic input;
- preserve current league set, Provider policy and Scheduler behavior.

Required states:

```text
MARKET_STABLE
MARKET_MOVEMENT
MARKET_ANOMALY
MODEL_MARKET_DISAGREEMENT
DATA_INCOMPLETE
MODEL_DIAGNOSTIC_WARNING
COLLECTION_INCIDENT
```

Required guard:

```text
MODEL_MARKET_DIVERGENCE_AS_OPPORTUNITY = FORBIDDEN
```

## Round 1 prohibited work

- no league expansion;
- no new Provider calls or allowlist changes;
- no Scheduler policy changes;
- no full Market Radar scoring yet;
- no Model Lab analytics beyond semantic shell/diagnostic presentation;
- no Signal Ledger, Shadow, Portfolio, Risk, Kelly or 2×1;
- no real-money or betting-edge claims;
- no changes to Candidate/Formal/Lock/Production.

## Delivery

- use one clean worktree;
- use one runtime PR for the whole Round 1 goal;
- run focused tests during development;
- one exact-head full Release Candidate;
- one merge and one deployment;
- browser acceptance with real data and zero console errors;
- stop after Round 1 acceptance.

## Future design guard

Round 3 Market Radar must include:

```text
OVERROUND_PERCENTILE = REQUIRED_ALERT_COVARIATE
```

Overround adjusts market-noise/confidence. High-overround isolated movement is not automatically informative and should normally classify as `THIN_MARKET_NOISE` unless stronger evidence exists. Exact thresholds are frozen only after the Round 2 live capability audit.

## Permanent boundaries

```text
BETTING_EDGE_CLAIM = FORBIDDEN
MODEL_DIVERGENCE_AS_OPPORTUNITY = FORBIDDEN
SIGNAL_LEDGER_FOR_EXECUTION = NOT_AUTHORIZED
PORTFOLIO = NOT_AUTHORIZED
RISK_KELLY = NOT_AUTHORIZED
REAL_MONEY = NOT_AUTHORIZED

CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
```
