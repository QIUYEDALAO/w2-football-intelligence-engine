# EV-SE drift and missing-coverage uncertainty — frozen protocol v3

Status: `FROZEN_BEFORE_ANY_V3_RESULT` for sections 3, 4 and 6. Sections 5, 7 and 8
are carried forward unchanged from the v2 protocol (commit `3fca0384`); section 7's
result was already computed under v2 before this document existed and is disclosed
as such in section 9 rather than presented as a blind result. Commit order is the
evidence for everything else.

The v2 delivery `b34eada9` is **retained as failed history** and is not amended.

## 1. What v2 got wrong

Independently reproduced before this protocol was written. Each defect is a fact
about the code or the data, not a matter of judgement.

1. **The holdout was not a holdout.** `HOLDOUT_EPOCH_DAYS = 20089` is
   `2025-01-01`, not `2026-01-01` (which is `20454`). Path C scored a full year of
   estimation-period matches as if they were held out.
2. **No point-in-time visibility anywhere in the loader.** `_load.py` never reads
   `captured_at`. In the frozen extract `captured_at` is `2026-07` for 0.5% of rows
   and `2026-08` for 99.5%; all `14,288` estimation-period rows carry
   `captured_at >= 2026-01-01`. No xG row in the extract was visible before
   `2026-07`, so nothing computed from it can claim pre-kickoff visibility.
3. **Path C measured the wrong quantity.** It scored `(actual - mean)/sqrt(SE0^2 + tau^2)`
   for one team and one component. Production forms
   `sigma_home = 0.5*sqrt(SE(home_attack)^2 + SE(away_defence)^2)` and propagates it
   through GH-3 to EV. It also reset each team's history at every provider season.
4. **The evidence carried a fraction of the protocol.** Power, linearity gate,
   season boundary, missingness/beta and the additive-vs-multiplicative comparison
   were all absent from the evidence JSON.
5. **The mutants tested a toy.** `se_formula` in the runner is a standalone
   function with no connection to `_empirical_xg_lambda_uncertainty` or
   `ah_expected_value_uncertainty_from_lambdas`. The suite proved the test could
   fail, never that production was right.

A sixth point is a claim, not a defect: v2's section 2 said the estimator "uses
every within-season pair", which invites the reading that `C(n,2)` pairs carry
`C(n,2)` worth of information. They do not — `n` observations carry `O(n)`
independent information. The team-clustered bootstrap kept the *intervals* honest,
so v2's CIs are not inflated. What was never established is **efficiency**: the
variogram is a method-of-moments estimator, and v2's "8% power" is a statement
about that estimator, not about the data. Section 3 replaces it with the efficient
one and section 4 measures the difference.

## 2. Question this protocol must answer

Not "what are alpha and beta". The deliverable is an auditable verdict on whether
the available point-in-time data can identify staleness and missing-coverage
uncertainty at all, and whether either belongs in production. `NOT_IDENTIFIABLE`
with a named list of missing inputs is a valid and complete answer. A holdout that
leaks is not.

## 3. Primary estimator: exact Gaussian likelihood for the local level model

Per team series inside one provider season, observations `y_1..y_n` at times
`t_1..t_n` for one `league x component`:

```
theta_k = theta_{k-1} + eta_k     eta_k ~ N(0, sigma^2 * (t_k - t_{k-1}))
y_k     = theta_k     + eps_k     eps_k ~ N(0, tau^2)
```

`sigma^2` is the drift variance rate in `xG^2/day` and is the same `alpha_abs` the
earlier generations estimated; `tau^2` is single-match observation noise.

**Likelihood.** Exact, by Kalman filter, with diffuse initialisation on `theta_1`.
The diffuse start is implemented in its closed form — `a_1 = y_1`, `P_1 = tau^2`,
and the likelihood accumulates from `k = 2` — so the team's level is profiled out
rather than given a prior. Series with `n < 3` contribute nothing. Team-season
series are independent, so the cell log-likelihood is their sum.

**Optimisation.** Nelder-Mead over `(log tau^2, log sigma^2)`, implemented in the
repository with no third-party dependency so the fit is bit-reproducible. Start
`tau^2` at the series' pooled variance and `sigma^2` at `1e-4`; simplex step `0.5`
in log space; convergence at `1e-10` relative on the objective or 2,000 iterations.
`sigma^2 = 0` is approached as `log sigma^2 -> -inf` and is handled by evaluating
the restricted model directly rather than by a bound.

**Test.** `sigma^2 = 0` is on the boundary of the parameter space, so the null
distribution of the likelihood-ratio statistic is the `50:50` mixture of a point
mass at zero and `chi^2_1`, not `chi^2_1`. Detection means
`LRT p < 0.05` one-sided under that mixture. Reporting a `chi^2_1` p-value here
would roughly double the false-positive rate.

**Interval.** Profile-likelihood interval for `sigma^2` at 95%, using the same
boundary-corrected calibration. A cluster bootstrap over teams with `200` reps at
seed `20260826` is reported beside it as a robustness check, not as the primary
interval; `10,000` reps of a full MLE is not affordable and a smaller bootstrap is
stated rather than disguised.

**Comparator.** The v2 variogram is retained and reported for every cell. v1 is
retained as before. Neither is deleted, and no cell may take its status from
whichever estimator is more agreeable.

## 4. Power and size, before any real estimate

Synthetic series on the **real timestamp geometry** of each cell, `tau^2` from that
cell's own fit, and injected `sigma^2` on `{0, 1e-5, 3e-5, 1e-4, 3e-4, 1e-3}`.
`500` replications per point, seed `20260826`.

`sigma^2 = 0` is on the grid deliberately: it measures the **size** of the test.
If the null rejection rate is materially above `0.05` the power numbers are void
and the cell is reported as `TEST_MISCALIBRATED`. Power without a size check is
not evidence.

