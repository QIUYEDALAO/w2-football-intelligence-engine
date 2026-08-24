# EV SE offline preregistration baseline — 2026-08-23

Status: `OWNER_ITEMS_1_2_DECIDED / ITEM_3_FORMULA_FAMILY_DRAFTED / COEFFICIENTS_UNSET / PRODUCTION_IMPLEMENTATION_GATED`

## Execution boundary

- Exact production release observed: `d05ab74217e37af2e85732ac3a63ee4d9e214aa1`.
- Exact production schema: `0070_notification_delivery_routing`.
- Evidence observed at: `2026-08-23T12:00:50Z`.
- Provider calls / production database writes / outcomes read: `0 / 0 / 0`.
- No model, threshold, Scheduler, notification, deployment, or runtime configuration changed.

This document preregisters the problem and behavioral acceptance conditions and records the Owner's Contract 1 semantic decision plus the approved persisted-saved-raw denominator authority. Item 3 is thawed only far enough to draft a coefficient-free formula family. No coefficient, final SE formula, production implementation, or release is approved. Reproduction is defined in `README.md`; every numeric field below is rendered by `scripts/audit_ev_se_offline_preregistration.py`.

## Binding non-claims

- Do not claim that stale xG raises EV. That causal claim failed its prior test.
- Do not use profit, loss, hit rate, or the current 65 settled picks to choose an uncertainty coefficient.
- Do not introduce or backtest-select an age cutoff or EV ceiling.
- The target is epistemic: `ev_se` claims to express uncertainty about the current match lambdas. The current formula treats old and recent source matches as exchangeable conditional on observed values and sample size; that stationarity assumption requires an explicit test and policy.

## Reproduction predicate and row-count lineage

`usable` means: both EV fields are numeric, `ev_se >= 0`, `COALESCE(recorded_at, evaluated_at) <= 2026-08-23T12:00:50Z`, the API-Football fixture identity resolves, both xG sides obey `kickoff_at < evaluated_at` and `captured_at <= evaluated_at`, visible rows are capped at 20, both sides have `n >= 3`, and age plus both reconstructed sigmas are non-null.

The four counts are different cohorts:

- `2564`: handoff snapshot rows with an `ev_se` value.
- `2528`: the handoff's age-correlation subset; it is not the handoff EV-SE count and cannot be compared as if it were.
- `2603`: this preregistration's frozen usable cohort at `2026-08-23T12:00:50Z`.
- `2653`: Owner's later unbounded live recount. Its extra `50` rows arrived after the frozen cutoff; row 2604 was recorded at `2026-08-23T12:01:12.133049Z` and row 2653 at `2026-08-23T12:38:09.196654Z`.

The handoff minimum `0.0296` was `0.029576` rounded to four decimals. The new `0.028387` row was evaluated at `2026-08-23T11:48:53Z` and recorded at `2026-08-23T11:49:13.927694Z`. The minimum changed because a new evaluation entered after the handoff snapshot, not because the filter changed.

## Code facts frozen before model design

### 1. Meaning of the existing `0.5`

The lambda point estimate uses:

```text
base_home = (home_xg_for + away_xg_against) / 2
base_away = (away_xg_for + home_xg_against) / 2
total     = clamp(base_home + base_away)
delta     = base_home - base_away + non-xG adjustments
lambda_home = (total + delta) / 2
lambda_away = (total - delta) / 2
```

When the total and final lambdas are inside their clamp boundaries, this simplifies to:

```text
lambda_home = base_home + constant / 2
lambda_away = base_away - constant / 2
```

Therefore the local Jacobian of each lambda with respect to each of its two xG means is `0.5`, and independent-error propagation gives:

```text
sigma_home = 0.5 * sqrt(SE(home attack)^2 + SE(away defence)^2)
sigma_away = 0.5 * sqrt(SE(away attack)^2 + SE(home defence)^2)
```

Conclusion: `0.5` is not an arbitrary gate discount in the unclamped interior. It is the derivative of the existing arithmetic-mean lambda estimator. The July design document recorded this formula but did not record the derivation.

The coefficient is only piecewise valid. A total clamp or final-lambda clamp changes the Jacobian. In the `157` frozen model captures, `156` base totals were inside `[1.35, 4.40]`; `1` was above `4.40` and `0` was below `1.35`. Any future uncertainty implementation must propagate through the actual piecewise calibration path rather than silently applying one global coefficient at clamp boundaries.

