# W2 Current Context

This is the mutable current authority for W2. It is maintained directly on branch `context/current` without a pull request, CI, Release Candidate, image build or deployment. Superseded context is replaced rather than retained as current authority.

## Current direction

W2 is not building the full quant platform yet. Phase 0.5 first determines whether W2 has a reproducible predictive or economic edge in low-overround Pinnacle AH/OU markets.

```text
PROGRAM = W2_FOOTBALL_QUANT_EDGE_EXISTENCE
PROTOCOL = W2_PHASE_0_5_AH_OU_EDGE_EXISTENCE_PROTOCOL_V1_RC3
PROTOCOL_FROZEN = true
ACTIVE_NEXT_ACTION = W2_PHASE_0_5_R2B_V_EVALUATION_AND_CONDITIONAL_H_MANIFEST_FREEZE
CURRENT_STATUS = R1_R2_FREEZE_REPORTED_PREUNLOCK_RECHECK_REQUIRED
```

Only `ECONOMIC_EDGE_CANDIDATE` may authorize preparation of the W2 Football Quant Platform total-design document.

## R1/R2 implementation report

The D-training and V-manifest implementation reports:

```text
D_TRAINING_ROWS = 21518
M2_DIVISIONS_FITTED = 20
M4_CANDIDATES = PRE/CLOSE × OU/AH × 4 L2
V_CANDIDATE_PREDICTION_ROWS = 14909
V_PRE_SELECTION_CANDIDATE_ROWS = 59636
V_RESULT_COLUMNS_READ = false
H_RESULT_COLUMNS_READ = false
```

Frozen V artifacts:

```text
V_CANDIDATE_PREDICTION_MANIFEST_SHA256 =
591314c9f13fc3256ca51aef6c65953150f40912e776ff8d6347b1701d24033f

V_PRE_SELECTION_CANDIDATE_MANIFEST_SHA256 =
e582585aaa57ac5cac894a2fad071dfadfa6ad7890b84ba4c8b3d74e4bd3fe13
```

Receipt path:

```text
/Users/liudehua/.hermes/workspace/w2-phase05-research/
r1_v_manifest_20260807/artifacts/R1_R2_FREEZE_RECEIPT.json
```

This report is not permission to open V immediately. The next task must first re-hash the two manifests, validate the full receipt and repeat the result-access/leakage checks.

## Current staged access

```text
D = usable for existing training and conditional D+V refit
V = one-time access only after R1/R2 freeze precheck passes
H = closed
```

The next execution may continue conditionally:

1. Validate the R1/R2 freeze pack without reading V outcomes.
2. If validation fails, stop and keep V/H closed.
3. If validation passes, open V results once and run the frozen V evaluation.
4. If V fails, permanently close H and issue `NO_EDGE` or `INSUFFICIENT_EVIDENCE`.
5. If V passes, automatically run the frozen D+V final refit and generate/freeze H prediction and PRE-selection manifests.
6. Stop before reading any H result.

## Frozen universe

```text
SOURCE = FOOTBALL_DATA_MMZ_ONLY
D = 2019_20,2020_21,2021_22
V = 2022_23,2023_24
H = 2024_25,2025_26
PRIMARY_PREDICTIVE = OU_2_5,AH_HALF_GOAL_LINES
PRIMARY_ECONOMIC = OU_2_5
ODDS_SOURCE = PINNACLE_ONLY
```

## Frozen models and methods

```text
M0_PRE / M0_CLOSE = PINNACLE_MARKET_ONLY
M2 = PURE_GOALS_DIXON_COLES_PER_DIVISION
RHO_GRID = -0.20_TO_+0.20_STEP_0.01_TRAIN_ONLY
M4_PRE / M4_CLOSE = BINARY_LOGISTIC_RESIDUAL_WITH_MARKET_LOGIT_OFFSET_AND_L2
M4_FEATURES = INTERCEPT,MODEL_MARKET_LOGIT_GAP
L2_GRID = 0.01,0.1,1.0,10.0
PRIMARY_DEVIG = PROPORTIONAL
```

OU 2.5 PRE selection remains fixed:

```text
select only the higher predicted-EV side
predicted EV < 3% => NO_SELECTION
exact tie => NO_SELECTION_TIE
one primary selection per fixture/market
fixed 1 unit
no Kelly, no compounding, no CLOSE field in PRE selection
```

`ev_se` is lambda-scenario sensitivity only. It is not a sampling standard error and must not be used as a confidence bound.

## V evaluation contract

V evaluation is static:

```text
V_EVALUATION_MODE = STATIC_TRAIN_D_NO_V_OUTCOME_UPDATE
```

After the one-time V unlock:

- evaluate all frozen L2 candidates only;
- calculate paired Log Loss, Brier and calibration on matching fixtures;
- calculate `PREDICTIVE_LIFT = market_log_loss - model_log_loss`;
- settle only the already frozen OU 2.5 PRE selections at their original PRE line/price;
- select final L2 from the frozen grid using V only;
- do not add features, markets, thresholds or candidates.

## Conditional R3/R4

If V passes, refit final models on D+V with the selected frozen hyperparameters, then generate H predictions and H PRE selections while H outcomes remain inaccessible.

```text
H_EVALUATION_MODE = STATIC_REFIT_D_PLUS_V_NO_H_OUTCOME_UPDATE
```

Freeze:

```text
FINAL_M2_MODEL_HASHES
FINAL_M4_PRE_MODEL_HASH
FINAL_M4_CLOSE_MODEL_HASH
FINAL_TRAINING_POPULATION_HASH
H_PREDICTION_MANIFEST_SHA256
H_SELECTION_MANIFEST_SHA256
```

Then stop before H result access.

## Final verdicts

```text
INSUFFICIENT_EVIDENCE
NO_EDGE
PREDICTIVE_INCREMENT_ONLY
ECONOMIC_EDGE_CANDIDATE
```

## Hard stop

```text
H_RESULT_ACCESS = false
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
