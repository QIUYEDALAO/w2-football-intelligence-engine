# EV-SE staleness and missing coverage — v5 findings

Protocol `4558f5ab`, frozen before sections 4–7 were run. Evidence
`EV_SE_DRIFT_V5_EVIDENCE.json`. Clause-by-clause state in `STATUS_MATRIX.md`.
v2 (`b34eada9`), v3 (`e429bd97`) and v4 (`5a40f448`) are retained unmodified.

## 1. The headline: v4's main argument does not survive

v4 concluded that an age term should not ship, and its strongest reason was that
the correction would be too small for production to notice — at most 7.88%, median
1.54%. That reason came from a bug.

v4 built evaluation windows grouped by `(league, team, season)`. Production's
`team_xg_matches_for_teams` takes the latest 20 rows ordered by kickoff with no
season predicate, so a real window routinely spans an off-season break. Under
production's own window:

| | v4 (season-reset) | v5 (production) |
|---|---|---|
| mean window age, p10→p90 span | 5.9 – 28.2 days | **55 – 180 days** |
| SE change from the age term, max | 7.88% | **49.07%** |
| SE change, median | 1.54% | **7.31%** |
| cells where the term does nothing | 11 of 26 | 11 of 26 |

The same defect sat in `se0_squared_quantiles`, which fed both `form_mismatch` and
the impact figure through `se0_squared_p50`, so it reached further than the review
found. Both now come from one shared constructor, `ev_se_v5_window`, and a
self-check fails if a season reset is ever reintroduced (section 3).

**"Too small to matter" is withdrawn.** The conclusion has to be re-derived, and
sections 5 and 6 do that. It lands in the same place for different — and I think
better — reasons, and it changes what should happen next.

Two things the bug does not touch, and I want to be explicit rather than let them
drift: the alpha estimates themselves, which are fitted within season by design with
the boundary handled separately, and the per-cell power study, which is about
detectability and never used an evaluation window.

## 2. Other corrections carried in

**Confounding.** v4 removed the home/away mean, then removed the opponent mean from
that result, and fitted the drift model to the leftovers as if nothing had been
estimated. That is one backfitting pass, not a joint fit, and it ignores the cost of
estimating the nuisance parameters. On that basis v4 wrote "confound-robust" and
"the drift is about the team". Both are withdrawn. Section 7 has the joint estimate.

**Calibration.** v4 said `var(z)` near 1.0 showed "the shipped baseline is roughly
calibrated". It cannot show that. The diagnostic is in-sample, uses final xG
existence, and applies no point-in-time filter. Withdrawn; section 6 states what it
can support.

**Power provenance.** v4's freeze tool wrote `verified: true` because a flag was
passed. Nothing was compared. And the record it called "bit for bit" contains
`seconds`. Section 8 replaces the claim with a check.

**Reporting.** The Bonferroni and Benjamini-Hochberg glosses are corrected in
section 4. The next-step recommending a first-write regression test is withdrawn —
`tests/integration/test_future_refresh_db_persistence.py::test_team_xg_match_preserves_first_visible_evidence`
already exists and passes; I recommended work the repository had already done.

## 3. One window constructor, and a guard that has been seen to fail

Everything that builds an evaluation state now calls `ev_se_v5_window`. Its
`self_check` compares the cross-season construction against a deliberately
season-reset one and fails unless the former yields more states and a materially
wider age spread — 8,578 states at a 92.3-day spread against 4,489 at 29.1, a ratio
of 3.17.

A guard nobody has watched fail is not a guard, so `--prove-it-fails` injects the
regression and confirms the check catches it. That negative control found a real
defect on its first run: it patched `ev_se_v5_window.observed_states` while the file
was executing as `__main__`, so the patch landed on a second module object and the
check reported a pass having injected nothing. Fixed, and it now reports two
findings under the injected regression.

## 4. What the data says, with the multiplicity statements corrected

26 cells; 11 return `sigma^2 = 0` exactly. Four reject uncorrected where 26
one-sided tests at 5% expect 1.3. Bonferroni and Benjamini-Hochberg agree and keep
`primeira_liga|attack` and `allsvenskan|attack`.

The two guarantees differ and v4's gloss was loose. **Bonferroni** controls the
family-wise error rate: the probability that the procedure makes *one or more* false
rejections is at most 5%. **Benjamini-Hochberg** controls the false discovery rate:
the *expected proportion* of false rejections among those reported is at most 5%.
Neither is a probability statement about any individual survivor, and v4's "with 95%
confidence no survivor is false" read like one.