### 2. Owner decision 1 — Contract 1 is approved as a semantic contract

The EV-SE nodes use `0.25 / 0.50 / 0.25`, so effective SD is `0.7071 sigma`. Simulation uses `0.158655 / 0.68269 / 0.158655`, so effective SD is `0.5633 sigma`; their ratio is `1.2553`. Both paths also floor the lower node at `max(mu - sigma, 0.01)`, which further compresses dispersion as `mu - sigma` approaches zero.

Owner selected **Contract 1: `lambda_sigma` is the true standard deviation of the lambda distribution**. This approval is semantic only. It does not approve the current SE formula, any coefficient, production code, or release.

The reference discretization is GH-3: standardized nodes `-sqrt(3), 0, +sqrt(3)` and weights `1/6, 2/3, 1/6`. Its discrete moments are `m0=1, m1=0, m2=1, m3=0, m4=3`, matching a standard normal through degree four. At an interior point where the `0.01` floor does not fire, its effective SD is therefore exactly `sigma`. The old paths match neither the required second moment nor each other.

## EV-SE-EXEC-05 — frozen GH-3 impact

The approved Contract 1 comparison is pinned to local Git object `3fb17ced5dbefa6201bad164556940d8894bb9b2` / `docs/review_packages/EV_SE_OFFLINE_VALIDATION/EV_SE_OFFLINE_PREREGISTRATION_EVIDENCE_20260823.json` with SHA-256 `62e4c0baed196b865d468e3d0a9f34351bef3f187db5b4607e178d6e8412e55f`. The old mutable `team_xg_match` merge path later changed the current reconstruction to `2576` accepted rows and added `8` exclusions. Those IDs are recorded in JSON. The script preserves the approved cohort instead of choosing a historical raw capture by fitting reported `ev_se`.

Of the `2,603` usable evaluations, `5` were excluded because their model-input group contains only one market, so both point lambdas cannot be identified from the frozen five-state distributions. That leaves `2,598` identifiable evaluations in `1,068` groups before the baseline-reproduction gate.

The frozen dynamic read model does not retain the original lambda sigmas. Current PIT input reconstruction failed to reproduce old reported `ev_se` within `0.000001` for `14` evaluations / `7` whole model-input groups across `4` fixtures. The script excludes those groups instead of back-solving sigma from the answer. Their exact evaluation IDs, timestamps, inputs, reported values, reconstructed values, and residuals remain in the JSON. The actual old-versus-GH-3 comparison therefore uses the same `2,584` evaluations in `1,061` groups on both sides. Prices came from the payload for `2,106` comparison rows and were algebraically recovered from current EV plus the five-state distribution for `478` rows.

Lambda reconstruction is outcome-free. It fits the two point lambdas to the frozen AH/TOTALS five-state distributions with `rho=0` and the existing 13x13 matrix. Maximum absolute distribution-probability error is `0.000000`; maximum point-EV reconstruction residual is `0.000001`. Before the baseline gate, maximum old reported `ev_se` reconstruction residual is `0.057594`; inside the accepted comparison cohort it is `0.000001`.

| Consumer / measurement | mean delta GH-3 minus old | p05 / median / p95 | min / max | max absolute |
|---|---:|---:|---:|---:|
| analysis-evidence reported point EV | `+0.000000` | `+0.000000 / +0.000000 / +0.000000` | `+0.000000 / +0.000000` | `0.000000` |
| analysis-evidence internal quadrature mean EV | `-0.000320` | `-0.001760 / -0.000251 / +0.000679` | `-0.004681 / +0.002518` | `0.004681` |
| analysis-evidence `ev_se` | `+0.022056` | `+0.016598 / +0.020762 / +0.035729` | `+0.011775 / +0.049328` | `0.049328` |
| simulation mixed-score EV | `-0.000437` | `-0.002405 / -0.000343 / +0.000931` | `-0.006423 / +0.003496` | `0.006423` |

The reported analysis-evidence point EV stays unchanged because `_lambda_scenarios` only computes `ev_se`; the internal quadrature mean is reported separately so the weighting effect is still visible.

## EV-SE-EXEC-06 — price-source stratification

