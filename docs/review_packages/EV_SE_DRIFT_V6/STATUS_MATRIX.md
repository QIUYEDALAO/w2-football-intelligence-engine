# v6 protocol — clause-by-clause status matrix

Protocol `b74766f9`. Every `DONE` row names a file that exists and a field inside
it. Rows that are not finished say so; no clause is marked done because it was
attempted.

## Section 1 — v5 findings independently reproduced

| Finding | Verdict | Evidence |
|---|---|---|
| 1 Epochs conditioned on the target later having xG | CONFIRMED, **and a second condition found** | 872 epochs lost to target conditioning; a further **5,082** lost to an implicit full-20-row window that v5 sliced as `series[i-20:i]`. Production fails closed below **three** rows, not twenty. Together they reconcile exactly to v5's 8,578 against 14,290 |
| 2 Two constructors, one claim; guard blind to it | CONFIRMED | `ev_se_v6_epochs` is now the single epoch source, with a guard per regression |
| 3 §4 promised a bootstrap p-value, shipped none | CONFIRMED | `share_at_boundary` is not a p-value; a null parametric bootstrap now supplies one |
| 4a "10 of 15" | CONFIRMED — it is **12 of 15** | `non_boundary_cells_whose_band_reaches_zero` |
| 4b "more seasons add cells, not resolution" | CONFIRMED wrong | cells are fixed; series inside them are not, and the likelihood accumulates over series |

## Section 3 — the authoritative epoch population

| Clause | Status | Where |
|---|---|---|
| Epoch = (team, finished fixture) at kickoff | DONE | `ev_se_v6_epochs.analysis_epochs` |
| Window = latest 20 xG rows, `kickoff < as_of`, across seasons | DONE | same |
| PIT basis adds `captured_at <= as_of` | DONE | `pit=True` |
| Admitted at ≥3 rows with positive variance | DONE | matches `_xg_standard_error`'s fail-closed |
| Target xG is **not** an admission rule | DONE | `require_target_xg` exists only for the negative control |
| Calibration may restrict, and reports the count | DONE | `epochs_with_target_xg` per cell |
| Admission ledger with per-reason counts | DONE | `admission_ledger`: 33,450 candidates → 14,290 admitted |

## Section 4 — three guards, each watched to fail

| Regression | Guard fires | Where |
|---|---|---|
| season reset | YES | `season_reset_indistinguishable_from_production_population` |
| target-xG conditioning | YES | `target_xg_conditioning_indistinguishable_from_production` |
| future capture leak | YES | `pit_basis_admits_as_many_epochs_as_one_ignoring_captured_at` |
| all three demonstrated, not asserted | DONE | `--prove-it-fails`, `all_guards_bite: true` |

## Section 5 — the confound p-value

| Clause | Status | Where |
|---|---|---|
| Joint two-way fixed effects | DONE | carried from v5, `fit_effects` |
| Parametric bootstrap under the null | DONE | `EV_SE_DRIFT_V6_CONFOUND.json`, `null_bootstrap.construction` |
| Both stages refitted per replicate | DONE | FE and drift refitted on every null replicate |
| `p = (1 + #{≥ observed}) / (1 + reps)` | DONE | `bootstrap_p_value` |
| 400 replications, seed 20260826 | DONE | `replications`, `seed` |
| Percentile interval retained, not called a p-value | DONE | `percentile_interval.note` |
| `share_at_boundary` not renamed | DONE | kept under its own name on both the observed and null sides |
| Unmet clauses reported rather than substituted | DONE — none unmet | — |

Both artefacts now exist and the evidence carries their SHA-256s with
`present: true`.

A limit of the construction is recorded rather than hidden: with 400 replications the
smallest attainable p is `1/401 = 0.0025`, while Bonferroni across 26 tests needs
`0.00192`. **No cell can clear Bonferroni at this replication count however strong
the signal.** `bonferroni_is_attainable: false` says so in the artefact.

## Section 6 — what waiting buys, measured

| Clause | Status | Where |
|---|---|---|
| Power repeated at series scale {1,2,4,8} | DONE | `EV_SE_DRIFT_V6_SCALING.json`, 26 cells × 4 scales × 500 replications |
| At the rate that moves SE ~10% over 60 days | DONE | `sigma2: 1e-4` |
| Same real geometry | DONE | series replicated from each cell's own timestamps |
| Report the multiple reaching 80%, or that none does | DONE | none does; `cells_reaching_80pc_within_range: []`, report §5 |

## Section 7 — recomputation

| Artefact | Status |
|---|---|
| Production state ages | DONE — refrozen on the section 3 population |
| `SE0^2` distribution | DONE — now spans 3-to-20-row windows, not only full ones |
| `form_mismatch` | DONE — recomputed from the same quantiles |
| Operational impact | DONE — max 84.91%, median 11.42% |
| Alpha estimates, power study, behavioural results | UNCHANGED — not re-derived, as the protocol states |

## Section 8 — carried forward

| Clause | Status |
|---|---|
| Estimator and inference semantics (v4 §3–§4) | DONE — same point estimates since v3 |
| Missingness as a PIT question (v4 §5) | DONE — `MISSINGNESS_NOT_IDENTIFIABLE` |
| Calibration claim limits (v5 §5) | DONE — in-sample only, stated in the artefact |
| Power provenance (v5 §6) | DONE — `EV_SE_DRIFT_V5_POWER.json`, verified by comparison |
| Statistical statement discipline (v5 §7) | DONE — FWER and FDR stated precisely |
| Behavioural test classification (v4 §8) | DONE — `ev_se_v4_production_tests.py`, unchanged |

## Section 9 — constraints

| Constraint | Status |
|---|---|
| α/β NULL, never 0 | HELD — `parameter_state.encoding_rule` |
| No Gate, no Contract 1, no production formula, no deploy | HELD — `authorisation`, all false |
| Provider 0 / production reads 0 / writes 0 | HELD — every input is a frozen local artefact |
| GitHub 0 / GHCR 0 | HELD |
| Formal / Lock / Production / Real-money untouched | HELD — no `src/` or `apps/` change since v2 |
| No settled profit, hit rate, or the 65 picks | HELD |
| Point EV out of scope | HELD — report §10 |
| v2–v5 history unmodified | HELD — each still reproduces at its own commit |

## Known deviations

1. **Confound bootstrap at 400 replications**, which caps the smallest p at 0.0025
   and puts Bonferroni out of reach. Recorded in the artefact, not worked around.
2. **The confound is a separate frozen artefact**, not inlined in the evidence: its
   null bootstrap is a fifteen-minute run and `--check` would carry it twice. It is
   referenced by SHA-256.
3. **Calibration remains in-sample.** The PIT basis yields no states.
4. **`raw_payload_sha256` is a placeholder in the behavioural harness.** It makes
   production more permissive, so a blocked verdict stays conservative.
5. **`mypy src apps` fails on two pre-existing `src/` errors**, identical at
   `b34eada9`.
6. **The scaling study extrapolates by replicating existing series**, so it assumes
   future seasons resemble observed ones in length and spacing. It does not model
   changes in fixture calendars or coverage.
