# EV-SE staleness and missing coverage — v6 findings

Protocol `b74766f9`, frozen before sections 3–7 were run. Clause-by-clause state in
`STATUS_MATRIX.md`. v2 (`b34eada9`), v3 (`e429bd97`), v4 (`5a40f448`) and v5
(`9e4e4723`) are retained unmodified.

**Two artefacts are still computing at the time of writing** and their rows say so
in the matrix, in the evidence (`present: false`) and in section 12 here. Nothing in
this report claims a file that does not exist.

## 1. The population was still conditioned on the future

v5 fixed the window and then drew evaluation epochs from the xG-carrying series, so
an epoch existed only where the target fixture produced xG afterwards. Production
decides at the as-of of every fixture it analyses and cannot know that.

Verifying it turned up a second condition in the same family, and a larger one.
Slicing `series[i-20:i]` also required a **full twenty-row window**, while
`_xg_standard_error` fails closed below **three** rows. Both are conditions
production does not impose:

| condition v5 imposed | epochs lost |
|---|---|
| target fixture later carried xG | 872 |
| window held a full 20 rows | **5,082** |
| both together | v5's 8,578, against production's **14,290** |

Admission ledger on the corrected population: 33,450 candidate `(team, fixture)`
pairs → 2,059 excluded for a team with no xG history at all → 17,101 excluded for a
window below three rows → **14,290 admitted**, 0 excluded for zero variance.

## 2. The impact has grown at every correction

| | v4 | v5 | v6 |
|---|---|---|---|
| age span p10→p90 | 5.9–28.2 d | 55–180 d | wider again; p10 falls to ~25–49 d |
| SE change, max | 7.88% | 49.07% | **84.91%** |
| SE change, median | 1.54% | 7.31% | **11.42%** |
| cells where the term does nothing | 11/26 | 11/26 | 11/26 |

Worth stating plainly rather than burying: **every correction so far has made the
effect larger, never smaller.** Three successive reviews each removed a condition
that suppressed it. That pattern is itself information — it says the direction of my
errors has been consistent, and it is a reason to treat the current number as a
lower bound on what a fourth review might find rather than as settled.

The count Codex corrected is confirmed: **12 of 15** non-boundary cells have a
profile-based impact band reaching zero, not 10.

## 3. One epoch source, three guards, all watched to fail

`ev_se_v6_epochs` is the single constructor. It carries a guard for each regression
that has already put a wrong number in one of these reports:

| regression | guard fires under injection |
|---|---|
| windows grouped by season | yes |
| epochs conditioned on the target having xG | yes |
| PIT basis ignoring `captured_at` | yes |

`--prove-it-fails` injects each and reports `all_guards_bite: true`. The season-reset
guard alone could not have caught finding 1, which is why there are three.

## 4. The bootstrap p-value v5 promised

A percentile interval yields no p-value at a boundary, and `share_at_boundary` is
not one. It is built rather than renamed: the null distribution is simulated with
`sigma^2` pinned to zero on the real geometry, the joint fixed effects are refitted
on every replicate so they cost something on both sides, and

```
p = (1 + #{sigma2_null >= sigma2_observed}) / (1 + 400)
```

A sanity check the construction passes: the share of null draws resting on the
boundary lands at **0.52–0.58**, against the 0.5 the theory predicts for a variance
component at its boundary.

Computed values, with the artefact being refrozen to add multiplicity:

| cell | adjusted `sigma^2` | null p95 | bootstrap p |
|---|---|---|---|
| `primeira_liga\|attack` | 1.161e-03 | 2.764e-04 | 0.0025 |
| `serie_a\|defence` | 4.626e-04 | 2.340e-04 | 0.0025 |
| `allsvenskan\|attack` | 7.876e-04 | 3.457e-04 | 0.0050 |
| `allsvenskan\|defence` | 6.599e-04 | 3.353e-04 | 0.0075 |

**A limit of the procedure, recorded rather than hidden.** With 400 replications the
smallest attainable p is `1/401 = 0.0025`. Bonferroni across 26 tests requires
`0.00192`. **No cell can clear Bonferroni at this replication count however strong
the signal is** — reaching it would need at least 520 replications. The artefact
carries `bonferroni_is_attainable: false`. Benjamini-Hochberg is attainable and
keeps four cells.

My technical opinion on the clause: v5 §4 was **not** met, and the honest reading is
that it was reported met on a quantity that had the wrong meaning. It is met now,
with the resolution caveat above stated as part of the answer rather than as a
footnote.

## 5. What waiting for data buys — measured, and the answer is not much