The baseline gate lineage is source-specific. `DERIVED_FROM_CURRENT_EV_AND_FIVE_STATE_DISTRIBUTION` has `492` attempted identifiable evaluations, `478` accepted, and `14` excluded. Its true failure rate among attempted rows is `2.8455%`; `14 / 478 = 2.9289%` is the excluded-to-accepted ratio, not the attempted-row failure rate. `PAYLOAD_DECIMAL_ODDS` has `2106` attempted, `2106` accepted, and `0` excluded. This records the observed concentration without changing any of the 14 exclusions.

| price source | comparison measurement | n | min | p05 | p25 | median | mean | p75 | p95 | max | max absolute |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `DERIVED_FROM_CURRENT_EV_AND_FIVE_STATE_DISTRIBUTION` | reported point EV delta | `478` | `+0.000000` | `+0.000000` | `+0.000000` | `+0.000000` | `+0.000000` | `+0.000000` | `+0.000000` | `+0.000000` | `0.000000` |
| `DERIVED_FROM_CURRENT_EV_AND_FIVE_STATE_DISTRIBUTION` | internal quadrature mean EV delta | `478` | `-0.004681` | `-0.003386` | `-0.000961` | `-0.000320` | `-0.000412` | `+0.000486` | `+0.002253` | `+0.002518` | `0.004681` |
| `DERIVED_FROM_CURRENT_EV_AND_FIVE_STATE_DISTRIBUTION` | ev_se delta | `478` | `+0.015113` | `+0.017721` | `+0.019871` | `+0.023259` | `+0.027423` | `+0.036258` | `+0.043939` | `+0.049328` | `0.049328` |
| `DERIVED_FROM_CURRENT_EV_AND_FIVE_STATE_DISTRIBUTION` | mixed-score-matrix EV delta | `478` | `-0.006423` | `-0.004631` | `-0.001313` | `-0.000436` | `-0.000561` | `+0.000665` | `+0.003135` | `+0.003496` | `0.006423` |
| `PAYLOAD_DECIMAL_ODDS` | reported point EV delta | `2106` | `+0.000000` | `+0.000000` | `+0.000000` | `+0.000000` | `+0.000000` | `+0.000000` | `+0.000000` | `+0.000000` | `0.000000` |
| `PAYLOAD_DECIMAL_ODDS` | internal quadrature mean EV delta | `2106` | `-0.002770` | `-0.001261` | `-0.000687` | `-0.000237` | `-0.000299` | `+0.000127` | `+0.000609` | `+0.001044` | `0.002770` |
| `PAYLOAD_DECIMAL_ODDS` | ev_se delta | `2106` | `+0.011775` | `+0.016311` | `+0.018628` | `+0.020617` | `+0.020838` | `+0.022630` | `+0.026168` | `+0.034009` | `0.034009` |
| `PAYLOAD_DECIMAL_ODDS` | mixed-score-matrix EV delta | `2106` | `-0.003793` | `-0.001725` | `-0.000940` | `-0.000323` | `-0.000408` | `+0.000174` | `+0.000836` | `+0.001428` | `0.003793` |

The reporting-only materiality rule is fixed before interpreting the layers: a difference is material when either the absolute mean gap or the largest absolute `p05/p25/median/p75/p95` gap is at least `0.20` pooled within-source SD. This is a descriptive reporting criterion, not a model gate, coefficient, or outcome-derived threshold. For `ev_se_delta_gh3_minus_old`, the absolute standardized mean gap is `1.349489` and the largest standardized central-quantile gap is `3.642091` at `p95`. Classification: `MATERIAL_PRICE_SOURCE_DIFFERENCE`. The price-source layers meet the preregistered descriptive materiality criterion. The pooled mean must therefore not be the only reporting granularity.

The pure linear-rescaling reference uses each accepted row's forward-reconstructed old `ev_se * (sqrt(2) - 1)`; it does not infer or back-solve historical sigma.

| price source | n | actual mean `ev_se` delta | pure `sqrt(2)` predicted mean | absolute relative gap |
|---|---:|---:|---:|---:|
| `DERIVED_FROM_CURRENT_EV_AND_FIVE_STATE_DISTRIBUTION` | `478` | `+0.027423` | `+0.027685` | `0.9465%` |
| `PAYLOAD_DECIMAL_ODDS` | `2106` | `+0.020838` | `+0.020927` | `0.4227%` |
| pooled | `2584` | `+0.022056` | `+0.022177` | `0.5437%` |

