# EV-SE staleness and missing coverage — frozen protocol v6

Status: `FROZEN_BEFORE_ANY_V6_RESULT` for sections 3 through 7. Section 2 records
two measurements taken while verifying the review and says so.

v2 (`b34eada9`), v3 (`e429bd97`), v4 (`5a40f448`) and v5 (`9e4e4723`) are retained
unmodified, evidence included. No earlier protocol commit is amended.

## 1. What v5 got wrong

1. **The evaluation-epoch population conditioned on the future.** `observed_states`
   walked the xG-carrying series and treated each of *those* kickoffs as an
   evaluation epoch. Production forms an SE state at the as-of of every fixture it
   analyses and never requires the target to produce xG afterwards. So the
   population was selected on an outcome that postdates the decision.
2. **Two constructors, one claim.** Impact and `SE0^2` used `observed_states` while
   calibration used `coverage_states`, and the two admit target epochs by different
   rules. The status matrix said "one shared constructor". The season-reset guard
   cannot see this class of defect at all, because both constructions reset or do
   not reset together.
3. **A protocol clause was reported as met and was not.** v5 §4 promised "the
   interval and the bootstrap p-value". The artefact carries a percentile interval
   and `share_at_boundary`, which is the fraction of replications resting on the
   boundary. That is not a p-value and renaming it would not make it one.
4. **Two reporting errors.** The count of non-boundary cells whose profile-based
   impact band reaches zero is **12 of 15**, not 10. And "more seasons add cells,
   not resolution" is wrong: the 26 cells are fixed by league and component, and
   what more seasons add is team-season series *inside* each cell, which is exactly
   what the likelihood accumulates over.

## 2. Disclosure of two figures already seen

Measured while verifying finding 1, before this document was frozen:

- production's evaluation epochs number **14,290** against v5's **8,578**, so 40%
  were excluded by a condition that could not be known at the epoch;
- with them restored the age distribution shifts left at the bottom: the 10th
  percentile falls from roughly 70–100 days to roughly 25–49 days while the 90th is
  little changed, so the span widens again.

The impact figures that follow from these are **not** yet computed and are v6
results. Sections 3 to 7 were fixed before any of them was read.

## 3. The authoritative evaluation-epoch population

An evaluation epoch is a `(team, fixture)` pair drawn from **every** finished
fixture in the frozen corpus, at the fixture's kickoff. Admission is decided only by
what is knowable at that instant:

- the window is the latest `20` xG rows for that team with `kickoff < as_of`,
  ordered by kickoff, **across seasons**;
- under the point-in-time basis the window additionally requires
  `captured_at <= as_of`;
- an epoch is admitted when the window holds at least `3` rows and their sample
  variance is positive, which is where `_xg_standard_error` fails closed.

Whether the target fixture ever produced xG is **not** an admission criterion. It is
required only to score a residual, so the calibration study — and nothing else — may
restrict to epochs that have one, and must report that restriction as a count.

Every artefact reports admitted and excluded epoch counts with the reason for each
exclusion.

## 4. Guards, each with a negative control that must fail

One module constructs epochs. Its self-check must fail under each of these injected
regressions, and the failure must be demonstrated, not asserted:

1. **season reset** — windows grouped by `(league, team, season)`;
2. **target-xG conditioning** — epochs restricted to fixtures that later carried xG;
3. **future capture leak** — the point-in-time basis ignoring `captured_at`.

A guard that has not been watched to fire is not evidence. The negative-control run
emits, per injection, which findings fired.

## 5. Confounding: the p-value the clause requires

A percentile interval does not yield a p-value at a boundary, and
`share_at_boundary` is not one. The bootstrap p-value is therefore defined here as a
**parametric bootstrap under the null**:

for each cell, take the jointly fitted fixed effects and `tau^2` from the null-
restricted fit, simulate replicate series on the real timestamp geometry with
`sigma^2 = 0`, refit the fixed effects jointly on each replicate, refit the drift
model to its residuals, and report

```
p = (1 + #{sigma2_null >= sigma2_observed}) / (1 + replications)
```

400 replications, seed `20260826`. This respects the boundary, prices in the fixed
effects on both sides, and is comparable to the size check the power study already
runs. The percentile interval and `share_at_boundary` are retained beside it and
neither is called a p-value.

If this cannot be produced for a cell, that cell reports the clause as unmet rather
than substituting a different quantity.

## 6. What waiting for data can and cannot buy

The 26 cells are fixed. More seasons add **team-season series within** each cell,
and the likelihood accumulates across series, so more seasons do add estimation
information. v5 said otherwise and was wrong.

The honest answer is quantitative, not rhetorical, so it is measured: the power
study is repeated with the per-cell series count scaled by `{1, 2, 4, 8}` on the
same real geometry, at the drift rate that moves `SE` about 10% over 60 days. The
report states the multiple of today's data at which that rate reaches 80% power, or
states that it is beyond the range examined.

## 7. Recomputation

Production state ages, the `SE0^2` distribution, `form_mismatch` and the
operational impact are all recomputed on the section 3 population and refrozen. The
alpha estimates, the per-cell power study and the behavioural test results are
unchanged and are not re-derived.

## 8. Carried forward unchanged

Estimator and inference semantics from v4 §3 and §4. Missingness as a point-in-time
question from v4 §5. Calibration claim limits from v5 §5. Power provenance from v5
§6. Statistical statement discipline from v5 §7. Behavioural test classification
from v4 §8.

## 9. Standing constraints

`alpha_age_per_day` and `beta_missing` stay `NULL` and are never encoded as `0`.
Nothing here enters a production Gate, unlocks Contract 1, implements a production
formula, or deploys. Provider 0, production reads 0, production writes 0, GitHub 0,
GHCR 0. Formal, Lock, Production and Real-money stay off. Settled profit, hit rate
and the current 65 picks may not select or reject any parameter or conclusion. Point
EV is out of scope.
