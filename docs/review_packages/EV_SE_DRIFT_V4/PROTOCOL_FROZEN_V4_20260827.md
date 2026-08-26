# EV-SE staleness and missing coverage — frozen protocol v4

Status: `FROZEN_BEFORE_ANY_V4_RESULT`. v2 (`b34eada9`) and v3 (`603a9753` …
`e429bd97`) are **retained unmodified as history**, including their evidence
files. Nothing in `EV_SE_DRIFT_V2/` or `EV_SE_DRIFT_V3/` is overwritten.

## 1. What v3 got wrong

Nine findings, all independently reproduced against the code and artefacts before
this document was written. Two of them are places where v3's *description* was
false, which is worse than an unfinished computation.

1. **The status matrix claimed work that did not exist.** Per-cell power was marked
   `DONE` while `EV_SE_DRIFT_V3_POWER.json` was absent and the run was 44 of 156
   points in. The main evidence file contained no power block at all. The
   representative-geometry table in the report came from an ad-hoc shell heredoc
   with no committed script, so it could not be reproduced.
2. **`kappa` was not point-in-time.** `observed_fixtures()` decided whether a
   fixture carried xG from the final static extract and never referenced
   `captured_at`. Under a real `captured_at <= as_of` filter the observed set is
   empty for every evaluation epoch before 2026-07, which makes `kappa`
   `NOT_IDENTIFIABLE` rather than premise-failed. v3 reported the weaker and wrong
   conclusion.
3. **The mutants were simulated, against v3's own instruction.** v3 §10 said a
   mutant that cannot be expressed against production must be reported as such and
   not simulated. v3 then applied all five to a local `candidate()` wrapper.
   Production carries no age or coverage term, so four of the five have nothing to
   mutate there. The season-switch mutant is furthest off: the harness attached a
   `season` field that production never reads.
4. **The calibration measured neither of the things it named.** History was grouped
   by `(league, team, season)`, so it reset at every season boundary, while
   production takes the latest 20 by kickoff across seasons. And the window was
   drawn from the xG-only series, so `|O| = |E| = 20` by construction and
   `mean_coverage` was identically `1.0` in every stratum of every cell. The
   coverage stratification was vacuous.
5. **The write semantics were described backwards.** `upsert_team_xg_matches` is
   first-write-wins behind an immutability guard: an existing row is compared field
   by field and any difference raises `TEAM_XG_MATCH_IMMUTABLE_CONFLICT`; otherwise
   the write is skipped. `captured_at` is never overwritten by ordinary ingestion.
   One controlled path, `XgRetentionService.repair_derived_lineage`, can rewrite it,
   and only it: the operation requires `write_db=true` plus a backup path, and
   `_guarded_timestamp_updates` raises on any non-timestamp drift.
6. **Three statistical statements were wrong or unstated.**
   - The profile interval used `2.7055` for every cell. That is the boundary
     critical value. For a cell whose optimum is interior it is not a 95% interval.
   - `cluster_bootstrap` resampled elements of `series_list`, which are keyed by
     `(team, season)`. That is a team-season bootstrap, not the team cluster the
     protocol specifies; a team appearing in several seasons is split across units
     and the resulting interval is too narrow.
   - The report said a naive `chi^2_1` p-value would "roughly double the
     false-positive rate". It is the reverse. The mixture p-value is
     `0.5*P(chi^2_1 > LR)`, so the naive one is twice as large, rejects less often,
     and *halves* the size to about 0.025. The naive test is conservative.
7. **The 7.9% figure had no artefact**, and it mixed three different populations —
   the representative geometry, the real per-cell geometry, and the distribution of
   real production states — inside one paragraph.
8. **Hygiene and bookkeeping.** Ruff reported 8 errors and mypy 33 across the new
   scripts. The report quoted 1,165 numeric fields when the file had 1,217, and
   named `9222ee8c` as the head of the chain when `e429bd97` was.
9. **`0` was used to mean "unset".** The recommendation asked to ship with
   `alpha_age_per_day = 0` and `beta_missing = 0` "recorded as unidentifiable",
   which is a contradiction. A written zero is a claim that the effect is absent.
   `NOT_IDENTIFIABLE` is the absence of a claim.

## 2. Question, unchanged from v3 §2

Whether the point-in-time data that exists can identify staleness and
missing-coverage uncertainty, and whether either belongs in production.
`NOT_IDENTIFIABLE` with the missing inputs named remains a complete answer.

## 3. Estimator, unchanged from v3 §3 except where §4 corrects it

The exact Gaussian likelihood for the local level model, diffuse in the level,
Kalman recursion accumulating from `k=2`, Nelder-Mead in pure stdlib, seed
`20260826`. The variogram and v1 stay as comparators. None of this changes; the
v3 point estimates stand and are re-emitted unmodified.

## 4. Corrected inference semantics

**Test.** `sigma^2 = 0` is on the boundary, so the null distribution of the
likelihood-ratio statistic is `0.5*delta_0 + 0.5*chi^2_1`. The one-sided p-value is
`0.5*P(chi^2_1 > LR)`. A naive `chi^2_1` p-value is exactly twice this, rejects
less often, and would run the test at about half its nominal size. The mixture is
used, and the direction is stated correctly wherever it appears.

**Two intervals, both reported, each with its meaning stated.**