The independently supplied pooled prediction was `+0.022213`; the observed pooled `+0.022056` differs by `0.7054%`. The layer rows show whether that near-`sqrt(2)` behavior is shared across both price sources rather than being only a pooled artifact.

### `0.01` lower-node floor

| Measurement | old `mu-sigma` | GH-3 `mu-sqrt(3)sigma` |
|---|---:|---:|
| triggered lambda sides / side inputs | `0 / 2122` | `0 / 2122` |
| trigger rate | `0.000000` | `0.000000` |
| affected model-input groups | `0` | `0` |
| affected evaluations | `0` | `0` |

GH-3 newly affects `0` model-input groups / `0` evaluations. The closest unfloored lower nodes are `0.534679` under the old path and `0.468176` under GH-3, both still well above `0.01`; this is why the observed trigger counts are zero rather than the anticipated increase. For the `0` triggered lambda sides, actual effective SD is `not observed (0 triggered sides)` (min / median / max), or `not observed (0 triggered sides)` times input `sigma`. The JSON contains every affected model-input hash, fixture, side, evaluation ID, `mu`, `sigma`, actual SD, and collapse ratio; when the trigger count is zero the affected-sample list is correctly empty and effective-SD collapse is `N/A` for this frozen cohort.

Therefore Contract 1 has one explicit exception under the current positivity treatment: once the floor fires, the actual discrete-node SD is less than `sigma`. The combined Contract 1 + SE formula production Gate must either accept and document this exception or separately approve a positivity-preserving distribution; this offline package does neither.

### 3. Existing point-in-time and hard sample boundaries remain binding

- `kickoff_at < as_of`.
- `captured_at <= as_of`.
- `limit_per_team = 20`.
- Each attack/defence sample group requires `n >= 3`.

No replacement PIT subsystem is proposed. Historical reconstruction additionally restricted xG rows to `captured_at <= evaluated_at` so later backfill could not appear in an earlier evaluation. It applies point-in-time visibility before the latest-20 cap so a later backfill cannot displace an older row that was visible at the frozen evaluation time.

### 4. Coverage is partially represented by `n`, but missingness is not identified

The current standard error contains `1 / sqrt(n)`. It therefore reacts to the number of observed xG rows.

It does not identify why `n` has that value, and it selects the latest 20 rows that have xG rather than the xG-covered subset of the latest 20 matches that should exist. Consequently:

- five occurred matches with five xG rows; and
- twenty occurred matches with only five xG rows

are identical after `_xg_uncertainty_rows` if only the five observed rows are presented. Conversely, twenty older xG rows can fill `n=20` even when several of the most recent expected matches have no xG.

## Falsification test A — does age retain an effect after fixing n?

The frozen read-only reconstruction produced `2,603` usable evaluations across `162` fixtures. Fixed effects retain only exact `(home_n, away_n, market, selection)` strata with at least four rows.

| Measurement | Result |
|---|---:|
| `ev_se` min / mean / max | `0.028387 / 0.053626 / 0.121181` |
| raw `latest age × ev_se` correlation | `-0.029046` |
| raw `min(home_n, away_n) × ev_se` correlation | `-0.787364` |
| within exact `(home_n, away_n, market, selection)` `age × ev_se` correlation | `+0.002498` |
| fixed-effect rows | `2,582` |

The dominant exact sample stratum was `home_n=20 / away_n=20`:

| Measurement | Result |
|---|---:|
| evaluations / fixtures | `2,293 / 139` |
| age median | `14.000 days` |
| age correlation with `ev_se` | `-0.004335` |
| fresh half mean age / mean `ev_se` | `9.156 days / 0.049100` |
| old half mean age / mean `ev_se` | `71.219 days / 0.050651` |

Result: after fixing sample size and market/selection, age contributes effectively zero to the reported `ev_se`. The previously observed approximately 10% old-versus-fresh difference is not evidence of an age response; it is explained by sample-size and composition differences. The problem statement is therefore upgraded to: **the current uncertainty formula has no explicit recency response**.

This is an epistemic formula diagnosis, not evidence that stale xG biases EV upward or downward.

## Falsification test B — can an expected-match denominator vary independently of n?

