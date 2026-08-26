# EV-SE staleness and missing-coverage uncertainty — v3 findings

Protocol `603a9753`, frozen before sections 3, 4 and 6 were run. Evidence
`EV_SE_DRIFT_V3_EVIDENCE.json`. Clause-by-clause status in `STATUS_MATRIX.md`.
v2 (`b34eada9`) is retained as failed history and was not amended.

## 1. The question

Not "what are alpha and beta". Whether the point-in-time data that exists can
identify staleness and missing-coverage uncertainty at all, and whether either
belongs in production. `NOT_IDENTIFIABLE` with the missing inputs named is a
complete answer; a holdout that leaks is not.

## 2. Why the estimator changed

v2 regressed squared differences of within-season match pairs on their time gap.
That is a method-of-moments estimator for the local level model. It is consistent,
and because its interval came from a bootstrap clustered on teams, that interval
was honest — `C(n,2)` pairs from `n` observations do not inflate it.

What was never established is efficiency. v2's headline — 8% power at the drift
rate that matters — is a property of the moment estimator, not of the data. The
efficient estimator under the same model is the exact Gaussian likelihood, so the
question deserved to be asked again with it.

`sigma^2 = 0` sits on the boundary of the parameter space, so the likelihood-ratio
statistic is not `chi^2_1` under the null. It is the 50:50 mixture of a point mass
at zero and `chi^2_1`. Using `chi^2_1` would roughly double the false-positive
rate; the mixture is what section 3 fixes and what `lrt_pvalue` applies.

## 3. The efficient estimator is two to three times more powerful

500 replications, seed `20260826`, both estimators on identical replicates,
`20 teams x 45 matches / 300 days`, `tau^2 = 0.5`:

| injected `sigma^2` | MLE (boundary LRT) | variogram |
|---|---|---|
| **0** | **0.050** | 0.030 |
| 1e-5 | 0.056 | 0.030 |
| 3e-5 | 0.084 | 0.034 |
| 1e-4 | 0.172 | 0.068 |
| 3e-4 | 0.632 | 0.182 |
| 1e-3 | 0.998 | 0.712 |

The first row is the one that licenses the rest. The MLE's null rejection rate is
0.050 against a nominal 0.05, so the boundary correction is doing its job. The
variogram sits at 0.030 — conservative, which is why it also finds less.

So the criticism was right and it does not rescue the coefficient. The rate that
moves `SE` by 10% over 60 days is `alpha ≈ 1e-4` at the measured median
`SE0^2 ≈ 0.027`. Even the efficient estimator detects that 17% of the time on a
favourable geometry, and on real geometry it is worse: `allsvenskan|attack` gives
8.8%, `argentina_primera|attack` 13.2%. Per-cell results are in
`EV_SE_DRIFT_V3_POWER.json`.

## 4. What the real data says

26 cells. 22 detect nothing; 12 of those return `sigma^2 = 0` exactly, the
boundary solution. Four reject uncorrected. Under 26 one-sided tests the null
expects 1.3, so multiplicity is not optional:

| cell | `sigma^2` | p | profile CI |
|---|---|---|---|
| `primeira_liga\|attack` | 7.74e-04 | 0.0001 | [3.40e-04, 1.46e-03] |
| `allsvenskan\|attack` | 8.40e-04 | 0.0014 | [3.04e-04, 1.67e-03] |
| `allsvenskan\|defence` | 5.48e-04 | 0.0101 | [1.30e-04, 1.19e-03] |
| `serie_a\|defence` | 3.26e-04 | 0.0261 | [3.83e-05, 7.96e-04] |

Bonferroni and Benjamini-Hochberg agree and keep the same two:
`primeira_liga|attack` and `allsvenskan|attack`.

Their drift rates sit near `8e-4` — about eight times the rate that would move
`SE` 10% over 60 days, and squarely in the region where the test has power. That
is the shape of the result: **the data identifies drift when drift is large, and
says nothing at the size that would matter for a modest correction.** This is a
sharper statement than v2's flat "not identifiable", and it is the correct one.

Every cell passes the linearity gate. Both relative-deviation conventions are
emitted, and the verdict is the same under either.

## 5. The two survivors are not a calendar artefact

The local level model carries neither home advantage nor opponent quality, and
both can imitate drift when the schedule is not randomly ordered. Removing both as
fixed effects makes the signal *stronger*, not weaker:

