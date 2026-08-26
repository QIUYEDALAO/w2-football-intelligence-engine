# EV-SE staleness and missing coverage — v4 findings

Protocol `18f812b7`, frozen before any v4 result. Evidence
`EV_SE_DRIFT_V4_EVIDENCE.json`. Clause-by-clause state in `STATUS_MATRIX.md`. Per-cell power in `EV_SE_DRIFT_V4_POWER.json`.
v2 (`b34eada9`) and v3 (`e429bd97`) are retained unmodified as failed history; their
evidence files were not touched.

## 1. What this answers

Whether the point-in-time data that exists can identify staleness and
missing-coverage uncertainty, and whether either belongs in production.
`NOT_IDENTIFIABLE` with the missing input named is a complete answer. This report
reaches that verdict for two of the three questions and a qualified one for the
third.

## 2. Corrections to v3

Two of v3's statements were wrong, not merely unfinished. Both are corrected here
and in the protocol, and both changed a conclusion.

**The chi-square direction was backwards.** With `sigma^2 = 0` on the boundary the
null distribution of the likelihood-ratio statistic is `0.5*delta_0 + 0.5*chi^2_1`,
so the mixture p-value is `0.5*P(chi^2_1 > LR)`. A naive `chi^2_1` p-value is
exactly **twice** that, rejects **less** often, and runs the test at about **half**
its nominal size. The naive test is conservative. v3 said it would "roughly double
the false-positive rate", which is the opposite.

**The write semantics were described backwards.** `upsert_team_xg_matches` is
first-write-wins behind an immutability guard: an existing row is compared field by
field and any difference raises `TEAM_XG_MATCH_IMMUTABLE_CONFLICT`, otherwise the
write is skipped. `captured_at` is never overwritten by ordinary ingestion. One
controlled path, `XgRetentionService.repair_derived_lineage`, can rewrite it; it
requires `write_db=true` plus a backup, and `_guarded_timestamp_updates` raises on
any non-timestamp drift. v3 called the column unreliable and built its Path C
reasoning on that. The column is close to a first-write record. The reason a replay
finds nothing is different, and is in section 8.

Three further corrections of fact: the impact figure is **7.88% maximum and 1.54%
median with 11 of 26 cells at zero** (v3 said "at most 7.9%, 0% in 12, median 2–4%"
from an uncommitted heredoc); the self-test covers **1,217** numeric fields, not
1,165; and the head of the v3 chain was `e429bd97`, not `9222ee8c`.

## 3. Inference semantics, stated rather than implied

v3 reported one interval per cell, built at the boundary critical value `2.7055`,
and called it a 95% CI. That is the set the one-sided boundary test does not
reject — it is not a two-sided 95% confidence interval for a cell whose optimum is
interior. Each cell now carries three intervals, each with its meaning in the file:

| interval | construction | what it means |
|---|---|---|
| `boundary_region_95` | `2*(ll_max - ll_profile) <= 2.7055` | the set the one-sided boundary LRT does not reject at 5%; excludes zero exactly when the test rejects |
| `profile_ci_95` | same at `3.8415` | conventional two-sided 95% profile interval; correct at an interior optimum, conservative at the boundary |
| `cluster_bootstrap_200reps` | percentile, resampled on **teams** | robustness check, never primary; 200 replications because 10,000 two-parameter MLEs across 26 cells is not affordable |

The bootstrap unit also changed. v3 resampled the flat list of team-season series,
which splits one team across units, treats correlated series as independent and
returns an interval that is too narrow. The unit is now the team.

**The choice matters for the weaker cells.** `serie_a|defence` excludes zero under
the boundary region and **includes** it under the conventional profile interval.
`allsvenskan|defence` excludes zero under both likelihood intervals and **includes**
it under the corrected team bootstrap. v3's single interval overstated both.

## 4. Power on real geometry: the size check first

`EV_SE_DRIFT_V4_POWER.json`, 26 cells x 6 injected rates x 500 replications, seed
`20260826`, both estimators on identical replicates.

The null row comes first because power quoted without it is not evidence. The MLE's
rejection rate at `sigma^2 = 0` runs from **0.028 to 0.060** across the 26 cells
against a nominal 0.05, and no cell is flagged `TEST_MISCALIBRATED`. The boundary
mixture is doing its job on real geometry, not just on the synthetic design. The
variogram sits at 0.020–0.036, well under nominal — conservative, which is the same
thing that costs it power below.

With size established, the power:

| injected `sigma^2` | MLE, across cells | variogram |
|---|---|---|
| 0 (size) | 0.028 – 0.060 | 0.020 – 0.036 |
| **1e-4** | min 0.078, **median 0.128**, max 0.206 | median 0.042 |
| 3e-4 | min 0.220, median 0.446, max 0.730 | — |
| 1e-3 | 0.788 – 1.000 | — |