v5 said "more seasons add cells, not resolution". That was wrong and Codex is right
about why: the 26 cells are fixed by league and component, and what more seasons add
is team-season **series inside** each cell, which is exactly what the likelihood
accumulates over. So more data does add estimation information.

The useful question is how much, so it is measured rather than argued. Power at
`sigma^2 = 1e-4` — the rate that moves `SE` about 10% over 60 days — with each
cell's series count replicated 1, 2, 4 and 8 times on its own real geometry:

| cell | ×1 | ×2 | ×4 | ×8 | reaches 80% |
|---|---|---|---|---|---|
| `allsvenskan\|attack` | 0.088 | 0.132 | 0.204 | 0.322 | no |
| `allsvenskan\|defence` | 0.092 | 0.142 | 0.218 | 0.340 | no |
| `argentina_primera\|attack` | 0.132 | 0.194 | 0.338 | 0.518 | no |
| `argentina_primera\|defence` | 0.128 | 0.186 | 0.338 | 0.508 | no |

*(4 of 26 cells complete; the study is still running — section 12.)*

At **eight times** today's data — on the order of twenty seasons — power at the rate
that matters is still 0.32 to 0.52. The growth is real and roughly what a
`sqrt(N)` noncentrality predicts, which means reaching 80% would take something like
another four to eight-fold beyond that. So the corrected statement is:

> Waiting does add information. It does not add nearly enough. The estimate becomes
> better, not usable, and the gap is orders of magnitude rather than a season or two.

That is a stronger and more useful answer than either v5's wrong claim or a vague
"more data would help".

## 6. What has not changed

Alpha estimates, the per-cell power study and the behavioural test results are
unchanged since v3, v4 and v4 respectively, and are not re-derived. Under
`captured_at <= as_of` no epoch in the estimation period carries three visible xG
observations, so missingness/`beta`, the PIT calibration basis and Path C all remain
`NOT_IDENTIFIABLE` for one reason: the values were absent from `team_xg_match`
before the 2026-07 backfill. Only elapsed time changes that.

## 7. Why an age term still should not ship

The arguments have been rebuilt twice and I want to be explicit that the *first* one
is gone for good.

- **Not "too small".** That was v4's reason and it was an artefact of a bug. On the
  corrected population the term is a first-order change to `SE`.
- **Too wide.** 12 of 15 non-boundary cells have an impact band reaching zero at the
  bottom while the top runs into the tens of percent. A Gate moved by an unbounded
  amount is worse than one not moved.
- **Not identifiable at the magnitude that matters, and not fixable by waiting.**
  0 of 26 cells reach 80% power at `1e-4` today, and at 8× the data the completed
  cells sit at 0.32–0.52.
- **The largest impacts come from the regime the boundary term distrusts.** The
  longest windows cross season breaks; 4 of 26 jump terms exclude zero and 3 of those
  are negative, which is the random walk over-predicting at long lags.
- **Beta cannot be measured at all**, and no out-of-sample check exists to catch
  either coefficient being wrong.

## 8. The four questions

**Is the research package acceptable?** Codex's call. What changed: the epoch
population is now defined by what is knowable at the decision instant and carries an
admission ledger; two conditions that suppressed the effect are removed; three
guards exist where one did; the promised p-value is built rather than borrowed; and
two counts are corrected.

**Are alpha and beta identifiable?** No. Alpha is not identifiable at the magnitude
that matters and would not become so with an order of magnitude more data. Beta is
`MISSINGNESS_NOT_IDENTIFIABLE` under a real point-in-time filter. Both stay `NULL`;
zero is a claim that the effect is absent and is not available as a way to write
this.

**Is Contract 1 authorised?** No. Nothing here enters a production Gate, unlocks
Contract 1, implements a production formula, or deploys. The evidence records this
under `authorisation` with all three flags false. Owner decisions, not mine.

**Is point EV in scope?** No, by protocol §9, and nothing here adjudicates it.

## 9. My independent opinion

Keep the direction paused — and I now hold the *reason* differently for the second
time, so the shift is worth naming rather than smoothing over.

v4 said the effect was negligible. v5 said it was large but unmeasurably wide. v6
says the same as v5 with a larger number and adds one thing that changes the
practical advice: **waiting will not fix it.** Before measuring the scaling curve I
recommended letting data accumulate as the path back to alpha. That was optimistic.
Eight times today's data leaves power at roughly a third to a half. The honest
version is that alpha is not coming back through patience.

What does follow:

1. **Production's age blindness is a live risk and the largest open item.** The
   effect is first-order, and identical `SE` for a one-day-old and a
   four-hundred-day-old window is a modelling gap, not a rounding error. A
   fail-closed staleness gate needs no estimated coefficient — but its threshold
   cannot come from backtested performance under the standing rule, so it needs its
   own package and its own basis. I am not proposing a value.
