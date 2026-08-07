# W2 AI Project Context

Current mutable context is maintained on branch `context/current`. Read:

- `CURRENT_CONTEXT.md`
- `CURRENT_STATE.yaml`
- `CURRENT_TASK_CHECKLIST.md`
- `NEXT_ACTION.md`
- `AI_QUANT_PROJECT_CONTEXT.md`
- `QUANT_AGENTS.md`

Context changes are direct replacements and do not use PR, CI, Release Candidate, image build or deployment.

## Current decision

```text
PROGRAM = W2_FOOTBALL_QUANT_EDGE_EXISTENCE
PHASE_0_5_STATUS = COMPLETE
FINAL_VERDICT = NO_EDGE
ACTIVE_NEXT_ACTION = OWNER_DECISION_REQUIRED_AFTER_NO_EDGE
NEXT_CODE_ACTION = NONE_AUTHORIZED
H_RESULT_ACCESS = PERMANENTLY_CLOSED
```

Phase 0.5 tested whether a pure-goals per-division Dixon-Coles model plus a Pinnacle-anchored binary residual model could provide predictive or PRE-price economic edge in OU 2.5 and AH half-line markets.

Reported V results:

```text
OU_CLOSE_BEST_PREDICTIVE_LIFT = -0.0000758
AH_CLOSE_BEST_PREDICTIVE_LIFT = -0.0006467
OU_PRE_FROZEN_SELECTIONS = 7566
OU_PRE_FROZEN_STRATEGY_ROI = -5.32_PERCENT
V_CONTINUATION_GATE = FAIL
```

The best frozen candidates did not improve on Pinnacle closing prediction, and the frozen PRE strategy remained negative. R3/R4 were not executed and H is permanently closed under the protocol.

## Product implication

Do not build the W2 Football Quant Platform around this tested model/selection hypothesis.

Recommended role:

```text
W2_FOOTBALL_MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
```

Existing W2 assets remain useful for:

- fixture, team, raw-payload and quote identity;
- data coverage, freshness and anomaly monitoring;
- market movement and price diagnostics;
- probability calibration and market-baseline evaluation;
- research replay and evidence tooling;
- the deployed Dashboard and controlled Scheduler.

A future quant program is allowed only with a genuinely new information source, model/edge hypothesis and pre-registered protocol. V/H outcomes from this protocol may not be used to tune the failed hypothesis.

## Hard boundaries

```text
OPEN_H_RESULTS = false
RERUN_FAILED_PROTOCOL_WITH_CHANGED_PARAMETERS = false
PRODUCTION_CODE_CHANGE = false
PRODUCTION_MODEL_CHANGE = false
SIGNAL_LEDGER_DEVELOPMENT = false
PORTFOLIO_DEVELOPMENT = false
PROVIDER_CALLS = 0
DEPLOYMENT_EXECUTED = false
REAL_MONEY = NOT_AUTHORIZED

PERSISTENT_SCHEDULER = ON_CONTROLLED
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
```

No code action is currently authorized. Wait for the owner product-direction decision.