`1e-4` is the rate that would move `SE` about 10% over 60 days at the measured
median `SE0^2`. **No cell reaches 80% power there — 0 of 26.** The median is 12.8%,
lower than the 17.2% the favourable synthetic design gave, because real series are
shorter and less evenly spaced than `20 x 45 / 300 days`.

The efficient estimator is worth roughly **2.9x** the variogram's power at that rate
(median ratio across cells), which is why v3's "8%" described the moment estimator
rather than the data. It is also why the answer does not change: tripling the power
of a test that had 4% leaves it far short of 80%.

These three populations are kept separate throughout and never averaged:
`representative_geometry` (the synthetic design, in `EV_SE_DRIFT_V4_IMPACT.json`),
`real_cell_geometry` (this table), and `production_states` (section 7).

## 5. What the data says

26 cells. 22 detect nothing and 11 return `sigma^2 = 0` exactly, the boundary
solution. Four reject uncorrected, where 26 one-sided tests at 5% expect 1.3 under
the null:

| cell | `sigma^2` | p | boundary region | profile 95% | team bootstrap |
|---|---|---|---|---|---|
| `primeira_liga\|attack` | 7.74e-04 | 0.0001 | [3.40e-04, 1.46e-03] | [2.77e-04, 1.64e-03] | [2.78e-04, 1.57e-03] |
| `allsvenskan\|attack` | 8.40e-04 | 0.0014 | [3.04e-04, 1.67e-03] | [2.25e-04, 1.88e-03] | [1.53e-04, 1.83e-03] |
| `allsvenskan\|defence` | 5.48e-04 | 0.0101 | [1.30e-04, 1.19e-03] | [6.71e-05, 1.35e-03] | **[0, 1.62e-03]** |
| `serie_a\|defence` | 3.26e-04 | 0.0261 | [3.83e-05, 7.96e-04] | **[0, 9.14e-04]** | **[0, 7.98e-04]** |

Bonferroni and Benjamini-Hochberg agree and keep the same two:
`primeira_liga|attack` and `allsvenskan|attack`. These carry different guarantees
and the difference is worth stating: Bonferroni controls the family-wise error rate
at 5% across all 26 tests, so the claim is that with 95% confidence *no* survivor is
false. Benjamini-Hochberg controls the false discovery rate at 5%, so among reported
survivors an expected one in twenty is false. Here they coincide, and the two
survivors hold under all three intervals.

Every cell passes the linearity gate under both relative-deviation conventions.

## 6. The two survivors are not a calendar artefact

The local level model carries neither home advantage nor opponent quality, and a
non-random schedule can make either imitate drift. Removing both as fixed effects
makes the signal stronger, not weaker: `primeira_liga|attack` goes 0.0001 → 0.0000,
`allsvenskan|attack` 0.0014 → 0.0006, `allsvenskan|defence` 0.0101 → 0.0020,
`serie_a|defence` 0.0261 → 0.0012. Where drift is detected it is about the team.
This check was added after the primary estimates were read and is labelled as
supplementary in the evidence.

## 7. Why it still should not ship

**The correction is smaller than production would notice.** Across real evaluation
states the mean age of a latest-20 window moves by only **5.9 to 28.2 days**
between its 10th and 90th percentile, because the window's calendar span is nearly
constant. Feeding each cell its own alpha — including the two confound-robust ones —
the age term changes `SE` by at most **7.88%**, by **1.54%** in the median cell, and
by nothing at all in **11 of 26**. Where alpha is measurable its own interval spans
roughly a factor of five. Frozen in `EV_SE_DRIFT_V4_IMPACT.json`, which names the
population for every number.

**Neither age nor coverage shows a calibration failure.** This needs no fitted
coefficient. For each evaluation state on production's own window,
`z = (y_next - mean(window)) / sqrt(SE0^2 + tau^2)`, stratified into quartiles.
`var(z)` rises with window age in **12 of 26** cells and falls in 14. Split by
coverage — now genuinely varying from **0.15 to 1.0**, where v3's was identically
1.0 — the low-coverage quartile has the larger `var(z)` in **14 of 26**. Both are
coin flips, and `var(z)` sits near 1.0 throughout, so the shipped baseline is
roughly calibrated in both directions an added term would address.

**Beta is not identifiable at all.** See section 8.

**Nothing can be validated out of sample.** See section 8.

## 8. Three point-in-time verdicts, one cause

Under `captured_at <= as_of` — the filter `ReadModelService._xg_uncertainty_rows`
itself applies — **not one evaluation epoch in the estimation period has three xG
observations visible at that epoch**. Zero of 18,978 rows carry a capture time
before 2026-07. Three consequences follow from that single fact:

- **`missingness_beta_pit` → `MISSINGNESS_NOT_IDENTIFIABLE`.** `u` and `D` cannot
  be formed at any epoch, so no `kappa` exists. v3 computed `kappa` from final
  static xG existence, found it negative everywhere and reported
  `MISSINGNESS_PREMISE_FAILED` — a measured direction where no admissible
  measurement existed. That static computation is retained as a diagnostic and
  relabelled; its premise verdicts must not be quoted as if they answered the
  production question.
- **`calibration.pit_basis` → `NOT_IDENTIFIABLE`.** No calibration state can be
  formed. Only the static basis is computable, and it is labelled in-sample.
- **`path_c` → `PATH_C_NOT_IDENTIFIABLE`.** No holdout fixture after 2026-01-01 has
  admissible history.

The cause is not a corrupted column. The xG values were absent from `team_xg_match`
before 2026-07; they first landed with the backfill that followed the null-retry
fix. A point-in-time replay finds nothing because there was nothing to find, and no
new record can recover epochs where the data did not exist. What changes this is
**elapsed time**: from 2026-07 onward `captured_at` accumulates a usable visibility
history under first-write-wins, so a holdout beginning after that date becomes
answerable once enough of it exists.

Production itself is not defective here. `_xg_uncertainty_rows` drops rows with
`captured_at > as_of`, so the shipped read model fails closed rather than reading
the future. The defect was in the v2 and v3 research loaders, which never read the
column.

## 9. What production does, and what can be mutated

The suite runs through `ReadModelService._empirical_xg_lambda_uncertainty`,
`ReadModelService._xg_standard_error` and
`ah_expected_value_uncertainty_from_lambdas`. Mutants are classified rather than
simulated, which is what v3's own section 10 required and v3 did not do.

**Production behaviour, measured on its own.** All four invariants production
genuinely has hold: it fails closed below three observations, more observations do
not raise sigma, more dispersed observations do not lower it, and a larger sigma
does not lower `EV_SE` through GH-3. And it is **blind to observation age**: a
one-day-old and a four-hundred-day-old observation set produce byte-identical sigma
and byte-identical `EV_SE`.

**Three mutants are production-expressible** and all three die when injected into
`_xg_standard_error`: fail-open below the evidence threshold, inverted sample
scaling, and dispersion ignored. The third initially **survived**, because the
dispersion rule only forbade a decrease and a constant standard error satisfies
that. A strict-response check (`P3b_dispersion_response_inert`) was added and it
dies. This is the same defect class the age invariant taught, found a second time in
a different rule — a preregistered invariant that only forbids a decrease is
satisfied by a formula that ignores the input entirely.

**Three mutants cannot be expressed against production and are not scored.**
Production carries no age coefficient to invert, no coverage term to flip, and never
reads a season field. Their absence is itself the finding, and simulating them
against a local wrapper — as v3 did — measures nothing about production.

**The research candidate formula** is exercised separately and labelled as research
code. It is not shipped, not reachable from production, and not a proposal.

## 10. Recommendation

**Leave `alpha_age_per_day` and `beta_missing` NULL. Recommend to the Owner that
they stay unset, and record the reason as `NOT_IDENTIFIABLE`.**

Zero is not available as a way to say this. A written zero is a claim that the
effect is absent; `NOT_IDENTIFIABLE` is the absence of a claim. v3's recommendation
asked to ship with both coefficients set to `0` "recorded as unidentifiable", which
is a contradiction, and it is withdrawn. A consumer of an unset coefficient must
omit the term rather than multiply by zero, so an unset parameter can never be read
as a measured absence of effect. The evidence encodes this in `parameter_state`.

This is a recommendation, not an action. **Nothing here unlocks Contract 1, a
migration, or a deployment; those are the Owner's decisions.** v3 wrote its
recommendation as though it could unlock Contract 1, which was not its place.

The reasoning is not "there is no drift". Two cells carry real, confound-robust
drift, established with the estimator that has the best claim to finding it. It is
that the correction is smaller than its own uncertainty and smaller than production
would notice, that its companion coefficient cannot be measured at all, and that no
out-of-sample check exists to catch either being wrong.

**On continuing research.** The binding constraint on alpha is not sample size — it
is the narrow range of `A` that production states actually span, and more seasons
will not widen it. The binding constraint on beta and on Path C is elapsed
point-in-time history, which does accumulate from 2026-07 onward. So the honest
split is: alpha is unlikely to become shippable by waiting; beta and out-of-sample
calibration become answerable in roughly a season. Re-running this package after
enough post-2026-07 history exists is worthwhile; re-running the alpha estimate
alone is not.

**On point EV.** This evidence says nothing about it, in either direction. The SE
question is not being paused because point EV has problems, and point EV must not be
adjudicated by this package. If a point-EV task is opened it should be opened on its
own evidence.