## 5. Why an age term still should not ship — the argument, rebuilt

v4's reason is gone. Four remain, and the first is new.

**The correction is not too small; it is too wide.** Reading the impact at the
endpoints of alpha's own 95% profile interval, for **10 of the 15 cells where alpha
is non-zero the band runs from 0% to somewhere between 20% and 68%.** So the honest
statement is not "this would do nothing" but "this would do somewhere between
nothing and a two-thirds inflation, and the data cannot say which". Shipping a
coefficient that wide into a Gate is worse than shipping none, because it moves the
threshold by an amount nobody can bound.

**Alpha is not identifiable at the magnitude that matters.** Unchanged by the window
bug and still the load-bearing fact: at the drift rate that moves `SE` about 10%
over 60 days, per-cell power runs 0.078 to 0.206 with a median of 0.128, and **no
cell of 26 reaches 80%**. The efficient estimator is worth about 2.9x the
variogram's power there, which is why v2's "8%" described the moment estimator — and
why tripling it changes nothing.

**The long windows sit in the regime the boundary term distrusts.** A 200-day window
necessarily crosses an off-season. The season-boundary model finds 4 of 26 jump
terms excluding zero and **3 of those negative** — the random walk over-predicting
dispersion at long lags, which is what mean reversion looks like. Extrapolating a
within-season alpha linearly across those breaks is precisely the extrapolation that
evidence argues against, and it is where the largest impact numbers come from.

**Nothing can be validated out of sample.** Section 9.

Two of these got *stronger* when the bug was fixed, not weaker. The effect is
potentially large, and that makes the inability to measure it more serious, not less.

## 6. Calibration, and what it may be used for

On the shared cross-season window with real coverage (0.15 to 1.0 across 18 distinct
levels), `var(z)` rises with window age in **12 of 26** cells and the low-coverage
quartile is worse in **14 of 26**. Both are coin flips.

That is all this can support. The basis is in-sample, it decides xG existence from
the final extract, and it applies no point-in-time filter, so it uses information
that was not available at prediction time. **It is not evidence that the shipped
baseline is calibrated**, in production or out of sample. The point-in-time basis
yields no states at all and stays `NOT_IDENTIFIABLE`; nothing here substitutes for
that.

## 7. Confounding, jointly estimated

Home advantage and opponent identity are fitted as a joint two-way fixed-effects
model by alternating projections, and the whole two-stage procedure is resampled —
400 team-cluster replications, refitting both the fixed effects and the drift model
each time — so the interval carries the cost of having estimated the nuisance
parameters.

After adjustment, 5 of 26 cells have intervals excluding zero, and they include both
multiplicity survivors: `primeira_liga|attack` (7.74e-04 → 1.16e-03) and
`allsvenskan|attack` (8.40e-04 → 7.88e-04).

**What that permits me to say:** adjusting jointly for home advantage and opponent
identity does not remove the signal in those two cells, and their intervals still
exclude zero once the fixed-effect estimation is priced in.

**What it does not permit:** any claim that confounding has been ruled out.
Opponent identity is a proxy for opponent strength and is itself measured with
error; congestion, competition and personnel are not in the model at all. The 5 of
26 are per-cell intervals with no multiplicity correction applied, against about 1.3
expected under a null. "Confound-robust" and "the drift is about the team" are not
supportable and are withdrawn.

The first run of this analysis produced 25 of 26 survivors with bootstrap lower
bounds *above* their point estimates — the tell that something was wrong. A team
drawn twice had its rows merged into one series with duplicated timestamps, which
reads as instantaneous jumps. Recorded because the artefact would otherwise look
like it had always been sane.

## 8. Power provenance, checked rather than claimed

`EV_SE_DRIFT_V5_POWER.json` carries the same 26-cell study and a verification a
machine can re-run. `ev_se_v5_verify_power.py` recomputes one cell under the
canonical script, compares the two deterministic fields, and writes **both sides'
observed values** into the artefact beside the verdict: 12 comparisons, 0
mismatches. `seconds` is wall clock, is excluded by name, and now sits under
`timing_not_compared` so it cannot be mistaken for evidence again. `verified: true`
is written only by a tool that ran the comparison.

## 9. Three point-in-time verdicts, one cause

Under `captured_at <= as_of`, the filter `_xg_uncertainty_rows` itself applies, **no
epoch in the estimation period has three xG observations visible**; 0 of 18,978 rows
carry a capture time before 2026-07. So `missingness_beta_pit`, the PIT calibration
basis, and Path C are all `NOT_IDENTIFIABLE`.

