# W2 Current Task Checklist

This is the complete current task order for W2. It is maintained directly on branch `context/current`; context updates do not use PR or CI.

## Program

```text
PROGRAM = W2_FOOTBALL_QUANT_EDGE_EXISTENCE
PROTOCOL = W2_PHASE_0_5_AH_OU_EDGE_EXISTENCE_PROTOCOL_V1_RC3
PROTOCOL_FROZEN = true
EXECUTION = AUTHORIZED_STAGEWISE
ACTIVE_TASK = Q05-R2B-V-EVALUATION-AND-CONDITIONAL-R3-R4
```

No task below authorizes Provider calls, production changes, deployment, Signal Ledger, Portfolio, Kelly, 2×1 or real-money execution.

---

## Q05-00 — Direction and protocol freeze

```text
STATUS = DONE
```

- Stop the Sporttery-specific implementation direction.
- Preserve the operational W2 system unchanged.
- Freeze Phase 0.5 AH/OU edge-existence protocol and staged result-access gates.

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
STATUS = DONE_REPORTED_PREUNLOCK_RECHECK_REQUIRED
```

Reported implementation:

```text
D_TRAINING_ROWS = 21518
M2_DIVISIONS_FITTED = 20
M2_RHO_GRID = -0.20_TO_+0.20_STEP_0.01
M4_CANDIDATES = PRE/CLOSE × OU/AH × 4 L2
D_RESULT_COLUMNS_READ = true
V_RESULT_COLUMNS_READ = false
H_RESULT_COLUMNS_READ = false
```

The R2B task must validate the referenced M2/M4 manifests before V unlock.

---

## Q05-R2 — V prediction and PRE-selection freeze

```text
STATUS = DONE_REPORTED_PREUNLOCK_RECHECK_REQUIRED
```

Reported artifacts:

```text
V_CANDIDATE_PREDICTION_ROWS = 14909
V_PRE_SELECTION_CANDIDATE_ROWS = 59636

V_CANDIDATE_PREDICTION_MANIFEST_SHA256 =
591314c9f13fc3256ca51aef6c65953150f40912e776ff8d6347b1701d24033f

V_PRE_SELECTION_CANDIDATE_MANIFEST_SHA256 =
e582585aaa57ac5cac894a2fad071dfadfa6ad7890b84ba4c8b3d74e4bd3fe13
```

Receipt:

```text
/Users/liudehua/.hermes/workspace/w2-phase05-research/
r1_v_manifest_20260807/artifacts/R1_R2_FREEZE_RECEIPT.json
```

V/H outcomes were reported unread. This must be revalidated before the one-time V unlock.

---

## Q05-R2A — Pre-unlock freeze verification

```text
STATUS = NEXT_PRECONDITION
V_RESULTS = CLOSED
H_RESULTS = CLOSED
```

Must pass before R2B:

1. Recompute both V artifact hashes and match the frozen values.
2. Validate the full R1/R2 receipt and referenced source/model manifests.
3. Confirm deterministic rerun byte identity.
4. Confirm M4 PRE visible CLOSE-field count = 0.
5. Confirm PRE and CLOSE model/training/parameter hashes are isolated.
6. Confirm all 16 expected M4 candidate models exist:
   - 2 phases × 2 markets × 4 L2 values.
7. Confirm V/H outcome-read count = 0 during R1/R2.
8. Confirm Provider calls, production writes, tracked-source changes, PR, CI and deployment = 0.

Failure result:

```text
BLOCKED_R1_R2_FREEZE_RECHECK
```

Keep V/H closed and stop.

---

## Q05-R2B — One-time V evaluation

```text
STATUS = AUTHORIZED_AFTER_R2A_PASS
V_RESULTS = ONE_TIME_ACCESS
H_RESULTS = CLOSED
V_EVALUATION_MODE = STATIC_TRAIN_D_NO_V_OUTCOME_UPDATE
```

### Predictive evaluation

For every frozen L2 candidate:

- OU 2.5 M4 CLOSE vs M0 CLOSE;
- AH half-goal M4 CLOSE vs M0 CLOSE;
- paired Log Loss;
- Brier;
- calibration diagnostics;
- `PREDICTIVE_LIFT = market_log_loss - model_log_loss`;
- fixture-paired coverage and exclusion matrix.

### V economic proxy

For each frozen M4 PRE L2 candidate:

- settle only frozen OU 2.5 PRE selections;
- retain original PRE line and PRE odds;
- fixed 1 unit;
- line-moved orders remain included;
- same-line CLV remains exploratory;
- report selected-order count, ROI and concentration diagnostics.

### Hyperparameter selection

Select only among:

```text
L2 = 0.01, 0.1, 1.0, 10.0
```

Use V only. Do not add features, models, thresholds, markets or devig methods.

### V continuation gate

If V fails the frozen gate:

```text
H_RESULT_ACCESS = PERMANENTLY_CLOSED
FINAL_VERDICT = NO_EDGE | INSUFFICIENT_EVIDENCE
```

Stop.

If V passes, continue automatically to R3 and R4.

---

## Q05-R3 — Conditional final D+V refit

```text
STATUS = CONDITIONAL_ON_V_GATE_PASS
H_RESULTS = CLOSED
```

Refit with frozen algorithms and V-selected L2:

- final per-division M2 on D+V;
- final M4 PRE on D+V;
- final M4 CLOSE on D+V.

Freeze:

```text
FINAL_M2_MODEL_HASHES
FINAL_M4_PRE_MODEL_HASH
FINAL_M4_CLOSE_MODEL_HASH
FINAL_TRAINING_POPULATION_HASH
FINAL_FEATURE_MANIFEST_HASH
FINAL_PARAMETER_MANIFEST_HASH
```

No H result may be read.

---

## Q05-R4 — Conditional H prediction and selection freeze

```text
STATUS = CONDITIONAL_ON_R3_COMPLETE
H_RESULTS = CLOSED
H_EVALUATION_MODE = STATIC_REFIT_D_PLUS_V_NO_H_OUTCOME_UPDATE
```

Using final D+V models and H non-result fields only:

- generate all H predictions;
- generate frozen OU 2.5 PRE selections;
- record selected/no-selection reasons;
- calculate selected-order count and design-side economic MDE without outcomes;
- do not update the model between H seasons.

Freeze:

```text
H_PREDICTION_MANIFEST_SHA256
H_SELECTION_MANIFEST_SHA256
```

Then stop before H result access.

---

## Q05-R5 — One-time H audit

```text
STATUS = BLOCKED_UNTIL_H_MANIFESTS_FROZEN_AND_CHATGPT_REVIEW
```

No automatic H unlock is allowed in the current task.

---

## Q05-R6 — Final verdict

```text
STATUS = BLOCKED_UNTIL_R5
```

Allowed final verdicts:

```text
INSUFFICIENT_EVIDENCE
NO_EDGE
PREDICTIVE_INCREMENT_ONLY
ECONOMIC_EDGE_CANDIDATE
```

Consequences:

- `NO_EDGE`: stop quant-platform development.
- `PREDICTIVE_INCREMENT_ONLY`: at most design a minimal forward Signal Ledger and fixed-unit Shadow measurement.
- `ECONOMIC_EDGE_CANDIDATE`: authorize the full W2 Football Quant Platform total-design document.
- No verdict authorizes real money.

---

## Current hard stop

```text
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

CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
```
