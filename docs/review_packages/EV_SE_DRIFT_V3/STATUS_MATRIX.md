# v3 protocol — clause-by-clause status matrix

Protocol `603a9753`. Evidence `EV_SE_DRIFT_V3_EVIDENCE.json`. Every `DONE` row
names the artefact that carries it, so the claim can be checked rather than taken.

Legend: **DONE** implemented and in evidence · **BLOCKED** cannot be done with the
data that exists, with the reason recorded · **PARTIAL** implemented with a stated
deviation.

## Section 1 — v2 defects independently reproduced

| Clause | Status | Where |
|---|---|---|
| Holdout constant was 2025-01-01, not 2026-01-01 | DONE | protocol §1.1; `20089` vs `20454` |
| Loader never read `captured_at`; 99.5% captured 2026-08 | DONE | `path_c.rows_captured_before_2026_07 = 0` |
| Path C scored a single team's xG mean, reset per season | DONE | protocol §1.3 |
| Evidence carried a fraction of the protocol | DONE | this matrix is the remedy |
| Mutants tested a local copy of the formula | DONE | `ev_se_v3_production_tests.py` binds to production |
| "Every pair" implies `C(n,2)` information — refuted claim | DONE | protocol §1, closing paragraph |

## Section 3 — primary estimator

| Clause | Status | Where |
|---|---|---|
| Local level model, exact Gaussian likelihood | DONE | `ev_se_mle.loglik` |
| Kalman filter with closed-form diffuse level | DONE | `a_1 = y_1`, `P_1 = tau^2`, accumulate from `k=2` |
| Series with `n < 3` contribute nothing | DONE | `loglik` early return |
| Cell likelihood is the sum over independent team-season series | DONE | `cell_loglik` |
| Nelder-Mead, no third-party dependency | DONE | `_nelder_mead`, pure stdlib |
| Start `tau^2` at pooled variance, `sigma^2` at 1e-4 | DONE | `fit_full` |
| Simplex step 0.5 in log space; tol 1e-10; 2,000 iterations | DONE | `_nelder_mead` defaults |
| `sigma^2 = 0` evaluated directly, not as a bound | DONE | `fit_restricted`, compared in `fit_full` |
| One-sided LRT under the 50:50 boundary mixture | DONE | `lrt_pvalue`; `0.5*erfc(sqrt(LR/2))` |
| Profile interval at the same critical value | DONE | `profile_interval`, `LRT_CRITICAL_95 = 2.7055` |
| Cluster bootstrap, 200 reps, seed 20260826, reported beside | DONE | `cluster_bootstrap_ci_200reps` in every cell |
| v2 variogram retained as comparator | DONE | `variogram_comparator` in every cell |
| v1 retained | DONE | `scripts/ev_se_drift_alpha.py`, unmodified |
| No cell takes its status from the friendlier estimator | DONE | status derives from the MLE only |

## Section 4 — power and size

| Clause | Status | Where |
|---|---|---|
| Real timestamp geometry per cell | DONE | `ev_se_v3_power.cell_series` |
| `tau^2` from that cell's own fit | DONE | `fit_full` on the real series |
| Grid `{0, 1e-5, 3e-5, 1e-4, 3e-4, 1e-3}`, 500 reps, seed 20260826 | DONE | `SIGMA2_GRID`, `REPLICATIONS` |
| `sigma^2 = 0` on the grid to measure size | DONE | `mle_size_at_null` per cell |
| Both estimators on identical replicates | DONE | one `draw` feeds both |
| `TEST_MISCALIBRATED` when size runs high | DONE | status field per cell |
| Rate that moves SE 10% over 60 days, and power at it | DONE | report §4 |

## Section 5 — frozen thresholds

| Clause | Status | Where |
|---|---|---|
| Support: ≥10 teams, ≥1,000 pairs, span ≥100 days | DONE | `estimate`, `INSUFFICIENT_SUPPORT` |
| Five weighted-quantile bins, ≥50 pairs and ≥5 teams each, ≥4 valid | DONE | `weighted_quantile_bins`, `bins_sufficient` |
| Linearity gate: `delta^2` CI excludes zero AND worst binned deviation >20% | DONE | `linearity_gate` |
| Both relative-deviation conventions emitted | DONE | `max_rel_dev_observed`, `max_rel_dev_quadratic` |
| Cross-season pairs estimated separately with a jump term | DONE | `season_boundary`, all 26 `IDENTIFIED` |
| Negative slopes and boundary terms reported as-is | DONE | negative values present and untruncated |

## Section 6 — Path C