The production `canonical_team_match_history` table cannot currently serve the enabled runtime scope: it contains `102` rows, all from Allsvenskan, and has `0` rows for the enabled competitions.

Offline denominator feasibility was tested with the already frozen saved-raw Gate 1 corpus:

- snapshot: `2026-08-22T05:50:41.929427Z`;
- canonical corpus fingerprint: `d19b217afe159c87dbf8d0dea87c260374ac9d18ffd8bb97581cfffe858cedc5`;
- file SHA-256: `80e49d1a32b5dd9653d41826e87415acff0d32a6804dea408f3b99737a6ab5e2`;
- team-history rows: `38,706`;
- identity namespace: `api_football.provider_team_id.v1`.

For each evaluation and team, the expected set was the latest 20 finished canonical fixtures from the same provider league strictly before the target kickoff. Coverage was the intersection of that set with xG rows visible by the evaluation time. Evaluations at or after kickoff were excluded.

The enabled scope is read from `league_season.payload.enabled`; the script neither assumes a fixed league count nor divides by one. The frozen observation contains `11` enabled competitions. Coverage is reported per league only; no overall coverage average is computed.

| competition | evaluable rows | frozen finished fixtures | offline structural xG coverage | PIT denominator available rows | PIT xG coverage | runtime canonical fixtures / identity fixtures |
|---|---:|---:|---:|---:|---:|---:|
| `argentina_primera` | `356` | `2178` | `0.254916` | `356` | `0.254916` | `0` / `53` |
| `brasileirao_serie_a` | `176` | `1744` | `0.966477` | `176` | `0.966477` | `0` / `47` |
| `bundesliga` | `8` | `1232` | `1.0` | `8` | `1.0` | `0` / `20` |
| `eliteserien` | `4` | `1103` | `0.975` | `4` | `0.975` | `0` / `34` |
| `eredivisie` | `149` | `1293` | `0.974329` | `149` | `0.974329` | `0` / `31` |
| `la_liga` | `198` | `1528` | `0.996465` | `184` | `0.998098` | `0` / `28` |
| `ligue_1` | `154` | `1304` | `0.991558` | `154` | `0.991558` | `0` / `19` |
| `mls` | `738` | `2371` | `0.942412` | `706` | `0.943768` | `0` / `55` |
| `premier_league` | `184` | `1521` | `1.0` | `184` | `1.0` | `0` / `18` |
| `primeira_liga` | `120` | `1249` | `0.989583` | `120` | `0.989583` | `0` / `31` |
| `serie_a` | `178` | `1521` | `1.0` | `178` | `1.0` | `0` / `20` |

Canonical Provider fixture identity is validated separately from xG coverage. The join key is `(provider_fixture_id, provider_team_id)`; failure samples are bounded to five per league. No overall identity or coverage mean is computed.