### Evidence boundary

Historical xG and the frozen Gate-1 corpus only. No settled outcome, profit, hit
rate, or the current 65 picks was read; no threshold was taken from a backtest; no
Provider call, production write, GitHub or GHCR access, or deployment occurred. **No
production read was performed at all** — every input is a frozen local artefact. No
`src/` or `apps/` file was modified, so Formal, Lock, Production and Real-money paths
are untouched. Nothing in this package is deployed, and nothing in it should be read
as deployed.

What it cannot tell you: whether the shipped `SE0` is calibrated out of sample (no
admissible holdout exists), whether these findings extend beyond the 13 leagues in
the corpus, and whether the two detected cells generalise beyond the seasons
observed.

## 11. Reproduction

The frozen xG extract is not in the repository. SHA-256
`84ef81e90377014cb9ea9abc93276aebed65e1c63b9d4e5dfa18d47443634909`, 18,978 data
rows, kickoff range 2024-02-22 to 2026-08-25, at
`/Users/liudehua/.hermes/data/ev_se_drift_v2/team_xg_match.csv`. Corpus SHA-256
`80e49d1a32b5dd9653d41826e87415acff0d32a6804dea408f3b99737a6ab5e2`. Both are in the
evidence `inputs` block.

```bash
cd /Users/liudehua/.hermes/worktrees/w2-ev-se-variogram
export W2_XG_CSV=/Users/liudehua/.hermes/data/ev_se_drift_v2/team_xg_match.csv

python3 scripts/run_ev_se_drift_v4.py --check           # expects {"reproduction": "PASS"}
python3 scripts/run_ev_se_drift_v4.py --self-test-check  # proves --check fails on 1e-6
python3 scripts/ev_se_v4_calibration.py                  # stratified calibration
python3 scripts/ev_se_v4_impact.py                       # representative power + impact
python3 scripts/ev_se_v4_power.py                        # per-cell power, about 2.5 hours
python3 scripts/ev_se_v4_power.py --only allsvenskan\|attack   # one cell, for spot checks
```

The behavioural suite needs the project dependencies:

```bash
PYTHONPATH=src /Users/liudehua/.hermes/worktrees/w2-ev-se-offline-validation/.venv/bin/python scripts/ev_se_v4_production_tests.py
```

v2 reproduces at HEAD. v3 reproduces at its own commit, because v4 corrected shared
modules — which is what a frozen historical artefact means, and it was verified
rather than asserted:

```bash
python3 scripts/run_ev_se_drift_v2.py --check
git worktree add --detach /tmp/w2-v3-frozen e429bd97
cd /tmp/w2-v3-frozen && python3 scripts/run_ev_se_drift_v3.py --check
```

## 12. Ruff, mypy and tests

| Check | Result |
|---|---|
| `ruff check .` | **All checks passed** (was 8 errors) |
| mypy strict, all 16 EV-SE scripts | **0 errors in `scripts/`** (was 33) |
| `mypy src apps` (the `make typecheck` gate) | **2 errors — pre-existing.** Identical at `b34eada9`; no `src/` or `apps/` file was changed here |
| `pytest` on the bound production paths | **54 passed** |
| `run_ev_se_drift_v4.py --check` | PASS |
| `run_ev_se_drift_v4.py --self-test-check` | PASS, counts printed by the command |
| `ev_se_v4_production_tests.py` | exit 0; 3 of 3 expressible mutants killed, 0 survived |
| `run_ev_se_drift_v2.py --check` | PASS |
| `ev_se_v4_power.py --only "allsvenskan\|attack"` | matches the frozen artefact on all 6 grid points |
| `run_ev_se_drift_v3.py --check` at `e429bd97` | PASS |

The two `mypy src apps` errors are in `expected_match_denominator.py:100` and
`future_refresh_repository.py:875`. They are reported because the gate is failing,
not because this work caused it. The full 2,912-test suite was not run; the 54 above
are the tests covering the paths this work binds to.

## 13. Open items

1. **The full test suite was not run.** 2,912 tests exist; 54 were run.
2. **Calibration has no out-of-sample basis** and will not until enough post-2026-07
   history accumulates.
3. **`raw_payload_sha256` is a placeholder in the behavioural harness**, because the
   frozen extract omitted the column. It makes production more permissive, so a
   blocked verdict stays conservative.
4. **The season-boundary signal is suggestive, not established.** 4 of 26 jump terms
   exclude zero against 1.3 expected, and 3 of those 4 are negative, which a season
   break adding variance cannot explain. The consistent reading is mean reversion at
   long lags, which would mean a linear-in-age inflation over-inflates at large `A` —
   the regime an age term would exist to serve. It is reported, not concluded.