| Clause | Status | Where |
|---|---|---|
| `lambda_home`/`lambda_away` from pre-kickoff information only | BLOCKED | no admissible xG history exists |
| Sigma pair from the production code path | DONE | production path exercised in the test suite |
| Full variance propagation through to EV | DONE | `ah_expected_value_uncertainty_from_lambdas` exercised |
| Calibration stratified by age and coverage | PARTIAL | in-sample only; `EV_SE_DRIFT_V3_CALIBRATION.json` |
| History not reset at a provider season boundary | DONE | boundary enters through the jump term |
| Admissibility: first-visibility at or before kickoff | DONE | `path_c.columns_examined_and_rejected` |
| `PATH_C_NOT_IDENTIFIABLE` with the missing record named | DONE | `path_c.record_that_would_make_it_identifiable` |

The blocked row is the protocol working. `captured_at` is upsert-overwritten and
`team_xg_rolling_snapshot` is merged from it, so neither records first visibility;
0 of 18,978 rows are visible before 2026-07. The stratified calibration is
therefore in-sample and labelled `IN_SAMPLE_ESTIMATION_PERIOD` in its own file.
Its baseline column needs no fitted coefficient, so that column is still a fact
about prediction error rather than a circular one.

## Section 7 — beta

| Clause | Status | Where |
|---|---|---|
| `u`, `D`, through-origin `kappa`, equal team weight | DONE | `ev_se_beta_kappa` |
| Four premises evaluated jointly | DONE | `premises` per league |
| `MISSINGNESS_PREMISE_FAILED` when they do not hold | DONE | all 13 leagues fail |
| Argentina reported on its own | DONE | own row, no special-casing |

## Section 8 — form

| Clause | Status | Where |
|---|---|---|
| `alpha_rel = alpha_abs / SE0^2` reported per league | DONE | `form_mismatch` |
| Coefficients never distorted to fit the multiplicative form | DONE | only absolute rates are emitted |

## Section 10 — behavioural tests and mutants

| Clause | Status | Where |
|---|---|---|
| Five invariants keep positive tests | DONE | `positive_invariants: PASS` |
| Five mutants rejected | DONE | `mutants_survived: []` |
| Bound to `_empirical_xg_lambda_uncertainty` | DONE | `bound_to` field |
| Bound to `ah_expected_value_uncertainty_from_lambdas` | DONE | monotonicity re-checked after propagation |
| Mutant inexpressible against production is reported, not simulated | DONE | production's own verdict recorded separately |
| Supplementary strict-increase check retained | DONE | `age_term_inert` |
| 1e-6 mutation makes `--check` exit non-zero, by self-test | DONE | `--self-test-check`, 41 of 1,165 fields sampled |

## Section 11 — deliverables

| Deliverable | Status |
|---|---|
| Clause-by-clause status matrix | DONE — this file |
| Reproducible power, alpha, boundary, missingness, form | DONE |
| Path C or a rigorous `NOT_IDENTIFIABLE` | DONE — `NOT_IDENTIFIABLE`, record named |
| Age/coverage stratified calibration of baseline and candidate | PARTIAL — in-sample, labelled |
| Behavioural tests and mutants on the production path | DONE |
| Report, evidence JSON, reproduction commands, provenance | DONE |
| Recommendation with the evidence boundary stated | DONE — report §7 |

## Section 12 — constraints

| Constraint | Status |
|---|---|
| No settled profit, hit rate or the 65 picks | HELD — no outcome table read anywhere |
| No threshold picked from backtests | HELD — no backtest run |
| Provider calls 0 | HELD |
| Production writes 0 | HELD |
| GitHub 0 | HELD |
| No deployment | HELD |
| Production reads only under repeatable-read read-only | HELD — no production read was made; every input is a frozen local artefact |

## Known deviations

1. **Cluster bootstrap at 200 reps, not 10,000.** Fixed in the protocol before the
   run and reported beside the profile interval, which is primary. Ten thousand
   replications of a two-parameter MLE across 26 cells is not affordable.
2. **`--self-test-check` samples 41 of 1,165 numeric fields.** Every sampled
   mutation was detected. The sampling is deterministic (`paths[::step]`), so the
   set is reproducible rather than random.
3. **Stratified calibration is in-sample.** Forced by the Path C block, labelled in
   the artefact, and the coefficient-free baseline column is called out separately.
4. **`raw_payload_sha256` is a placeholder in the behavioural harness.** The frozen
   extract selected seven columns and did not include it. A valid placeholder makes
   production *more* permissive, so any blocked verdict stays conservative.