| competition | eligible team-history rows | canonical ID shape success | xG identity join success | bounded failure samples |
|---|---:|---:|---:|---|
| `argentina_primera` | `4356` | `1.0` | `0.430211` | `[{"canonical_fixture_id":"api_football:831664","provider_fixture_id":"831664","provider_team_id":"458"},{"canonical_fixture_id":"api_football:831664","provider_fixture_id":"831664","provider_team_id":"444"},{"canonical_fixture_id":"api_football:831665","provider_fixture_id":"831665","provider_team_id":"455"},{"canonical_fixture_id":"api_football:831665","provider_fixture_id":"831665","provider_team_id":"474"},{"canonical_fixture_id":"api_football:831666","provider_fixture_id":"831666","provider_team_id":"442"}]` |
| `brasileirao_serie_a` | `3488` | `1.0` | `0.563647` | `[{"canonical_fixture_id":"api_football:837992","provider_fixture_id":"837992","provider_team_id":"128"},{"canonical_fixture_id":"api_football:837992","provider_fixture_id":"837992","provider_team_id":"124"},{"canonical_fixture_id":"api_football:837998","provider_fixture_id":"837998","provider_team_id":"127"},{"canonical_fixture_id":"api_football:837998","provider_fixture_id":"837998","provider_team_id":"144"},{"canonical_fixture_id":"api_football:837994","provider_fixture_id":"837994","provider_team_id":"129"}]` |
| `bundesliga` | `2464` | `1.0` | `0.496753` | `[{"canonical_fixture_id":"api_football:871164","provider_fixture_id":"871164","provider_team_id":"157"},{"canonical_fixture_id":"api_football:871164","provider_fixture_id":"871164","provider_team_id":"169"},{"canonical_fixture_id":"api_football:871166","provider_fixture_id":"871166","provider_team_id":"159"},{"canonical_fixture_id":"api_football:871166","provider_fixture_id":"871166","provider_team_id":"182"},{"canonical_fixture_id":"api_football:871168","provider_fixture_id":"871168","provider_team_id":"167"}]` |
| `eliteserien` | `2206` | `1.0` | `0.516772` | `[{"canonical_fixture_id":"api_football:831004","provider_fixture_id":"831004","provider_team_id":"321"},{"canonical_fixture_id":"api_football:831004","provider_fixture_id":"831004","provider_team_id":"2159"},{"canonical_fixture_id":"api_football:831005","provider_fixture_id":"831005","provider_team_id":"326"},{"canonical_fixture_id":"api_football:831005","provider_fixture_id":"831005","provider_team_id":"329"},{"canonical_fixture_id":"api_football:831006","provider_fixture_id":"831006","provider_team_id":"320"}]` |
| `eredivisie` | `2586` | `1.0` | `0.490333` | `[{"canonical_fixture_id":"api_football:872224","provider_fixture_id":"872224","provider_team_id":"426"},{"canonical_fixture_id":"api_football:872224","provider_fixture_id":"872224","provider_team_id":"210"},{"canonical_fixture_id":"api_football:872225","provider_fixture_id":"872225","provider_team_id":"194"},{"canonical_fixture_id":"api_football:872225","provider_fixture_id":"872225","provider_team_id":"205"},{"canonical_fixture_id":"api_football:872226","provider_fixture_id":"872226","provider_team_id":"196"}]` |
| `la_liga` | `3056` | `1.0` | `0.502618` | `[{"canonical_fixture_id":"api_football:877947","provider_fixture_id":"877947","provider_team_id":"536"},{"canonical_fixture_id":"api_football:877947","provider_fixture_id":"877947","provider_team_id":"727"},{"canonical_fixture_id":"api_football:877945","provider_fixture_id":"877945","provider_team_id":"540"},{"canonical_fixture_id":"api_football:877945","provider_fixture_id":"877945","provider_team_id":"538"},{"canonical_fixture_id":"api_football:877950","provider_fixture_id":"877950","provider_team_id":"533"}]` |
| `ligue_1` | `2608` | `1.0` | `0.470092` | `[{"canonical_fixture_id":"api_football:871474","provider_fixture_id":"871474","provider_team_id":"98"},{"canonical_fixture_id":"api_football:871474","provider_fixture_id":"871474","provider_team_id":"80"},{"canonical_fixture_id":"api_football:871470","provider_fixture_id":"871470","provider_team_id":"91"},{"canonical_fixture_id":"api_football:871470","provider_fixture_id":"871470","provider_team_id":"95"},{"canonical_fixture_id":"api_football:871472","provider_fixture_id":"871472","provider_team_id":"85"}]` |
| `mls` | `4742` | `1.0` | `0.574019` | `[{"canonical_fixture_id":"api_football:816716","provider_fixture_id":"816716","provider_team_id":"1612"},{"canonical_fixture_id":"api_football:816716","provider_fixture_id":"816716","provider_team_id":"1599"},{"canonical_fixture_id":"api_football:816717","provider_fixture_id":"816717","provider_team_id":"1603"},{"canonical_fixture_id":"api_football:816717","provider_fixture_id":"816717","provider_team_id":"1613"},{"canonical_fixture_id":"api_football:816718","provider_fixture_id":"816718","provider_team_id":"1610"}]` |
| `premier_league` | `3042` | `1.0` | `0.500329` | `[{"canonical_fixture_id":"api_football:867946","provider_fixture_id":"867946","provider_team_id":"42"},{"canonical_fixture_id":"api_football:867946","provider_fixture_id":"867946","provider_team_id":"52"},{"canonical_fixture_id":"api_football:867947","provider_fixture_id":"867947","provider_team_id":"40"},{"canonical_fixture_id":"api_football:867947","provider_fixture_id":"867947","provider_team_id":"36"},{"canonical_fixture_id":"api_football:867948","provider_fixture_id":"867948","provider_team_id":"66"}]` |
| `primeira_liga` | `2498` | `1.0` | `0.504404` | `[{"canonical_fixture_id":"api_football:898605","provider_fixture_id":"898605","provider_team_id":"240"},{"canonical_fixture_id":"api_football:898605","provider_fixture_id":"898605","provider_team_id":"211"},{"canonical_fixture_id":"api_football:898604","provider_fixture_id":"898604","provider_team_id":"810"},{"canonical_fixture_id":"api_football:898604","provider_fixture_id":"898604","provider_team_id":"226"},{"canonical_fixture_id":"api_football:898608","provider_fixture_id":"898608","provider_team_id":"242"}]` |
| `serie_a` | `3042` | `1.0` | `0.499014` | `[{"canonical_fixture_id":"api_football:881780","provider_fixture_id":"881780","provider_team_id":"494"},{"canonical_fixture_id":"api_football:881780","provider_fixture_id":"881780","provider_team_id":"489"},{"canonical_fixture_id":"api_football:881781","provider_fixture_id":"881781","provider_team_id":"499"},{"canonical_fixture_id":"api_football:881781","provider_fixture_id":"881781","provider_team_id":"498"},{"canonical_fixture_id":"api_football:881782","provider_fixture_id":"881782","provider_team_id":"505"}]` |

