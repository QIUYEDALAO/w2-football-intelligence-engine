# W2 Current Task Checklist

This is the complete current task order for W2. It is maintained directly on branch `context/current`; context updates do not use PR or CI.

## Program status

```text
PROGRAM = W2_FOOTBALL_QUANT_EDGE_EXISTENCE
PROTOCOL = W2_PHASE_0_5_AH_OU_EDGE_EXISTENCE_PROTOCOL_V1_RC3
PROTOCOL_FROZEN = true
PHASE_0_5_STATUS = COMPLETE
FINAL_VERDICT = NO_EDGE
ACTIVE_TASK = OWNER_DECISION_REQUIRED_AFTER_NO_EDGE
NEXT_CODE_TASK = NONE_AUTHORIZED
```

No task below authorizes Provider calls, production changes, deployment, Signal Ledger, Portfolio, Kelly, 2×1 or real-money execution.

---

## Q05-00 — Direction and protocol freeze

```text
STATUS = DONE
```

---

## Q05-01 — Outcome-blind inventory and RC3 binding

```text
STATUS = DONE
```

- 156 source files recovered and bound.
- 20 divisions × 7 seasons = 140 mutually exclusive division-season units.
- D/V/H = 3/2/2 seasons.
- RC3 canonical pack recovered read-only.
- B1–B5 passed after exact-byte recovery.

---

## Q05-R1 — D training

```text
STATUS = DONE
```

```text
D_TRAINING_ROWS = 21518
M2_DIVISIONS_FITTED = 20
M2_RHO_GRID = -0.20_TO_+0.20_STEP_0.01
M4_CANDIDATES = PRE/CLOSE × OU/AH × 4 L2
```

---

## Q05-R2 — V prediction and PRE-selection freeze

```text
STATUS = DONE
```

```text
V_CANDIDATE_PREDICTION_ROWS = 14909
V_PRE_SELECTION_CANDIDATE_ROWS = 59636

V_CANDIDATE_PREDICTION_MANIFEST_SHA256 =
591314c9f13fc3256ca51aef6c65953150f40912e776ff8d6347b1701d24033f

V_PRE_SELECTION_CANDIDATE_MANIFEST_SHA256 =
e582585aaa57ac5cac894a2fad071dfadfa6ad7890b84ba4c8b3d74e4bd3fe13
```

---

## Q05-R2A — Pre-unlock verification

```text
STATUS = DONE_PASS
CHECKS = 41/41
DETERMINISTIC_ARTIFACTS = 9/9
```

---

## Q05-R2B — One-time V evaluation

```text
STATUS = DONE_FAIL_CONTINUATION_GATE
V_ROWS_READ_ONCE = 14909
```

Results:

```text
OU_CLOSE_BEST_PREDICTIVE_LIFT = -0.0000758
AH_CLOSE_BEST_PREDICTIVE_LIFT = -0.0006467
OU_PRE_BEST_FROZEN_SELECTION_COUNT = 7566
OU_PRE_BEST_FROZEN_STRATEGY_ROI = -5.32_PERCENT
V_CONTINUATION_GATE = FAIL
FINAL_VERDICT = NO_EDGE
```

Receipt:

```text
/Users/liudehua/.hermes/workspace/w2-phase05-research/
r2b_v_evaluation_20260807/artifacts/R2B_V_GATE_RECEIPT.json
```

---

## Q05-R3 — Final D+V refit

```text
STATUS = CANCELLED_BY_V_GATE_FAIL
EXECUTED = false
```

---

## Q05-R4 — H prediction and selection freeze

```text
STATUS = CANCELLED_BY_V_GATE_FAIL
EXECUTED = false
```

---

## Q05-R5 — One-time H audit

```text
STATUS = PERMANENTLY_FORBIDDEN_BY_V_GATE_FAIL
H_RESULT_ACCESS = PERMANENTLY_CLOSED
```

Do not open H to seek a reversal.

---

## Q05-R6 — Final verdict

```text
STATUS = DONE
FINAL_VERDICT = NO_EDGE
```

Protocol consequence:

- The tested model family did not provide predictive lift over Pinnacle closing markets.
- The frozen PRE OU 2.5 strategy lost 5.32% on 7,566 V selections.
- Do not build the W2 Football Quant Platform around this hypothesis.
- Do not authorize Signal Ledger, Portfolio, Risk, Kelly, 2×1 or real-money workflows.

---

## NEXT-01 — Owner product-direction decision

```text
STATUS = NEXT
TYPE = NON_CODE_DECISION
```

Recommended product direction:

```text
W2_FOOTBALL_MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
```

Potential scope after owner approval:

- data coverage, identity and freshness monitoring;
- market movement and anomaly alerts;
- probability calibration and market-baseline diagnostics;
- model evidence and replay tooling;
- existing operational Dashboard and scheduler improvements;
- no profit or betting-edge claim.

Alternative quant research is permitted only under a new protocol with a genuinely new information source and model hypothesis. It may not tune the failed Phase 0.5 hypothesis on V/H outcomes.

---

## Current hard stop

```text
NO_ACTIVE_CODE_TASK = true
OPEN_H_RESULTS = false
RERUN_PHASE_0_5_WITH_CHANGED_THRESHOLDS = false
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

CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
```
