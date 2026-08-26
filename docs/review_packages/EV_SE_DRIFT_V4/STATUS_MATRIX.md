# v4 protocol — clause-by-clause status matrix

Protocol `18f812b7`. Every `DONE` row names an artefact that exists on disk; the
matrix was checked against `ls` rather than against intent, which is the failure
v3 was rejected for. Rows that are not finished say so.

Legend: **DONE** implemented and in a file that exists · **BLOCKED** cannot be done
with the data that exists, reason recorded · **PARTIAL** implemented with a stated
deviation · **IN PROGRESS** running, artefact not yet present.

## Section 1 — v3 findings independently reproduced

| Finding | Verdict | Evidence |
|---|---|---|
| 1 Power marked DONE while artefact absent | CONFIRMED | `EV_SE_DRIFT_V3_POWER.json` never existed; run was 44/156 |
| 2 `kappa` not point-in-time | CONFIRMED, verdict changes | PIT filter gives zero usable epochs → `MISSINGNESS_NOT_IDENTIFIABLE` |
| 3 Mutants simulated on a local wrapper | CONFIRMED | violated v3 §10; 3 of 5 are not expressible in production |
| 4 Calibration reset by season, coverage ≡ 1.0 | CONFIRMED | v3 artefact had exactly one distinct `mean_coverage` value |
| 5 Write semantics described backwards | CONFIRMED, v3 was wrong | `upsert_team_xg_matches` is first-write-wins behind an immutability guard |
| 6a Boundary critical value used as a 95% CI | CONFIRMED | both intervals now emitted with their meanings |
| 6b Bootstrap resampled team-seasons | CONFIRMED | `cluster_bootstrap` now resamples teams |
| 6c `chi^2` direction stated backwards | CONFIRMED, v3 was wrong | naive `chi^2_1` halves the size; it is conservative |
| 7 7.9% figure had no artefact | CONFIRMED | now `EV_SE_DRIFT_V4_IMPACT.json`, and the number is 7.88% max / 1.54% median |
| 8 Ruff, mypy, field count, commit chain | CONFIRMED | 8 ruff + 33 mypy; 1,217 fields quoted as 1,165; head was `e429bd97` |
| 9 Zero used to mean unset | CONFIRMED | recommendation rewritten; `parameter_state` encodes NULL |

## Section 3 — estimator, carried forward unchanged

| Clause | Status | Where |
|---|---|---|
| Local level model, exact Gaussian likelihood, diffuse level | DONE | `ev_se_mle.loglik` |
| Nelder-Mead, pure stdlib, deterministic | DONE | `_nelder_mead` |
| Point estimates unchanged from v3 | DONE | identical `sigma2_alpha_abs` in both evidence files |
| Variogram comparator retained | DONE | `variogram_comparator` per cell |
| v1 retained | DONE | `scripts/ev_se_drift_alpha.py`, unmodified |

## Section 4 — corrected inference semantics

| Clause | Status | Where |
|---|---|---|
| Mixture p-value `0.5*P(chi^2_1 > LR)` | DONE | `lrt_pvalue` |
| `chi^2_1` direction stated correctly wherever it appears | DONE | module docstring, protocol §4, report §2 |
| `boundary_region_95` with its meaning | DONE | per cell, critical value emitted |
| `profile_ci_95` with its meaning | DONE | per cell, critical value emitted |
| Neither called "the" interval | DONE | both carry a `meaning` string |
| Boundary optima flagged | DONE | `optimum_at_boundary`, true in 11 of 26 |
| Bootstrap resamples teams | DONE | `cluster_bootstrap`, `resampling_unit: team` |
| 200 reps stated, not disguised | DONE | in the field name and the `meaning` string |
| v3 bootstrap retained so v3 reproduces | DONE | `cluster_bootstrap_by_team_season`, marked deprecated |

## Section 5 — missingness as a PIT question

| Clause | Status | Where |
|---|---|---|
| `E` = latest 20 expected fixtures across seasons, no reset | DONE | `ev_se_beta_kappa.states` |
| `O` filtered by `captured_at <= as_of` | DONE | `states(pit=True)` |
| `MISSINGNESS_NOT_IDENTIFIABLE` when no admissible measurement | DONE | `missingness_beta_pit`, zero usable epochs |
| Verdict distinct from `MISSINGNESS_PREMISE_FAILED` | DONE | separate status values, v3's relabelled |
| v3 static computation retained, relabelled | DONE | `missingness_beta_static_diagnostic` |

## Section 6 — calibration on production semantics

| Clause | Status | Where |
|---|---|---|
| Latest 20 by kickoff across seasons, no season reset | DONE | `ev_se_v4_calibration._expected_timelines` |
| Coverage `\|O\|/\|E\|` from the expected corpus | DONE | ranges 0.15–1.0, was 1.0 in v3 |
| `static` and `pit` bases computed, never mixed | DONE | separate top-level keys |
| PIT reports NOT_IDENTIFIABLE rather than falling back | DONE | `pit_basis.status` |
| No fabricated holdout | DONE | the static basis is labelled in-sample |
| Baseline column coefficient-free | DONE | uses only `SE0` and `tau^2` |
| Candidate column declared circular | DONE | `candidate_is_circular` |

