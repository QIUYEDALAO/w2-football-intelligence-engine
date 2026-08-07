# W2 Football Quant — AI Handoff

Read first from branch `context/current`:

1. `CURRENT_CONTEXT.md`
2. `CURRENT_STATE.yaml`
3. `CURRENT_TASK_CHECKLIST.md`
4. `NEXT_ACTION.md`
5. `QUANT_AGENTS.md`

Context updates do not use PR, CI, Release Candidate, image build or deployment.

## Final Phase 0.5 decision

```text
PROGRAM = W2_FOOTBALL_QUANT_EDGE_EXISTENCE
PROTOCOL = W2_PHASE_0_5_AH_OU_EDGE_EXISTENCE_PROTOCOL_V1_RC3
PROTOCOL_FROZEN = true
PHASE_0_5_STATUS = COMPLETE
FINAL_VERDICT = NO_EDGE
ACTIVE_NEXT_ACTION = OWNER_DECISION_REQUIRED_AFTER_NO_EDGE
NEXT_CODE_ACTION = NONE_AUTHORIZED
H_RESULT_ACCESS = PERMANENTLY_CLOSED
```

## Evidence summary

```text
R2A_PRECHECK = 41/41 PASS
V_ROWS_READ_ONCE = 14909
OU_CLOSE_BEST_PREDICTIVE_LIFT = -0.0000758
AH_CLOSE_BEST_PREDICTIVE_LIFT = -0.0006467
OU_PRE_BEST_FROZEN_SELECTIONS = 7566
OU_PRE_BEST_FROZEN_STRATEGY_ROI = -5.32_PERCENT
V_CONTINUATION_GATE = FAIL
```

The best frozen OU and AH residual candidates did not improve on Pinnacle closing prediction in V. The frozen PRE OU 2.5 strategy also lost 5.32%. R3/R4 were not executed and H must never be opened under this protocol.

## Meaning

The following tested hypothesis failed:

```text
PURE_GOALS_DIXON_COLES_PER_DIVISION
+
PINNACLE_MARKET_ANCHORED_BINARY_RESIDUAL
+
FROZEN_3_PERCENT_PRE_EV_SELECTION
```

Do not:

- lower or change the threshold and rerun the same V/H data;
- add features based on V results;
- open H to search for reversal;
- build Signal Ledger, Shadow, Portfolio, Risk, Kelly or Quant Dashboard around this hypothesis;
- claim economic or predictive edge.

## Recommended W2 role

```text
W2_FOOTBALL_MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
```

The existing W2 remains valuable for:

- real fixture and odds data;
- identity and raw-payload authority;
- market freshness and movement monitoring;
- data quality and coverage;
- calibration and market-baseline comparison;
- model diagnostics and historical replay;
- the existing controlled Dashboard and scheduler.

Any future quant research requires:

```text
NEW_INFORMATION_SOURCE
NEW_MODEL_OR_EDGE_HYPOTHESIS
NEW_PRE_REGISTERED_PROTOCOL
```

## Current boundary

```text
NO_ACTIVE_CODE_TASK = true
H_RESULT_COLUMNS_READ = false
PROVIDER_CALLS = 0
PRODUCTION_CODE_CHANGE = false
PRODUCTION_MODEL_CHANGE = false
PRODUCTION_DB_WRITES = 0
SIGNAL_LEDGER_DEVELOPMENT = false
PORTFOLIO_DEVELOPMENT = false
DEPLOYMENT_EXECUTED = false
REAL_MONEY = NOT_AUTHORIZED

CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
```

Codex must wait for the owner product-direction decision.
