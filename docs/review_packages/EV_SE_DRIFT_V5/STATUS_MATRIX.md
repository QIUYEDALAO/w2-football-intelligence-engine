# v5 protocol — clause-by-clause status matrix

Protocol `4558f5ab`. Every `DONE` row names a file that exists; the matrix was
checked against `ls` and against the emitted evidence, not against intent.

## Section 1 — v4 findings independently reproduced

| Finding | Verdict | Evidence |
|---|---|---|
| 1 Impact window reset by season | CONFIRMED, **and wider than reported** | the same defect sat in `se0_squared_quantiles`, feeding `form_mismatch` and the impact figure |
| 2 Sequential demeaning, no nuisance uncertainty | CONFIRMED | `_centre` ran one backfitting pass; residuals fed forward as data |
| 3 Static in-sample calibration offered as baseline calibration | CONFIRMED | claim withdrawn, report §6 |
| 4 `verified: true` from a flag; `seconds` in a "bit for bit" record | CONFIRMED | `verified: verified is not None`; grid carried `seconds` |
| 5 Bonferroni/BH gloss, existing test, mypy scope | CONFIRMED | test exists at `test_future_refresh_db_persistence.py:1887` and passes |

## Section 2 — the conclusion that had to be re-derived

| Item | Status | Where |
|---|---|---|
| Age span under production's window | DONE — 55–180 days, was 5.9–28.2 | `EV_SE_DRIFT_V5_IMPACT.json` |
| Impact under production's window | DONE — max 49.07%, median 7.31% | same artefact |
| v4's "too small to notice" withdrawn | DONE | report §1 and §5 |
| Recommendation re-derived, not defended | DONE | report §5 and §11 |
| Alpha estimates and power stated as unaffected | DONE | report §1, closing paragraph |

## Section 3 — one window constructor, with a guard

| Clause | Status | Where |
|---|---|---|
| Single shared constructor | DONE | `ev_se_v5_window`; impact, calibration and `se0` quantiles all call it |
| No season key in the production timeline | DONE | `observed_timelines` takes no season argument |
| Self-check fails on a season reset | DONE | `self_check`, ratio 3.17 |
| The guard has been observed to fail | DONE | `--prove-it-fails` injects the regression, 2 findings |
| Self-check embedded in the evidence | DONE | `window_self_check`, result PASS |

## Section 4 — confounding, joint and bootstrapped

| Clause | Status | Where |
|---|---|---|
| Joint two-way fixed effects | DONE | `joint_two_way_residuals`, alternating projections to `1e-10` |
| Whole two-stage procedure resampled | DONE | 400 team-cluster reps, both stages refitted |
| Nuisance uncertainty priced in | DONE | intervals widen; 5 of 26 exclude zero, was "all robust" |
| Claim discipline honoured | DONE | "confound-robust" and "about the team" withdrawn, report §7 |
| Limitations named | DONE | opponent as noisy proxy; congestion, competition, personnel absent |

## Section 5 — calibration claim limits

| Clause | Status | Where |
|---|---|---|
| Both bases on the section 3 window | DONE | `coverage_states`, coverage 0.15–1.0 across 18 levels |
| `static` described only as in-sample diagnostic | DONE | `what_this_may_be_used_for` in the evidence |
| Not offered as baseline calibration | DONE | report §6 |
| PIT stays `NOT_IDENTIFIABLE`, no substitution | DONE | `pit_basis.status` |

## Section 6 — power provenance

| Clause | Status | Where |
|---|---|---|
| Compared fields named | DONE | `compared_fields`, `excluded_fields` |
| `seconds` excluded and moved | DONE | `timing_not_compared` |
| Both sides' values written into the artefact | DONE | `comparisons`, 12 entries |
| `verified` written only after a comparison | DONE | `mismatches == 0` gates it |
| Supersession of v4's claim recorded | DONE | `equivalence_check.supersedes` |

## Section 7 — statistical statements

| Clause | Status | Where |
|---|---|---|
| Bonferroni stated as FWER | DONE | evidence `bonferroni_meaning`, report §4 |
| BH stated as FDR, expected proportion | DONE | evidence `benjamini_hochberg_meaning` |
| Neither glossed as a posterior | DONE | both say so explicitly |
| Existing first-write test acknowledged | DONE | report §2 and §9; the v4 next-step is withdrawn |
| mypy scope and result consistent | DONE | report §13 names the exact 22-file list and why `mypy scripts/` cannot be used |

## Section 8 — carried forward from v4

| Clause | Status |
|---|---|
| Estimator, boundary mixture, both intervals, team bootstrap | DONE — unchanged, same point estimates |
| Missingness as a PIT question | DONE — `MISSINGNESS_NOT_IDENTIFIABLE` |
| Behavioural test classification | DONE — `ev_se_v4_production_tests.py` unchanged and passing |
| Null is not zero | DONE — `parameter_state`, both `null` |

## Section 9 — constraints

| Constraint | Status |
|---|---|
| α/β encoded as NULL, never 0 | HELD — `parameter_state.encoding_rule` |
| No production Gate, no Contract 1, no deploy | HELD — `authorisation`, all three `false` |
| Provider 0 / production reads 0 / writes 0 | HELD — every input is a frozen local artefact |
| GitHub 0 / GHCR 0 / no deployment | HELD |
| Formal / Lock / Production / Real-money off | HELD — no `src/` or `apps/` change in v3, v4 or v5 |
| No settled profit, hit rate, or the 65 picks | HELD |
| Point EV not adjudicated | HELD — report §10 |

## Known deviations

1. **Confound bootstrap at 400 replications**, fixed in protocol §4 before the run.
2. **`--self-test-check` samples deterministically**, `paths[::step]`; counts are
   printed by the command rather than quoted.
3. **Calibration `static` basis is in-sample**, forced by the PIT block and labelled
   as such in the artefact; only its coefficient-free baseline column is read.
4. **Power numbers were produced by `scripts/ev_se_v3_power.py`.** The computation
   is unchanged across v3, v4 and v5; the equivalence is verified per section 6
   rather than asserted.
5. **`raw_payload_sha256` is a placeholder in the behavioural harness**, because the
   frozen extract selected seven columns. It makes production more permissive, so a
   blocked verdict stays conservative.
6. **`mypy src apps` fails on two pre-existing `src/` errors.** Identical at
   `b34eada9`; no `src/` or `apps/` file was changed in this work.

## Corrections made inside v5 itself

Two defects were found by v5's own controls rather than by review, and both are
recorded in the report:

1. The `--prove-it-fails` negative control initially reported a pass while injecting
   nothing, because it patched a second module object created by `import` while the
   file ran as `__main__`.
2. The confound bootstrap initially returned 25 of 26 survivors with lower bounds
   above their point estimates, because a team drawn twice had its rows merged into
   one series with duplicated timestamps.
