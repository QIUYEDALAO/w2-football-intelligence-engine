# EV-SE drift estimation v2 — frozen protocol

Status: `FROZEN_BEFORE_ANY_V2_RESULT`. Committed before the new estimator was run
against production data. Commit order is the evidence that the method was not
tuned to its own answer.

## 1. Why v1 could not identify alpha

v1 regressed `y = (m2-m1)^2 - s1^2/k - s2^2/k` on `H(W1,W2)`. Three defects, in
descending order of damage:

1. **Noise floor.** `E[(m2-m1)^2] = 2*tau^2/k + sigma^2*H`. With five-match windows
   the constant `2*tau^2/k` dominates `sigma^2*H` by roughly an order of magnitude,
   and the variance of a squared Gaussian difference scales with the square of its
   own mean. The drift term sits inside the noise of the term used to measure it.
2. **Subtracting a noisy estimate.** `s^2` is itself estimated from `k=5` values,
   so the subtraction injects variance rather than removing it, and `s^2` contains
   within-window drift, which over-subtracts and biases `alpha` low.
3. **Information discarded.** Non-overlapping windows use about `n/5` window pairs
   per team where the series supports `C(n,2)` match pairs. v1 threw away most of
   the available leverage, and window phase (where the first window starts) is an
   arbitrary choice the estimate depends on.

v1 is retained as a comparator, not deleted.

## 2. v2 primary estimator: within-season variogram with free intercept

For each team series inside one provider season, for every match pair `i<j`:

```
d_ij     = (y_j - y_i)^2
delta_ij = t_j - t_i            (days)
E[d_ij]  = 2*tau^2 + sigma^2 * delta_ij
```

Regress `d` on `delta` **with a free intercept**. Slope is `alpha_abs`
(`xG^2/day`); intercept/2 is the single-match observation noise `tau^2`.

This fixes all three v1 defects: it uses every within-season pair, it estimates
`tau^2` jointly as the intercept instead of subtracting a noisy estimate, and it
has no window phase.

Weighting: every team carries total weight one (`w = 1/pairs_in_team`).
CI: cluster bootstrap over teams, `10,000` reps, seed `20260826`, two-sided 95%.

## 3. Power study runs before the real estimate

Synthetic series are generated on the **real timestamp geometry** of each
`league x component`, with `tau^2` on a grid and known injected `sigma^2` on
`{1e-5, 3e-5, 1e-4, 3e-4, 1e-3}`. For each cell we report bias, CI width, and
detection power (share of replications whose CI lower bound exceeds zero).

This fixes what the design can resolve *before* the real answer is visible. If
power at `sigma^2 = 1e-4` is low, a null real result is a statement about the
design, not about football, and the report must say so.

## 4. Frozen thresholds

- Support: `>= 10` teams; `>= 1,000` within-season pairs; delta span `>= 100` days.
- Delta bins: 5 weighted-quantile bins, each `>= 50` pairs and `>= 5` teams;
  `>= 4` valid bins required.
- Linearity gate: add `delta^2`; `NONLINEAR_DRIFT` if its 95% CI excludes zero
  **and** max binned relative deviation from the linear fit exceeds `20%`.
- Estimation period `kickoff < 2026-01-01`; holdout `kickoff >= 2026-01-01`
  is reserved for path C and is never read during estimation.
- Season boundary: cross-season pairs are estimated separately with an added
  jump term; provider season is the boundary authority.
- Negative slopes and boundary terms are reported as-is, never truncated.

## 5. Status vocabulary

Per `league x attack/defence`:
`USABLE`, `CI_INCLUDES_ZERO`, `NEGATIVE_SLOPE`, `INSUFFICIENT_SUPPORT`,
`NONLINEAR_DRIFT`, `BOUNDARY_NOT_IDENTIFIED`, `MISSINGNESS_PREMISE_FAILED`,
`PATH_C_MISMATCH`. Unusable cells keep their point estimate and CI with
`use=false`. No aggregate alpha or beta is emitted, and no league borrows a
value from another.

## 6. Beta, unchanged from the 2026-08-26 acceptance protocol

`E` expected PIT fixture set, `O` those with two-sided numeric xG, `u = 1-|O|/|E|`,
`D = mean_age(O) - mean_age(E)`. Fit `D ~ kappa*u` through the origin with equal
team weight, then `beta_abs = alpha_abs * kappa`. Required jointly: alpha CI
excludes zero; lower CI bounds of both `kappa` and `D` above zero; approximation
NRMSE `<= 50%`; `>= 10` teams and `>= 50` states with `u > 0`. Otherwise
`MISSINGNESS_PREMISE_FAILED`. Argentina is reported on its own and is not
presumed to fail or pass.

## 7. Form

Estimated parameters are absolute variance rates, so the dimensionally consistent
form is `SE^2 = SE0^2 + alpha_abs*A + beta_abs*(1-c)`. The existing multiplicative
form needs `alpha_rel = alpha_abs / SE0^2`, which is not a constant. The mismatch
is reported per league; the coefficients are never distorted to fit the old form.

## 8. Invariants and negative controls

Five behavioural invariants keep positive tests. `--self-test-mutants` must reject
five mutants: negative age coefficient, inverted coverage sign, constant inflation
at `A=0,c=1`, high confidence when the denominator is unavailable, and age reset at
a season switch. A single-field `1e-6` mutation of the evidence JSON must make
`--check` exit non-zero.