The cause is absence, not corruption. Ordinary ingestion is first-write-wins behind
an immutability guard and never overwrites `captured_at` — a property the repository
already asserts in
`test_team_xg_match_preserves_first_visible_evidence`. The values simply were not in
the table before the 2026-07 backfill, so a replay finds nothing because there was
nothing. Only elapsed time changes that.

## 10. The four questions, answered directly

**Is the research package acceptable?** That is Codex's call, not mine. What I can
say is what changed: v4's load-bearing number was wrong by an order of magnitude and
is corrected; three overclaims are withdrawn; the window has one constructor and a
guard that has been observed to fail; and the power provenance is now a check rather
than an assertion.

**Are alpha and beta identifiable?** No. Alpha is not identifiable at the magnitude
that would matter — 0 of 26 cells reach 80% power there — although it is detectable
where it is large, in two cells after multiplicity correction. Beta is
`MISSINGNESS_NOT_IDENTIFIABLE` under a real point-in-time filter, which is a
stronger verdict than v3's "premise failed". Both stay `NULL`; zero is a claim that
the effect is absent and is not available as a way to write this.

**Is Contract 1 authorised?** No. Nothing in this package enters a production Gate,
unlocks Contract 1, or deploys. The evidence records that explicitly under
`authorisation`. Those are Owner decisions and this package makes none of them.

**Is point EV in scope?** No. It is out of scope by protocol §9 and this package
adjudicates nothing about it in either direction.

## 11. My independent opinion

I would keep the SE staleness direction paused, and I hold that more weakly than
v4 did, for a different reason.

v4 could say the effect was negligible. It is not. On the corrected window an age
term is a first-order change to `SE` in the cells where alpha is non-zero, which
means the *current* behaviour — production returning identical `SE` for a
one-day-old and a four-hundred-day-old window — is a live modelling gap rather than
a rounding error. I said the opposite in v4 and it was wrong.

What stops me recommending the term is not its size but its width: for two thirds of
the non-boundary cells the 95% band runs from zero to a large number. A Gate moved
by an unbounded amount is worse than a Gate not moved. And the largest impacts come
from windows crossing season breaks, which is exactly where the boundary evidence
says the linear model over-predicts.

So my ranking of what to do, in order of expected value:

1. **Treat production's age blindness as an open risk with a recorded decision**,
   not as a settled non-issue. This is a stronger recommendation than v4's, because
   the effect is larger than v4 believed. A fail-closed staleness *gate* needs no
   estimated coefficient, but the threshold cannot come from backtested performance
   under the standing rule, so it would need its own package and its own basis.
2. **Let point-in-time history accumulate.** From 2026-07 onward `captured_at` is
   usable, so beta and out-of-sample calibration become answerable around 2027-02.
   That is the only path that turns three `NOT_IDENTIFIABLE` verdicts into answers.
3. **Do not re-run the alpha estimate on more seasons alone.** Power at the relevant
   magnitude is a property of series length and spacing within a season; more
   seasons add cells, not resolution. If alpha is to be revisited, the useful change
   would be modelling mean reversion rather than a random walk — the boundary terms
   point that way — and that is a new protocol, not a re-run.
4. **Keep the strict-response invariants.** `age_term_inert` and
   `P3b_dispersion_response_inert` are the only checks that catch a formula ignoring
   an input entirely; that defect class appeared twice in unrelated rules.

I have low confidence in one thing worth flagging: whether the two surviving cells
generalise. They are two of 26, both in leagues with shorter seasons, one of them
withdrawn from production. I would not build anything on them.

## 12. Reproduction

Frozen extract SHA-256
`84ef81e90377014cb9ea9abc93276aebed65e1c63b9d4e5dfa18d47443634909`, 18,978 data
rows, at `/Users/liudehua/.hermes/data/ev_se_drift_v2/team_xg_match.csv`. Corpus
SHA-256 `80e49d1a32b5dd9653d41826e87415acff0d32a6804dea408f3b99737a6ab5e2`.

```bash
cd /Users/liudehua/.hermes/worktrees/w2-ev-se-variogram
export W2_XG_CSV=/Users/liudehua/.hermes/data/ev_se_drift_v2/team_xg_match.csv

python3 scripts/ev_se_v5_window.py                  # window self-check
python3 scripts/ev_se_v5_window.py --prove-it-fails  # negative control: guard must FAIL
python3 scripts/ev_se_v5_impact.py                   # cross-season impact
python3 scripts/ev_se_v5_confound.py                 # joint FE, ~10 min
python3 scripts/run_ev_se_drift_v5.py --emit         # ~8 min
python3 scripts/run_ev_se_drift_v5.py --check
python3 scripts/run_ev_se_drift_v5.py --self-test-check
python3 scripts/ev_se_v5_verify_power.py \
  --source docs/review_packages/EV_SE_DRIFT_V4/EV_SE_DRIFT_V4_POWER.json \
  --cell "allsvenskan|attack"
```