| cell | raw p | + home/away | + opponent |
|---|---|---|---|
| `primeira_liga\|attack` | 0.0001 | 0.0000 | 0.0000 |
| `allsvenskan\|attack` | 0.0014 | 0.0009 | 0.0006 |
| `allsvenskan\|defence` | 0.0101 | 0.0065 | 0.0020 |
| `serie_a\|defence` | 0.0261 | 0.0180 | 0.0012 |

So where drift is detected it is about the team. This check was added after the
primary estimates were read and is labelled as supplementary in the evidence; it
changes no frozen number.

## 6. Why it still should not ship

Four independent reasons, in descending order of force.

**The correction is smaller than production would notice.** In real evaluation
states the mean age of a latest-20 window varies by only 6 to 28 days between its
10th and 90th percentile, because the window's calendar span is nearly constant.
Feeding each cell its own `alpha` — including the two confound-robust ones — the
age term moves `SE` by at most **7.9%** across that range, by 0% in 12 of 26
cells, and by 2–4% in the median cell. The coefficient is uncertain by a factor of
five where it is measurable at all.

**Prediction error does not actually grow with age.** This one needs no fitted
coefficient. For each evaluation state, `z = (y_next - mean(window)) /
sqrt(SE0^2 + tau^2)`, stratified into age quartiles. If staleness bites, `var(z)`
rises with window age. It rises in **11 of 26 cells and falls in 15** — a coin
flip. `primeira_liga|attack`, the strongest drift detection in the study, is one
of the cells where it *falls*. The two facts are consistent: over a 13-day spread
in age, that cell's own `alpha` predicts a 1.7% change in variance, far below what
this test can resolve. Both readings say the same thing — the age range production
actually sees is too narrow for the term to earn its place.

**Beta's premise is false in direction.** `kappa` is negative in all 13 leagues
with intervals entirely below zero, and stays negative when restricted to the era
the xG feed covers. Missing coverage does not age a team's observations; it
slightly freshens them, because what goes missing sits further back in the window.
Support is sufficient, so this is not a sample-size problem — the model is simply
backwards. `beta_abs = alpha_abs * kappa` would be negative, meaning less coverage
implies less uncertainty, which the coverage-monotonicity invariant rejects
outright.

**Nothing can be validated out of sample.** See section 7.

## 7. Path C is not identifiable, and the missing record is small

`team_xg_match.captured_at` is overwritten on upsert and its current values record
the 2026-08 backfill. `team_xg_rolling_snapshot` is merged on a derived key and
rebuilt from that same table. Neither records first visibility, and **0 of 18,978
rows carry a capture time before 2026-07**. No holdout fixture after 2026-01-01
has admissible history, so Path C returns `PATH_C_NOT_IDENTIFIABLE`.

Two things this is *not*. It is not a production defect:
`ReadModelService._xg_uncertainty_rows` drops rows with `captured_at > as_of`, so
the shipped read model fails closed rather than reading the future. The defect was
in the v2 research loader, which never read the column at all. And it is not
permanent: fixture existence already has an append-only point-in-time history in
`ExpectedMatchFixtureObservationModel.source_inserted_at`. The missing record is
the same thing for xG values — an append-only observation log. Adding it changes
nothing retroactively, but it makes the question answerable in six to twelve
months instead of never.

## 8. What production does today

The behavioural suite runs through the shipped chain —
`ReadModelService._empirical_xg_lambda_uncertainty` for sigma and
`ah_expected_value_uncertainty_from_lambdas` for propagation. All five mutants die
against it and the positive invariants pass.

The finding is in the baseline row. Production **passes all five preregistered
invariants while being completely blind to observation age**: a one-day-old and a
four-hundred-day-old observation set produce byte-identical sigma (0.076399) and
byte-identical `EV_SE` (0.028653). Invariant 1 only forbids age from *lowering*
`SE`, so a formula that ignores age entirely satisfies it. That is the defect this
work was chartered to find, and it is now demonstrated against production code
rather than against a copy of the formula. The supplementary strict-increase check
(`age_term_inert`) is what catches it.

Production also fails closed below three observations, as required.

## 9. Form

The estimated parameters are absolute variance rates, so the consistent form is
`SE^2 = SE0^2 + alpha_abs*A + beta_abs*(1-c)`. The multiplicative form in place
needs `alpha_rel = alpha_abs / SE0^2` to be constant. Measured `SE0^2` spreads by
a factor of **2.6 to 4.6** between the 10th and 90th percentile *within a single
league*, so `alpha_rel` varies by the same factor across states. It is not a
constant and the coefficients were not distorted to pretend otherwise.