Across the enabled rows, count-only lineage remains `2,265` evaluable, `897` fully covered, and `1,274` false-full evaluations inside `2,171` legacy `n=20/n=20` evaluations. These are counts, not an overall coverage estimate. They retain the prior proof that fixture-level missingness varies independently at fixed `n`.

The frozen corpus is sufficient to prove offline identifiability. `result_first_captured_at <= evaluated_at` is used to show where the full structural latest-20 denominator was actually visible at evaluation time; the gap between the two columns is evidence that kickoff-only hindsight cannot be silently called runtime PIT availability.

Owner decision 2 and its implementation boundary:

- `canonical_team_match_history`: current enabled-scope coverage is insufficient.
- `matchday_fixture_identities`: useful identity routing, but it has no finished status, result, or first-result visibility time and cannot alone define the denominator.
- persisted saved-raw fixtures: **approved as the source for a bounded runtime materialization**, not for direct unbounded raw scans. Each immutable observation carries canonical Provider fixture identity, `captured_at`, and `source_inserted_at`; reads require both timestamps `<= as_of` and select the latest visible observation per fixture. A late historical raw with `source_inserted_at > as_of` cannot enter a prior denominator; an unknown insertion time is rejected and fails closed.
- dynamic scope is read from `league_season.payload.enabled`. The latest-20 expected set is cross-season within the same Provider league, so a season boundary is not a reset switch.
- deployment requires the historical materialization backlog to be exhausted before the read path is enabled. New fixture raw writes materialize in the same transaction. This package supplies the migration and local validation but does not deploy either.

The coverage rows above correspond to `POST_20260823_REFRESH_BEFORE_XG_INGEST_01_PROVIDER_RETRY` with `18846` xG rows visible at the frozen observation. No historical null-response Provider retry had run. Any later Owner-authorized retry changes the numerator baseline and requires regenerating this package; it does not change the expected-match denominator contract.

## Item 3 — coefficient-free formula-family draft

Status: `DRAFT_ONLY_COEFFICIENTS_UNSET_NOT_EXECUTABLE`. The following family is intentionally non-executable until Owner-approved coefficients are supplied without outcomes, profit, hit rate, age-cutoff backtests, or EV-cap backtests.

For each team, let `E` be the latest 20 finished, point-in-time-visible fixtures in the same Provider league before `as_of`, across seasons. Cancelled, abandoned, and postponed fixtures do not count as played. Let `m=|E|`, let `O` be the members of `E` with point-in-time-visible two-sided numeric xG, let `n=|O|`, `c=n/m`, `q=m-n`, and let `A` be the mean exact elapsed age in days over **E**, including fixtures whose xG is missing. Computing age over E rather than O means filling a missing xG value cannot itself increase the age term.

For each attack/defence component:

`SE0 = sample_sd(O) / sqrt(n)`

`SE = SE0 * sqrt(1 + alpha_age_per_day * A + beta_missing * (1 - c))`