Earlier packages reproduce at their own commits, which is what frozen history means:

```bash
python3 scripts/run_ev_se_drift_v2.py --check                    # at HEAD
git worktree add --detach /tmp/w2-v3 e429bd97 && cd /tmp/w2-v3 && python3 scripts/run_ev_se_drift_v3.py --check
git worktree add --detach /tmp/w2-v4 5a40f448 && cd /tmp/w2-v4 && python3 scripts/run_ev_se_drift_v4.py --check
```

## 13. Ruff, mypy and tests

| Check | Scope | Result |
|---|---|---|
| `ruff check .` | whole repository | **All checks passed** |
| mypy strict | the 22 EV-SE scripts, named below | **0 errors in `scripts/`** |
| `mypy src apps` (the `make typecheck` gate) | `src`, `apps` | **2 errors — pre-existing**, identical at `b34eada9`; no `src/` or `apps/` file changed in v3, v4 or v5 |
| `run_ev_se_drift_v5.py --check` | v5 evidence | PASS |
| `run_ev_se_drift_v5.py --self-test-check` | v5 evidence | PASS; counts printed by the command |
| `ev_se_v5_window.py` | window self-check | PASS, spread ratio 3.174 |
| `ev_se_v5_window.py --prove-it-fails` | negative control | guard fires, 2 findings |
| `ev_se_v5_verify_power.py` | one cell, 2 fields, 6 grid points | 12 comparisons, 0 mismatches |
| `ev_se_v4_production_tests.py` | shipped EV-SE chain | exit 0, unchanged from v4 |
| `run_ev_se_drift_v2.py --check` | v2 evidence at HEAD | PASS |
| `test_team_xg_match_preserves_first_visible_evidence` | repository, pre-existing | 1 passed |
| `pytest` on the bound production paths | 4 files | 54 passed |

The exact mypy file list: `_load`, `ev_se_drift_alpha`, `ev_se_variogram`,
`ev_se_mle`, `ev_se_v2_gates`, `ev_se_beta_kappa`, `ev_se_v3_power`,
`ev_se_v3_confound`, `ev_se_v3_calibration`, `ev_se_v3_production_tests`,
`run_ev_se_drift_v3`, `ev_se_v4_power`, `ev_se_v4_calibration`,
`ev_se_v4_production_tests`, `ev_se_v4_impact`, `ev_se_v4_freeze_power`,
`run_ev_se_drift_v4`, `ev_se_v5_window`, `ev_se_v5_confound`, `ev_se_v5_impact`,
`ev_se_v5_verify_power`, `run_ev_se_drift_v5`. `mypy scripts/` as a directory
cannot be used: `scripts/run_prematch_refresh.py` trips a pre-existing
module-name collision that stops the run before anything is checked.

The full 2,912-test suite was not run. 54 were, covering the paths this work binds
to; no `src/` or `apps/` file was changed, so nothing else is expected to move.

## 14. Remaining uncertainty

1. **The two surviving cells may not generalise.** Two of 26, both leagues with
   shorter seasons, one of them withdrawn from production. Reported, not built on.
2. **The confound adjustment is not a clean bill.** Opponent identity proxies
   opponent strength with error; congestion, competition and personnel are absent.
   The 5 of 26 adjusted intervals excluding zero carry no multiplicity correction.
3. **Out-of-sample calibration does not exist** and will not until enough
   post-2026-07 point-in-time history accumulates.
4. **The mean-reversion reading of the boundary terms is suggestive only.** 4 of 26
   exclude zero against 1.3 expected, 3 of them negative. It is the reason I distrust
   the largest impact numbers, and it is not established.
5. **`raw_payload_sha256` is a placeholder in the behavioural harness**, because the
   frozen extract selected seven columns. It makes production more permissive, so a
   blocked verdict stays conservative.
6. **The full test suite was not run.**

## 15. Commit chain

`b34eada9` v2 · `603a9753`…`e429bd97` v3 · `18f812b7`…`5a40f448` v4 ·
`4558f5ab` v5 protocol, frozen before results.