## 10. Season boundary

All 26 cells identify a jump term. Four have intervals excluding zero and three of
those are **negative**, which a season break adding variance cannot explain. The
consistent reading is that strength is mean-reverting rather than a pure random
walk: over long gaps the random walk over-predicts dispersion, and the jump term
absorbs the excess. Within-season lags are short enough that the linearity gate
still passes everywhere. Four of 26 against 1.3 expected is suggestive, not
established, and it is reported as such. It matters for one reason: a linear-in-age
inflation would over-inflate at large `A`, which is the regime an age term would
be introduced to serve.

## 11. Recommendation

**Pause the SE staleness direction. Do not ship `alpha` or `beta`. Unblock
Contract 1 to proceed with both coefficients explicitly unset.**

The reasoning is not "there is no drift" — two cells carry real, confound-robust
drift, and that statement is now backed by the estimator with the best claim to
finding it. It is that the correction is smaller than its own uncertainty and
smaller than production would notice, its companion coefficient has a false
premise, and no out-of-sample check exists to catch either being wrong.

Concretely:

1. **Ship Contract 1 with `alpha_age_per_day = 0` and `beta_missing = 0`,
   recorded as unidentifiable rather than as zero.** Contract 1 was blocked only on
   these being empty. This study says they should stay empty, which unblocks it on
   its own merits. The distinction matters for anyone reading it later: the data
   cannot resolve these effects, which is not the same as their being absent.
2. **Add the append-only xG observation log.** It is the one missing record, it
   costs little, and it converts a permanently unanswerable question into one
   answerable in a season. Without it this study cannot be improved by waiting.
3. **Keep the supplementary strict-increase invariant in the suite.** It is the
   only check that catches an age-blind formula, and production is age-blind today.
4. **Do not reopen the coefficient on more data alone.** The binding constraint is
   the narrow range of `A` that production actually sees, not the sample size. More
   seasons will not widen it.

**On point EV.** This evidence says nothing about it. The SE question is not being
closed because point EV has problems; it is being paused because a specific
measurement cannot be made with the records that exist, and the record needed is
named. Those are different claims and should not be traded against each other.

### Evidence boundary

This study used historical xG and the frozen Gate-1 corpus only. It read no
settled outcome, profit, hit rate, or the current 65 picks; it selected no
threshold from a backtest; it made no Provider call, no production write, no
GitHub access and no deployment. No production read was performed at all — every
input is a frozen local artefact.

What it therefore cannot tell you: whether the shipped `SE0` is well calibrated
out of sample (Path C is blocked), whether drift matters for leagues outside the
13 in the corpus, and whether the two detected cells generalise beyond the seasons
observed. The in-sample calibration in `EV_SE_DRIFT_V3_CALIBRATION.json` is
labelled in-sample and its candidate column is circular by construction; only its
baseline column is coefficient-free.

## 12. Reproduction

The frozen xG extract is not in the repository. Its SHA-256 is
`84ef81e90377014cb9ea9abc93276aebed65e1c63b9d4e5dfa18d47443634909`, 18,978 data
rows, kickoff range 2024-02-22 to 2026-08-25, held at
`/Users/liudehua/.hermes/data/ev_se_drift_v2/team_xg_match.csv`. The corpus SHA-256
is `80e49d1a32b5dd9653d41826e87415acff0d32a6804dea408f3b99737a6ab5e2`. Both
fingerprints are checked into the evidence `inputs` block.

```bash
cd /Users/liudehua/.hermes/worktrees/w2-ev-se-variogram
export W2_XG_CSV=/Users/liudehua/.hermes/data/ev_se_drift_v2/team_xg_match.csv

python3 scripts/run_ev_se_drift_v3.py --check            # expects {"reproduction": "PASS"}
python3 scripts/run_ev_se_drift_v3.py --self-test-check   # proves --check fails on 1e-6
python3 scripts/ev_se_v3_calibration.py                   # stratified calibration
python3 scripts/ev_se_v3_power.py                         # per-cell power, ~2.5 hours
```

The behavioural suite needs the project dependencies, so it runs under a project
virtualenv rather than the bare interpreter:

```bash
PYTHONPATH=src /Users/liudehua/.hermes/worktrees/w2-ev-se-offline-validation/.venv/bin/python scripts/ev_se_v3_production_tests.py
```

v2's evidence still reproduces under its own runner, which is how it stays
auditable as failed history:

```bash
python3 scripts/run_ev_se_drift_v2.py --check
```