- `boundary_region_95`: `{sigma^2 : 2*(ll_max - ll_profile) <= 2.7055}`. This is
  the set not rejected by the one-sided boundary test at 5%. It agrees with the
  test by construction and excludes zero exactly when the test rejects. It is
  **not** a two-sided 95% confidence interval for an interior parameter.
- `profile_ci_95`: the same construction at `3.8415`, the `chi^2_1` 95% quantile.
  This is the conventional 95% profile interval, correct where the optimum is
  interior, conservative at the boundary.

Neither is described as "the" interval. Cells whose optimum sits exactly at
`sigma^2 = 0` have the boundary case flagged in the evidence.

**Bootstrap.** Resampling unit is the **team**, not the team-season: all of a
team's series across all seasons move together. 200 replications, seed `20260826`,
percentile interval, reported beside the likelihood intervals as a robustness
check and never as the primary. The reduced replication count is stated, not
disguised.

## 5. Missingness and beta, restated as a PIT question

`E` is the latest `20` **expected** fixtures before the evaluation epoch, taken
from the frozen corpus across seasons — not reset at a season boundary, matching
what production's `limit_per_team=20` ordering does. `O` is the subset whose xG was
visible at that epoch, which means `captured_at <= as_of`, the same filter
`ReadModelService._xg_uncertainty_rows` applies.

If the PIT-filtered `O` is empty or too small to support the fit at every epoch,
`kappa` is `MISSINGNESS_NOT_IDENTIFIABLE`. That verdict is distinct from
`MISSINGNESS_PREMISE_FAILED`, which asserts a measured direction; it may not be
reported when no admissible measurement exists. The non-PIT computation from v3 is
retained beside it, relabelled as what it is: a static-existence diagnostic that
does not answer the production question.

## 6. Calibration, matching production semantics

Evaluation states use the latest `20` fixtures by kickoff **across seasons**, with
no season reset, exactly as `team_xg_matches_for_teams` orders them. Coverage is
`|O|/|E|` with `E` from the expected-fixture corpus and `O` the xG-carrying subset,
so coverage varies rather than being `1.0` by construction.

Two bases are computed and never mixed:

- `static`: `O` decided by final xG existence. In-sample, and labelled as a
  diagnostic that overstates what was knowable.
- `pit`: `O` decided by `captured_at <= as_of`. This is the production question.
  Where it yields too few states it reports `NOT_IDENTIFIABLE` rather than falling
  back to `static`.

No holdout is fabricated. The baseline column uses only `SE0` and `tau^2` and so
stays coefficient-free; the candidate column is circular whenever `alpha` comes
from the same data and says so.

## 7. Power and size, and the Gate that consumes them

Per-cell real geometry, `tau^2` from that cell's own fit, grid
`{0, 1e-5, 3e-5, 1e-4, 3e-4, 1e-3}`, 500 replications, seed `20260826`, both
estimators on identical replicates, `sigma^2 = 0` on the grid to measure size.
Unchanged from v3 §4 — but the artefact must **exist and be frozen** before any
matrix row may say `DONE`, and the evidence must carry a pointer to it with its
own SHA-256.

Three populations are named separately everywhere and never averaged together:

1. `representative_geometry` — the synthetic `20 x 45 / 300 days` design;
2. `real_cell_geometry` — the observed timestamps of each `league x component`;
3. `production_states` — the distribution of window ages across real evaluation
   states.

Any operational impact number is computed by a committed script into a frozen
artefact, naming which of the three it used.

## 8. Behavioural tests, honestly classified

Every mutant is placed in exactly one class and the class is emitted with it:

- `PRODUCTION_EXPRESSIBLE` — the defect can be injected into the shipped code path
  and the suite must reject it there;
- `NOT_EXPRESSIBLE_IN_PRODUCTION` — production has no such behaviour to break. The
  reason is recorded and **no simulated substitute is scored as a pass**;
- `RESEARCH_CANDIDATE_ONLY` — exercised against the candidate formula, which is
  research code and is labelled as research code.

Production's own behaviour is reported separately from any candidate: what the
shipped chain does about age, about coverage, and about insufficient evidence.

## 9. Form and boundary, unchanged from v3 §8 and §5

Carried forward. `alpha_rel = alpha_abs / SE0^2` reported per league with the
measured `SE0^2` spread; cross-season pairs estimated separately with a jump term.

## 10. Null is not zero

`alpha_age_per_day` and `beta_missing` remain `NULL`. `NOT_IDENTIFIABLE` is
recorded as the absence of a value, never as `0`. A formula consuming an unset
coefficient must omit the term, not multiply by zero, so that an unset parameter
cannot be silently read as a measured absence of effect. No recommendation in this
package unlocks a contract, a migration, or a deployment; those are Owner
decisions and are written as such.

## 11. Deliverables

Report, status matrix whose rows match the files that exist, frozen evidence JSON,
frozen power artefact, frozen operational-impact artefact, every reproduction
command, Ruff and mypy and test results, an explicit list of what remains open, and
an independent opinion on pausing SE, continuing research, or opening a separate
point-EV task — with the note that point EV may not adjudicate SE in either
direction.

## 12. Standing constraints

Provider 0, production writes 0, GitHub 0, GHCR 0, no deployment. Formal, Lock,
Production and Real-money stay off. Settled profit, hit rate and the current 65
picks may not select or reject any parameter. Local verification is never written
up as shipped. Production reads, if any, only under
`BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY`.
