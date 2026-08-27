# EV-SE staleness and missing coverage — frozen protocol v5

Status: `FROZEN_BEFORE_ANY_V5_RESULT` for sections 4, 5, 6 and 7. Section 3 records
one measurement taken before this document existed and says so.

v2 (`b34eada9`), v3 (`e429bd97`) and v4 (`5a40f448`) are retained unmodified,
evidence included. The v4 protocol commit `18f812b7` is not amended.

## 1. What v4 got wrong

Five findings, reproduced against the code before this was written.

1. **The operational-impact study reset the window at season boundaries.**
   `production_state_ages` grouped by `(league, team, season)`, so every window sat
   inside one season. Production's `team_xg_matches_for_teams` orders by kickoff
   with `limit_per_team=20` and does not filter by season. v4 §6 already required
   cross-season windows for calibration; the impact script simply did not implement
   the same thing, and neither did `se0_squared_quantiles`, which feeds
   `form_mismatch` **and** the impact figure through `se0_squared_p50`. The defect
   is therefore wider than the reviewer found.
2. **The confound diagnostic used sequential category demeaning.** `_centre` removed
   the home/away mean, then removed the opponent mean *from the result*. That is one
   pass of backfitting, not a joint two-way fixed-effects fit, and the drift model
   was then fitted to those residuals as if they were data — the nuisance parameters
   carried no uncertainty into the p-value. "Confound-robust" and "the drift is
   about the team" were stronger than the method supported.
3. **In-sample static calibration was described as calibration of the shipped
   baseline.** The diagnostic uses final xG existence, the estimation period, and no
   point-in-time filter. It cannot speak to whether production is calibrated, and
   PIT and out-of-sample remain `NOT_IDENTIFIABLE`.
4. **The power freeze recorded a claim, not a check.** `--verified-cell` set
   `verified: true` merely because the flag was passed; no comparison was performed
   or stored. And the artefact's grid entries carry `seconds`, which is wall clock,
   so "bit for bit" could not have meant the whole record.
5. **Reporting errors.** The Bonferroni and Benjamini-Hochberg glosses were loose;
   the next steps recommended adding a first-write regression test that already
   exists and passes
   (`tests/integration/test_future_refresh_db_persistence.py::test_team_xg_match_preserves_first_visible_evidence`);
   and the mypy row said "16 EV-SE scripts" after a seventeenth had been added.

## 2. What finding 1 does to v4's conclusion

Measured before this protocol was frozen, and disclosed here rather than presented
as a v5 result: under production's cross-season window the 10th-to-90th percentile
span of mean window age is **55 to 180 days**, not the 5.9 to 28.2 days v4 reported.
Feeding each cell its own alpha, the age term changes `SE` by up to **49%** with a
median of **7.3%**, not 7.88% and 1.54%.

So v4's strongest argument — that the correction is too small for production to
notice — was an artefact of the bug and is **withdrawn**. v5 must re-derive its
recommendation rather than defend the old one, and must state plainly which of the
remaining arguments still stand.

Two things this does not change, and the report must not let them drift: the alpha
estimates themselves, which are fitted within season by design with the boundary
handled separately, and the per-cell power study, which concerns detectability
rather than window construction.

## 3. Window semantics, and a check that enforces them

The production evaluation window is the latest `20` rows for a team ordered by
kickoff **across seasons**, as `team_xg_matches_for_teams` returns them, then
filtered by `_xg_uncertainty_rows` on `kickoff < as_of` and `captured_at <= as_of`.

Every script that builds an evaluation state must use one shared constructor. A
self-check must **fail** when a window is built per season: it compares the
cross-season state count and age spread against a deliberately season-reset
construction and asserts they differ in the direction a reset produces. A silent
regression to per-season grouping is the specific failure this must catch.

## 4. Confounding, estimated jointly and bootstrapped end to end

Home advantage and opponent identity enter as a **joint** two-way fixed-effects
model fitted by alternating projections to convergence, not by one sequential pass.

Nuisance-parameter uncertainty is handled by resampling the **whole two-stage
procedure**: each cluster bootstrap replication draws teams with replacement,
refits the fixed effects on the resampled data, and refits the drift model to those
residuals. The interval and the bootstrap p-value therefore include the cost of
having estimated the fixed effects. 400 replications, seed `20260826`.

**Claim discipline.** The permitted conclusion is about what the adjustment does to
the estimate, stated as such. `confound-robust`, `proves the drift is about the
team`, and any phrasing implying the confounds have been ruled out are prohibited
regardless of how the numbers come out. Opponent identity is a proxy for opponent
strength and is itself measured with error; congestion, competition, and personnel
are not in the model at all.

## 5. Calibration, and what may be said about it

Two bases, as in v4 §6: `static` and `pit`. Both use the section 3 window.

`static` may be described only as an in-sample diagnostic computed with information
that was not available at prediction time. It may **not** be offered as evidence
that the shipped baseline is calibrated, in production or out of sample. Where the
`pit` basis cannot be formed the answer stays `NOT_IDENTIFIABLE`, and no sentence
may substitute the static result for it.

## 6. Power provenance, checked by machine

A frozen power artefact must carry a comparison that a reviewer can re-run and a
machine can verify:

- the fields that participate are named explicitly. `mle_rejection_rate` and
  `variogram_rejection_rate` are compared; `seconds` is wall clock and is excluded,
  which is why "bit for bit" may not be said of the whole record;
- the verification tool re-runs one cell under the canonical script, compares the
  named fields, and writes the observed values from both sides into the artefact
  alongside the verdict;
- `verified: true` may only be written by a tool that performed the comparison.
  Passing a flag is not a verification.

## 7. Statistical statements

Bonferroni controls the family-wise error rate: the probability that the procedure
makes **one or more** false rejections is at most 5%. Benjamini-Hochberg controls
the false discovery rate: the **expected proportion** of false rejections among
those reported is at most 5%. Neither is a posterior probability about any
individual survivor, and neither may be glossed as one.

Every count, scope and command in the report must match what was run. The mypy row
names the exact file list; claims about repository state are checked against the
repository.

## 8. Carried forward unchanged

The estimator and its inference semantics from v4 §3 and §4: exact Gaussian
likelihood for the local level model, boundary mixture for the test, both intervals
with their meanings, team-clustered bootstrap. Missingness as a point-in-time
question from v4 §5. Behavioural test classification from v4 §8. Null is not zero
from v4 §10.

## 9. Standing constraints

`alpha_age_per_day` and `beta_missing` stay `NULL` and are not encoded as `0`.
Nothing in this package enters a production Gate, unlocks Contract 1, or deploys;
those are Owner decisions. Provider 0, production reads 0, production writes 0,
GitHub 0, GHCR 0, no deployment. Formal, Lock, Production and Real-money stay off.
Settled profit, hit rate and the current 65 picks may not select or reject any
parameter or conclusion. Point EV is out of scope and may not be adjudicated here.
