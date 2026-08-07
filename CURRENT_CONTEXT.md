# W2 Current Context

This is the mutable current authority for W2. It is maintained directly on branch `context/current` without a pull request, CI, Release Candidate, image build or deployment. Superseded context is replaced rather than retained as current authority.

## Phase 0.5 is complete

```text
PROGRAM = W2_FOOTBALL_QUANT_EDGE_EXISTENCE
PROTOCOL = W2_PHASE_0_5_AH_OU_EDGE_EXISTENCE_PROTOCOL_V1_RC3
PROTOCOL_FROZEN = true
FINAL_VERDICT = NO_EDGE
ACTIVE_NEXT_ACTION = OWNER_DECISION_REQUIRED_AFTER_NO_EDGE
NEXT_CODE_ACTION = NONE_AUTHORIZED
H_RESULT_ACCESS = PERMANENTLY_CLOSED
```

The frozen V gate failed. The protocol therefore forbids R3, R4 and any H audit.

## Decisive V evidence

Reported receipt:

```text
/Users/liudehua/.hermes/workspace/w2-phase05-research/
r2b_v_evaluation_20260807/artifacts/R2B_V_GATE_RECEIPT.json
```

Reported machine evidence:

```text
R2A_PRECHECK = 41/41 PASS
DETERMINISTIC_ARTIFACT_RECHECK = 9 PASS
V_ROWS_READ_ONCE = 14909

OU_CLOSE_BEST_PREDICTIVE_LIFT = -0.0000758
AH_CLOSE_BEST_PREDICTIVE_LIFT = -0.0006467

OU_PRE_BEST_FROZEN_SELECTION_COUNT = 7566
OU_PRE_BEST_FROZEN_STRATEGY_ROI = -5.32_PERCENT

V_CONTINUATION_GATE = FAIL
FINAL_VERDICT = NO_EDGE
H_RESULT_ACCESS = PERMANENTLY_CLOSED
```

`PREDICTIVE_LIFT = market_log_loss - model_log_loss`; both best values are negative, so even the best frozen residual candidates did not improve on Pinnacle closing probabilities in V. The frozen PRE strategy also lost 5.32% over 7,566 selections. This is not a low-sample `INSUFFICIENT_EVIDENCE` outcome; under the frozen continuation contract it is `NO_EDGE`.

The receipt bytes were not independently recomputed by ChatGPT because the file is local to the operator machine. The current context records the machine receipt and its declared protocol outcome.

## Binding consequence

The following work is not authorized:

```text
R3_D_PLUS_V_REFIT
R4_H_PREDICTION_AND_SELECTION_FREEZE
R5_H_AUDIT
SIGNAL_LEDGER_DEVELOPMENT
SHADOW_STRATEGY_PRODUCTIZATION
PORTFOLIO
RISK
KELLY
QUANT_DASHBOARD
REAL_MONEY
```

Do not open H to search for a reversal. Do not change the 3% selection threshold, model features, L2 grid, devig method, market scope or split assignment and rerun the same protocol. That would convert the held-out design into post-result tuning.

## Product conclusion

The tested hypothesis failed:

```text
PURE_GOALS_DIXON_COLES
+
PINNACLE_MARKET_ANCHORED_BINARY_RESIDUAL
+
FROZEN_PRE_SELECTION_RULE
```

has not shown predictive or economic edge in the V seasons for the tested OU 2.5 / AH half-line universe.

This does not prove that every possible football model is impossible. It proves that W2 must not build a quant platform around this tested model family and selection rule.

Recommended role for the existing W2 system:

```text
W2_FOOTBALL_MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
```

Existing useful assets remain:

- real fixtures, odds, raw payload and capture identity;
- data quality and coverage monitoring;
- market movement and freshness diagnostics;
- probability calibration and market-baseline comparison;
- model research and replay infrastructure;
- operational Dashboard and controlled scheduler.

A future quant attempt requires all three:

```text
NEW_INFORMATION_SOURCE
NEW_MODEL_OR_EDGE_HYPOTHESIS
NEW_PRE_REGISTERED_PROTOCOL
```

It may not reuse V/H results to tune the failed hypothesis.

## Existing operational track

```text
PERSISTENT_SCHEDULER = ON_CONTROLLED
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
```

The deployed W2 operational system remains unchanged.

## Current stop line

```text
NO_ACTIVE_QUANT_CODE_TASK = true
H_RESULT_COLUMNS_READ = false
PROVIDER_CALLS = 0
PRODUCTION_CODE_CHANGE = false
PRODUCTION_MODEL_CHANGE = false
PRODUCTION_DB_WRITES = 0
SIGNAL_LEDGER_DEVELOPMENT = false
PORTFOLIO_DEVELOPMENT = false
PR_CREATED = false
CI_RUN = false
DEPLOYMENT_EXECUTED = false
REAL_MONEY = NOT_AUTHORIZED
```