2. **If alpha is to be revisited, change the model, not the sample size.** The
   boundary terms point at mean reversion rather than a random walk. A model with a
   stationary component would be estimating something the data can resolve, unlike a
   variance rate at `1e-4`. That is a new protocol, not a re-run.
3. **Point-in-time history is still worth accumulating**, but for beta and
   out-of-sample calibration, not for alpha. Those three verdicts are blocked on
   absent history rather than on power.
4. **Keep the strict-response invariants.** `age_term_inert` and
   `P3b_dispersion_response_inert` are the only checks that catch a formula ignoring
   an input; that defect class has now appeared twice.

## 10. Reproduction

Frozen extract SHA-256
`84ef81e90377014cb9ea9abc93276aebed65e1c63b9d4e5dfa18d47443634909`, 18,978 data
rows, at `/Users/liudehua/.hermes/data/ev_se_drift_v2/team_xg_match.csv`. Corpus
SHA-256 `80e49d1a32b5dd9653d41826e87415acff0d32a6804dea408f3b99737a6ab5e2`.

```bash
cd /Users/liudehua/.hermes/worktrees/w2-ev-se-variogram
export W2_XG_CSV=/Users/liudehua/.hermes/data/ev_se_drift_v2/team_xg_match.csv

python3 scripts/ev_se_v6_epochs.py                   # epoch guard, ledger
python3 scripts/ev_se_v6_epochs.py --prove-it-fails   # all three guards must FAIL
python3 scripts/ev_se_v6_impact.py                    # ages, SE0^2, impact
python3 scripts/ev_se_v6_confound.py                  # joint FE + null bootstrap, ~15 min
python3 scripts/ev_se_v6_scaling.py                   # series scaling, ~2 hours
python3 scripts/run_ev_se_drift_v6.py --emit
python3 scripts/run_ev_se_drift_v6.py --check
python3 scripts/run_ev_se_drift_v6.py --self-test-check
```

Earlier packages reproduce at their own commits:

```bash
python3 scripts/run_ev_se_drift_v2.py --check                    # at HEAD
git worktree add --detach /tmp/w2-v5 9e4e4723 && cd /tmp/w2-v5 && python3 scripts/run_ev_se_drift_v5.py --check
```

## 11. Ruff, mypy and tests

| Check | Result |
|---|---|
| `ruff check .` | All checks passed |
| mypy strict, the v6 scripts | 0 errors in `scripts/` |
| `mypy src apps` (`make typecheck`) | 2 errors — pre-existing, identical at `b34eada9` |
| `ev_se_v6_epochs.py` self-check | PASS |
| `ev_se_v6_epochs.py --prove-it-fails` | all three guards bite |
| `ev_se_v6_impact.py` | max 84.91%, median 11.42%, 12/15 bands reach zero |
| `run_ev_se_drift_v2.py --check` | PASS |
| `pytest` on the bound production paths | 54 passed |

No `src/` or `apps/` file was changed in v3, v4, v5 or v6.

## 12. Still running, and what is therefore not claimed

1. **`EV_SE_DRIFT_V6_CONFOUND.json`** — the p-values in section 4 are computed and
   will not change (same seed, same data); the artefact is being rewritten to add
   the multiplicity block and the resolution note. Until the file exists the matrix
   says IN PROGRESS.
2. **`EV_SE_DRIFT_V6_SCALING.json`** — 4 of 26 cells complete. Section 5 reports
   only those four and says so. The pattern across them is consistent, but four
   cells are four cells.
3. **`EV_SE_DRIFT_V6_EVIDENCE.json`** is emitted after both, so that it can carry
   their SHA-256s rather than `present: false`.

## 13. Remaining uncertainty

1. **Every correction so far has enlarged the effect.** I would not treat 84.91% as
   settled; a fourth review finding a fifth suppressing condition would fit the
   pattern.
2. **The scaling study replicates observed series**, so it assumes future seasons
   resemble past ones in length and spacing. It does not model calendar or coverage
   change.
3. **The two surviving cells may not generalise** — two of 26, both shorter-season
   leagues, one withdrawn from production.
4. **The confound adjustment is not a clean bill.** Opponent identity proxies
   opponent strength with error; congestion, competition and personnel are absent.
5. **Out-of-sample calibration does not exist** and will not until enough
   post-2026-07 point-in-time history accumulates.
6. **The full 2,912-test suite was not run**; 54 were.

## 14. Commit chain

`b34eada9` v2 · `603a9753`…`e429bd97` v3 · `18f812b7`…`5a40f448` v4 ·
`4558f5ab`…`9e4e4723` v5 · `b74766f9` v6 protocol, frozen before results.