`alpha_age_per_day = None` and `beta_missing = None`. Both are constrained nonnegative but remain unset. The missingness term uses independently observed `m` and `q`; therefore five observed xG rows after five occurred matches (`c=1`) are not the same state as five observed rows after twenty occurred matches (`c=0.25`), even though both have `n=5`.

Lambda propagation is not allowed to apply the interior `0.5` coefficient beyond its valid segment. It uses a four-input GH-3 tensor product over home attack, away defence, away attack, and home defence; every node runs through the actual `calibrate_lambdas` piecewise function, including total clamps `1.35/4.40` and individual-lambda clamps. `lambda_sigma` is the weighted standard deviation of those mapped nodes. In the interior this reduces exactly to the existing Jacobian identity `0.5 * sqrt(SE_attack^2 + SE_opponent_defence^2)`. Any nonlinear quadrature mean shift is audit-only and does not change the point lambda in this draft.

The resulting scalar `lambda_sigma` is consumed by Contract 1 GH-3 at `point_lambda ± sqrt(3)·lambda_sigma` with weights `(0.16666666666666666, 0.6666666666666666, 0.16666666666666666)`. The `0.01` lower-node floor exception remains explicit: once it triggers, the consumed discrete SD is below the supplied `lambda_sigma`.

The five invariants are structural: nonnegative `alpha` makes uniform aging non-decreasing; at fixed dispersion and expected ages, increasing `n` decreases both `SE0` and `1-c`; `A=0,c=1` reproduces the interior baseline exactly and any nonzero-fresh case must pass the frozen tolerance; unavailable authority, `m<3`, `n<3`, identity conflict, unknown insertion time, or unset coefficients fail closed; and the cross-season latest-20 set replaces evidence one fixture at a time, so recent covered evidence reduces age and missingness without a season switch or time gate.

## Preregistered behavioral invariants

Any candidate method must satisfy all five invariants without consulting current-pick profit or loss:

1. **Age monotonicity:** holding xG values, expected fixtures, observed fixtures, sample count, market, and price fixed, making evidence older must not reduce `lambda_sigma` or `ev_se`.
2. **Sample and coverage monotonicity:** holding values and ages fixed, adding a valid recent observed fixture or increasing recent expected-fixture coverage must not increase uncertainty. A missing expected fixture must not be treated as a match that never occurred.
3. **Fresh complete baseline parity:** when the latest expected fixture set is fully covered and fresh, the candidate must reproduce the approved interior baseline within a preregistered numerical tolerance; no global inflation is allowed merely to close the gate more often.
4. **No-evidence fail closed:** fewer than three valid observations, an unavailable expected denominator, identity conflict, or unknown coverage state must not produce a high-confidence active pick.
5. **Automatic seasonal recovery:** as a team accumulates new, fully covered evidence, uncertainty must decrease continuously under the same rule. Bundesliga or another restarting league must recover without an age cutoff or season-start switch.

Additional structural requirements:

- The `0.5` interior coefficient is defined by the lambda Jacobian, not tuned from outcomes.
- Clamp-boundary propagation must use the actual piecewise lambda function.
- `lambda_sigma` must follow the Owner-approved probability meaning and consequences for both consumers.
- Expected fixtures and observed xG fixtures must be compared by canonical provider fixture identity.
- The latest-20 cap and `n>=3` lower bound remain unchanged unless separately approved.

## Gate state and remaining Owner decisions

1. **Decided:** Contract 1 defines `lambda_sigma` as a true standard deviation. GH-3 is the reference offline specification. This is not production implementation approval.
2. **Decided:** persisted saved-raw fixtures, materialized into immutable PIT observations, are the expected-match denominator authority. Migration and code are local-only; production deployment remains unapproved.
3. **Thawed for draft only:** the formula family above is specified, but both coefficients remain unset. No final formula or parameter is approved.

Owner superseded the earlier sequencing rule. Contract 1 production implementation no longer occupies a separate Gate; it may be bundled with the eventual SE formula change in one production Gate because its near-uniform `sqrt(2)` rescaling is analytically separable. This does not approve that deployment. The current state is `ITEMS_1_2_DECIDED / ITEM_3_DRAFTED_COEFFICIENTS_UNSET / COMBINED_PRODUCTION_GATE_NOT_AUTHORIZED`.