Both estimators are run on **identical** synthetic replicates so the comparison is
paired. The report must state the drift rate that moves `SE` by 10% over 60 days
for that cell, and the power both estimators have at it.

## 5. Frozen thresholds, carried forward from v2 section 4

Support `>= 10` teams, `>= 1,000` within-season pairs, delta span `>= 100` days.
Five weighted-quantile delta bins, each `>= 50` pairs and `>= 5` teams, `>= 4`
valid bins. Linearity gate: add `delta^2`; `NONLINEAR_DRIFT` when its 95% CI
excludes zero **and** the worst binned relative deviation from the linear fit
exceeds `20%`. Cross-season pairs estimated separately with an added jump term,
provider season being the boundary authority. Negative slopes and boundary terms
are reported as-is, never truncated.

The v2 sentence "max binned relative deviation from the linear fit" does not fix a
denominator, and with a free intercept the choice changes the number. Both
conventions — binned mean against the fitted line, and the v1 convention of
quadratic prediction against linear prediction — are computed and emitted for
every cell. The first is the gate. Fixing this ambiguity in writing, before the
numbers are read, is the point.

## 6. Path C, rebuilt

Path C scores the quantity production actually ships:

1. `lambda_home` and `lambda_away` for a real fixture, built only from information
   visible before that fixture's kickoff;
2. `sigma_home = 0.5*sqrt(SE(home_attack)^2 + SE(away_defence)^2)` and its away
   counterpart, taken from the production code path rather than reimplemented;
3. the full variance propagation through to EV as production performs it;
4. calibration of the realised outcome against that predicted distribution,
   stratified by observation age and by coverage — the two strata the candidate
   formula claims to fix.

Team history is **not** reset at a provider season boundary; the boundary enters
through the jump term of section 5, not by discarding the past.

**Admissibility.** A row may enter Path C only if the xG it uses carries a
first-visibility timestamp at or before the target fixture's kickoff. `captured_at`
on `team_xg_match` does not qualify: the column is overwritten on upsert and its
current values record the 2026-08 backfill.
`team_xg_rolling_snapshot` does not qualify either: it is written through
`session.merge` on a derived key and is rebuilt from `team_xg_match`.

If no admissible source exists, Path C is reported `PATH_C_NOT_IDENTIFIABLE`
together with the exact record that would make it identifiable. Substituting a
leaky holdout, or weakening admissibility until rows qualify, is prohibited.

## 7. Beta, carried forward from v2 section 6, unchanged

`E` expected PIT fixture set, `O` those with two-sided numeric xG, `u = 1-|O|/|E|`,
`D = mean_age(O) - mean_age(E)`. Fit `D ~ kappa*u` through the origin with equal
team weight, then `beta_abs = alpha_abs * kappa`. Required jointly: alpha's
interval excludes zero; lower bounds of both `kappa` and mean `D` above zero;
approximation NRMSE `<= 50%`; `>= 10` teams and `>= 50` states with `u > 0`.
Otherwise `MISSINGNESS_PREMISE_FAILED`. Argentina is reported on its own and is
presumed neither to pass nor to fail.

## 8. Form, carried forward from v2 section 7, unchanged

Estimated parameters are absolute variance rates, so the consistent form is
`SE^2 = SE0^2 + alpha_abs*A + beta_abs*(1-c)`. The multiplicative form in place
needs `alpha_rel = alpha_abs / SE0^2`, which is not a constant. The mismatch is
reported per league and the coefficients are never distorted to fit the old form.

## 9. Disclosure

The section 7 computation was run under the v2 protocol before this document was
written, and its result is therefore already known to the author. It is carried
forward verbatim and reported as-is; the freeze-before-result claim in this
document covers sections 3, 4 and 6 only. Saying which parts of a protocol were
frozen blind is worth more than claiming all of it was.

## 10. Behavioural tests and mutants, bound to production

The five behavioural invariants keep positive tests, and the mutant suite must
reject five mutants: negative age coefficient, inverted coverage sign, constant
inflation at `A=0,c=1`, high confidence when the denominator is unavailable, and
age reset at a season switch.

Both now execute against the **real** EV-SE path —
`_empirical_xg_lambda_uncertainty` for sigma and
`ah_expected_value_uncertainty_from_lambdas` for propagation — with each mutant
applied to that path rather than to a local copy of the formula. A mutant that
cannot be expressed against production code is evidence that production has no
such behaviour to break, and is reported that way instead of being simulated.

Invariant 1 as originally worded only forbids an increase in age from lowering
`SE`, which a formula ignoring age entirely satisfies. The supplementary
strict-increase check found in v2 is retained.

A single-field `1e-6` mutation of any numeric field in the evidence JSON must make
`--check` exit non-zero, demonstrated by a self-test that performs the mutation
rather than by assertion.

## 11. Required deliverables

- a clause-by-clause status matrix of this protocol against what was implemented;
- reproducible power, alpha, boundary, missingness/beta and form comparison;
- a Path C that uses only pre-kickoff-visible information, or `PATH_C_NOT_IDENTIFIABLE`
  with the missing record named;
- age- and coverage-stratified calibration of the baseline and candidate formulas;
- behavioural tests and mutants bound to the production path;
- report, frozen evidence JSON, reproduction commands and input provenance;
- an explicit recommendation on continuing SE, pausing it, or moving to point EV,
  with the evidence boundary stated.

## 12. Standing constraints

Settled profit, hit rate and the current 65 picks may not select or reject any
parameter. Staleness thresholds and EV caps may not be picked from backtests.
Provider calls 0, production writes 0, GitHub 0, no deployment; production reads
only under `BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY`.
