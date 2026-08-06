# W2 Current Context

This file is the mutable current context for W2. It is maintained on branch `context/current` and is updated directly without a pull request, CI, Release Candidate, image build or deployment. Superseded context is replaced rather than retained as authority.

## Current direction

W2 is no longer pursuing a Sporttery-specific quant system. The existing operational W2 system remains deployed, but the next product decision is whether W2 has a measurable edge in low-overround bookmaker markets before any quant-platform build begins.

```text
TOP_LEVEL_PROGRAM = W2_FOOTBALL_QUANT_EDGE_EXISTENCE
CURRENT_RESEARCH = PINNACLE_CLOSING_MAINLINE_AH_AND_OU25
ACTIVE_NEXT_ACTION = W2_PHASE_0_5_R1_D_TRAIN_AND_V_MANIFEST
```

The current task is **Phase 0.5 edge-existence testing**, not Signal Ledger, strategy, portfolio, risk, Dashboard or deployment work.

## Why Phase 0.5 comes first

The current W2 model did not show stable incremental information over Pinnacle closing 1X2 in the prior market-baseline evaluation. That result is a strong negative prior, but it does not logically settle AH or OU because the markets compress the score matrix differently.

Phase 0.5 therefore asks:

1. Does a pure-goals Dixon-Coles model improve out-of-sample prediction over Pinnacle closing probabilities for OU 2.5 or AH half-goal lines?
2. Does a market-anchored residual model improve on the market-only baseline?
3. Does a strategy frozen on PRE information produce positive fixed-unit economic results at PRE line and PRE price?
4. Is any apparent edge stable after held-out audit, clustering, multiple-testing control and concentration checks?

Only `ECONOMIC_EDGE_CANDIDATE` authorizes preparation of the full W2 Football Quant Platform design.

## Protocol state

```text
PROTOCOL = W2_PHASE_0_5_AH_OU_EDGE_EXISTENCE_PROTOCOL_V1_RC3
PROTOCOL_FROZEN = true
BINDING_ERRATUM_E1 = STAGED_OUTCOME_ACCESS_AND_HOLDOUT_EXECUTION
MODEL_EVALUATION_EXECUTION = AUTHORIZED_STAGEWISE
RESULT_ACCESS = STAGED_SPLIT_GATES
```

Machine-binding B1–B5 was reported PASS and must be recomputed before execution:

```text
B1 ARTIFACT_SHA_BINDING
B2 COVERAGE_AND_MUTUAL_EXCLUSIVITY
B3 NO_COMPETITION_SEASON_SPANS_SPLITS
B4 RELEVANT_CODE_MANIFEST_BINDING
B5 RESULT_COLUMNS_CLOSED
```

## Data universe

```text
CONFIRMATORY_SOURCE = FOOTBALL_DATA_MMZ_ONLY
SOURCE_WINDOW = 2019_20_TO_2025_26
DIVISION_COUNT = 20
DIVISION_SEASON_COUNT = 140
RAW_MMZ_ROWS = 51035
NEW_SERIES = EXCLUDED_FROM_CONFIRMATORY_SCOPE_NO_PINNACLE_AH_OU
```

Split by complete competition-season units:

```text
D = 2019_20, 2020_21, 2021_22
V = 2022_23, 2023_24
H = 2024_25, 2025_26
```

Exact outcome-blind population counts:

```text
AH_HALF_CLOSING_PREDICTIVE = 10816
AH_HALF_PRE_ECONOMIC = 10693
AH_HALF_SAME_LINE_CLV = 6479

OU25_CLOSING_PREDICTIVE = 46483
OU25_PRE_ECONOMIC = 46313
OU25_SAME_LINE_CLV = 46301

LINE_COMPARABLE_COUNT = 50958
SAME_LINE_COUNT = 31905
LINE_MOVED_COUNT = 19053
LINE_MOVED_RATE = 37.39_PERCENT
```

Held-out capacity reported from the frozen assignment:

```text
OU25_H_ELIGIBLE = 10123
AH_HALF_H_ELIGIBLE = 2437
```

These are eligible populations, not selected-order counts. Economic power must be recomputed from the actual frozen H selections.

## Market roles

```text
PRIMARY_PREDICTIVE_MARKETS = OU_2_5, AH_HALF_GOAL_LINES
PRIMARY_ECONOMIC_MARKET = OU_2_5
AH_HALF_ECONOMIC = EXPLORATORY_POWER_DEPENDENT
AH_INTEGER_AND_QUARTER = EXPLORATORY_FIVE_STATE_ONLY
CONFIRMATORY_ODDS_SOURCE = PINNACLE_ONLY
BET365_OR_AVERAGE_FALLBACK = FORBIDDEN
```

Pinnacle overround distributions measured in the inventory:

```text
AH_PRE_P50 = 2.94_PERCENT
AH_CLOSE_P50 = 2.56_PERCENT
OU25_PRE_P50 = 3.67_PERCENT
OU25_CLOSE_P50 = 3.39_PERCENT
```

Low overround lowers the hurdle; it does not prove that W2 has an edge.

## Line-movement contract