## Section 7 — power, size, and the three populations

| Clause | Status | Where |
|---|---|---|
| Representative geometry from a committed script | DONE | `ev_se_v4_impact.py` → `EV_SE_DRIFT_V4_IMPACT.json` |
| Production-state age distribution | DONE | same artefact, `production_state_ages` |
| Operational impact from a committed script | DONE | same artefact, `age_term_operational_impact` |
| Three populations named, never averaged together | DONE | `populations_are_never_mixed` |
| Per-cell real-geometry power, frozen | **IN PROGRESS** | `scripts/ev_se_v4_power.py`; artefact absent until the run completes |
| Evidence carries the power artefact's SHA-256 | DONE | `external_artefacts.power_per_cell`, `present` currently false |

The per-cell row is deliberately not `DONE`. The evidence file reports
`present: false` for that artefact, so the matrix, the evidence and the filesystem
agree while the run is unfinished — which is the property v3 lacked.

## Section 8 — behavioural tests, classified

| Clause | Status | Where |
|---|---|---|
| Production behaviour measured on its own | DONE | `production_behaviour`, no candidate involved |
| `PRODUCTION_EXPRESSIBLE` mutants injected into real methods | DONE | 3 mutants patched into `_xg_standard_error`, all killed |
| `NOT_EXPRESSIBLE_IN_PRODUCTION` reported, not scored | DONE | 3 mutants, `scored: false`, reasons recorded |
| `RESEARCH_CANDIDATE_ONLY` labelled as research | DONE | separate block with its own note |
| Supplementary strict-response checks | DONE | `age_term_inert`, and `P3b_dispersion_response_inert` added after a constant-SE mutant survived |
| 1e-6 mutation makes `--check` exit non-zero | DONE | `--self-test-check`, deterministic sampling |

## Section 9 — form and boundary

| Clause | Status | Where |
|---|---|---|
| `alpha_rel` per league with the `SE0^2` spread | DONE | `form_mismatch` |
| Cross-season jump term | DONE | `season_boundary`, 26 of 26 identified |

## Section 10 — null is not zero

| Clause | Status | Where |
|---|---|---|
| Coefficients recorded as NULL | DONE | `parameter_state`, both `null` |
| Encoding rule written down | DONE | `parameter_state.encoding_rule` |
| No recommendation unlocks a contract or deployment | DONE | report §8 states the decision is the Owner's |

## Section 11 — deliverables

| Deliverable | Status |
|---|---|
| Report | DONE — `REPORT.md` |
| Status matrix matching the files that exist | DONE — this file |
| Frozen evidence JSON | DONE — `EV_SE_DRIFT_V4_EVIDENCE.json` |
| Frozen power artefact | IN PROGRESS |
| Frozen operational-impact artefact | DONE — `EV_SE_DRIFT_V4_IMPACT.json` |
| Reproduction commands | DONE — report §9 |
| Ruff / mypy / test results | DONE — report §10 |
| Explicit list of what remains open | DONE — report §11 |
| Independent opinion on SE, research, point EV | DONE — report §8 |

## Section 12 — constraints

| Constraint | Status |
|---|---|
| No settled profit, hit rate, or the 65 picks | HELD — no outcome table read |
| No threshold picked from a backtest | HELD — no backtest run |
| Provider 0 | HELD |
| Production writes 0 | HELD |
| GitHub 0 / GHCR 0 | HELD |
| No deployment | HELD |
| Formal / Lock / Production / Real money stay off | HELD — untouched; no `src/` or `apps/` change in this work |
| Local verification never written up as shipped | HELD — report §8 states nothing is shipped |
| Production reads under repeatable-read read-only | HELD — no production read performed; all inputs are frozen local artefacts |

## Known deviations

1. **Bootstrap at 200 replications, not 10,000.** Fixed in protocol v4 §4 before
   the run, reported in the field name, and never the primary interval.
2. **`--self-test-check` samples 41 of the numeric fields.** Sampling is
   deterministic (`paths[::step]`), so the set is reproducible; the exact counts are
   printed by the command rather than quoted from memory.
3. **Calibration `static` basis is in-sample.** Forced by the PIT block, labelled in
   the artefact, and only its coefficient-free baseline column is interpreted.
4. **`raw_payload_sha256` is a placeholder in the behavioural harness.** The frozen
   extract selected seven columns and omitted it. A valid placeholder makes
   production more permissive, so a blocked verdict stays conservative.
5. **mypy is not clean on `scripts/`.** The project gate is `make typecheck`, which
   runs `mypy src apps` and does not cover `scripts/`. That gate is unaffected by
   this work, which changed no `src/` or `apps/` file. Exact counts in report §10.
6. **The per-cell power run was started under `scripts/ev_se_v3_power.py`.** v4 §7
   carries the computation forward verbatim, and `scripts/ev_se_v4_power.py --only
   <cell>` re-runs a single cell so the equivalence is checked rather than asserted.
