# W2 Market Movement Features V1

Market movement features are forward-only and calibration-gated.

## Enabled Semantics

Movement features are computed only from `CAPTURED_AT` snapshots.

## Disabled Semantics

`UNKNOWN_PREMATCH_AGGREGATE` and `CLOSING` rows must not be used for phase movement backtests.

## Feature Families

- first seen to current price move
- recent move
- velocity and acceleration
- main-line change
- bookmaker coherence
- dispersion change
- 1X2, AH, and OU cross-market consistency
- lineup-before and lineup-after hook

All thresholds remain `CALIBRATION_REQUIRED` and are reported as `WARN_ONLY` until real calibration
data exists.