```text
LINE_MOVED_BETWEEN_PRE_AND_CLOSE:
- excluded from SAME_LINE_CLV only;
- included in PRE_ENTRY_ECONOMIC_ROI using the original PRE line and price;
- included in closing predictive evaluation using the CLOSE line;
- never deleted from economic results solely because the line moved.
```

## Models

```text
M0_PRE = PINNACLE_PRE_MARKET_ONLY
M0_CLOSE = PINNACLE_CLOSE_MARKET_ONLY

M2 = PURE_GOALS_DIXON_COLES_PER_DIVISION
RHO_GRID = -0.20_TO_+0.20_STEP_0.01_TRAIN_ONLY

M4_PRE_MODEL_ID = M4_PRE_BINARY_RESIDUAL_V1
M4_CLOSE_MODEL_ID = M4_CLOSE_BINARY_RESIDUAL_V1
M4_MODEL_FAMILY = BINARY_LOGISTIC_RESIDUAL_WITH_MARKET_LOGIT_OFFSET_AND_L2
M4_FEATURES = INTERCEPT, MODEL_MARKET_LOGIT_GAP
L2_GRID = 0.01, 0.1, 1.0, 10.0

M1_AND_M3 = SECONDARY_CROSS_SOURCE_NOT_GATING
```

M4 PRE and M4 CLOSE must be trained independently and must have separate model, training-population, feature, parameter and calibration hashes. CLOSE parameters may not select PRE orders.

## Selection and metrics

OU 2.5 economic selection is frozen as:

```text
- compute OVER and UNDER probability using M4_PRE;
- compute predicted EV from the respective PRE price;
- select only the higher predicted-EV side;
- max predicted EV below 3% => NO_SELECTION;
- exact tie => NO_SELECTION_TIE;
- one primary selection per fixture per market;
- fixed 1 unit; no Kelly and no compounding;
- no CLOSE field may be read when selecting.
```

Predictive metric convention:

```text
PREDICTIVE_LIFT = PINNACLE_MARKET_LOG_LOSS - MODEL_LOG_LOSS
positive = model better
MIN_PRACTICAL_PREDICTIVE_LIFT = 0.002_NATS_PER_FIXTURE
```

Economic threshold:

```text
MIN_PRACTICAL_PREDICTED_EV_FOR_SELECTION = 0.03
MIN_PRACTICAL_REALIZED_ROI = 0.03
```

Current `ev_se` is not a sampling standard error. In this research it is treated only as `EV_SCENARIO_SD` / lambda-sensitivity diagnostics and is forbidden as a confidence-bound statistic.

## Statistical contract

```text
PRIMARY_DEVIG_METHOD = PROPORTIONAL
DEVIG_SENSITIVITY_METHOD = POWER

BOOTSTRAP_METHOD = TWO_STAGE_COMPETITION_SEASON_AND_FIXTURE_BOOTSTRAP
BOOTSTRAP_RESAMPLES = 20000
BOOTSTRAP_SEED = 2026080601
CI = TWO_SIDED_PERCENTILE_95

PREDICTIVE_TEST_FAMILY:
P1 = OU25_M4_CLOSE_VS_M0_CLOSE
P2 = AH_HALF_M4_CLOSE_VS_M0_CLOSE
MULTIPLE_TESTING = HOLM_ALPHA_0.05

ECONOMIC_TEST:
E1 = OU25_M4_PRE_FIXED_UNIT_REALIZED_ROI
ALPHA = 0.05
```

Individual-league results, AH economics, integer/quarter lines and M1/M3 are secondary or exploratory and cannot independently trigger the final GO result.

## Staged result-access gates

```text
R0: all D/V/H result columns closed; recompute B1-B5.
R1: unlock D results for training only; V/H remain closed.
R2: freeze all V candidate predictions and PRE selections before opening V results.
R2B: open V results once; select only among pre-registered L2 candidates and apply V gate.
R3: only if V passes, refit fixed final models on D+V.
R4: freeze H predictions and H PRE selections before opening H results.
R5: open H results once; evaluate, bootstrap, Holm and issue the final verdict.
```

Evaluation modes:

```text
V_EVALUATION_MODE = STATIC_TRAIN_D_NO_V_OUTCOME_UPDATE
H_EVALUATION_MODE = STATIC_REFIT_D_PLUS_V_NO_H_OUTCOME_UPDATE
```

## Final verdicts

```text
INSUFFICIENT_EVIDENCE
NO_EDGE
PREDICTIVE_INCREMENT_ONLY
ECONOMIC_EDGE_CANDIDATE
```

Decision consequences:

- `INSUFFICIENT_EVIDENCE`: do not claim no edge; decide whether to collect more evidence under a new protocol.
- `NO_EDGE`: do not build the quant platform; keep W2 as operational analysis/data infrastructure.
- `PREDICTIVE_INCREMENT_ONLY`: only a minimal forward Signal Ledger and fixed-unit Shadow measurement may be designed; no Portfolio/Risk/Quant Dashboard.
- `ECONOMIC_EDGE_CANDIDATE`: authorize the W2 Football Quant Platform total-design document; still no real money or automated execution.

## Operational stop lines

```text
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
