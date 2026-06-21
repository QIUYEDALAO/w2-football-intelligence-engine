# W2 Calibration Policy V1

Stage 7 compares calibration methods without test leakage.

## Methods

- Platt
- Isotonic
- Beta
- Dirichlet multiclass

## Selection

Calibration methods are fit and selected on validation data. Test data is evaluated once after
selection. Reports include before and after metrics, reliability bins, and ECE.

Calibration cannot be used to close Gate 4 if it worsens held-out performance materially.
