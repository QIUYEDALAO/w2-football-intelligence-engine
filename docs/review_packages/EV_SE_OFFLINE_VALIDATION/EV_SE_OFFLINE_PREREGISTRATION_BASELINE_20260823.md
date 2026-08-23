# EV SE offline preregistration baseline — 2026-08-23

Status: `PRE_MODEL_DIAGNOSTIC_PASS / PARAMETER_GATE_OPEN / NO_MODEL_CHANGE`

## Execution boundary

- Exact production release observed: `d05ab74217e37af2e85732ac3a63ee4d9e214aa1`.
- Exact production schema: `0070_notification_delivery_routing`.
- Evidence observed at: `2026-08-23T12:00:50Z`.
- Provider calls: `0`.
- Production database writes: `0` (all SQL ran in `BEGIN READ ONLY ... ROLLBACK`).
- Outcomes and the current 65 settled picks were not read.
- No model, threshold, Scheduler, notification, deployment, or runtime configuration changed.

This document preregisters the problem and behavioral acceptance conditions. It does not approve a formula, coefficient, implementation, or release.

## Binding non-claims

- Do not claim that stale xG raises EV. That causal claim failed its prior test.
- Do not use profit, loss, hit rate, or the current 65 settled picks to choose an uncertainty coefficient.
- Do not introduce or backtest-select an age cutoff or EV ceiling.
- The target is epistemic: `ev_se` claims to express uncertainty about the current match lambdas. The current formula treats old and recent source matches as exchangeable conditional on observed values and sample size; that stationarity assumption requires an explicit test and policy.

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

The coefficient is only piecewise valid. A total clamp or final-lambda clamp changes the Jacobian. In the 157 frozen model captures, 156 base totals were inside `[1.35, 4.40]`; one was above `4.40`. Any future uncertainty implementation must propagate through the actual piecewise calibration path rather than silently applying one global coefficient at clamp boundaries.

### 2. `lambda_sigma` has two inconsistent downstream probability meanings

The `ev_se` path evaluates nodes `mu-sigma`, `mu`, and `mu+sigma` with weights `0.25 / 0.50 / 0.25`. The weighted node standard deviation is `sqrt(0.5) * sigma`, approximately `0.7071 * sigma`.

The main simulation path evaluates the same nodes with weights `0.158655 / 0.68269 / 0.158655`. Its weighted node standard deviation is approximately `0.5633 * sigma`.

No repository document was found that declares whether `lambda_sigma` is intended to be:

- the true standard deviation of the lambda distribution; or
- only the distance from the centre node to the outer scenario nodes.

This semantic mismatch must be resolved before selecting any new age or coverage adjustment. Otherwise a correct upstream uncertainty can still be contracted differently by the two consumers.

### 3. Existing point-in-time and hard sample boundaries remain binding

- `kickoff_at < as_of`.
- `captured_at <= as_of`.
- `limit_per_team = 20`.
- Each attack/defence sample group requires `n >= 3`.

No replacement PIT subsystem is proposed. Historical reconstruction additionally restricted xG rows to `captured_at <= evaluated_at` so later backfill could not appear in an earlier evaluation.

### 4. Coverage is partially represented by `n`, but missingness is not identified

The current standard error contains `1 / sqrt(n)`. It therefore reacts to the number of observed xG rows.

It does not identify why `n` has that value, and it selects the latest 20 rows that have xG rather than the xG-covered subset of the latest 20 matches that should exist. Consequently:

- five occurred matches with five xG rows; and
- twenty occurred matches with only five xG rows

are identical after `_xg_uncertainty_rows` if only the five observed rows are presented. Conversely, twenty older xG rows can fill `n=20` even when several of the most recent expected matches have no xG.

## Falsification test A — does age retain an effect after fixing n?

The live read-only reconstruction produced 2,603 usable evaluations across 162 fixtures. This is slightly newer than the 2,528-row handoff snapshot.

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

The production `canonical_team_match_history` table cannot currently serve the active runtime: it contains 102 rows, all from Allsvenskan, and has zero coverage for the active 11 competitions.

Offline denominator feasibility was tested with the already frozen saved-raw Gate 1 corpus:

- snapshot: `2026-08-22T05:50:41.929427Z`;
- corpus SHA-256: `d19b217afe159c87dbf8d0dea87c260374ac9d18ffd8bb97581cfffe858cedc5`;
- team-history rows: `38,706`;
- identity namespace: `api_football.provider_team_id.v1`.

For each evaluation and team, the expected set was the latest 20 finished canonical fixtures strictly before the target kickoff. Coverage was the intersection of that set with xG rows visible by the evaluation time.

Active 11-competition result:

| Measurement | Result |
|---|---:|
| evaluations with both expected denominators `>=3` | `2,265` |
| both teams fully covered in their expected latest 20 | `897` |
| old algorithm reports `n=20` for both teams but expected latest-20 coverage is incomplete | `1,274` |
| side rows missing at least one expected xG fixture | `2,379` |
| side coverage min / median / mean | `0.20 / 0.95 / 0.858355` |

Among evaluations for which the old algorithm reports `n=20` on both teams, `1,274 / (1,274 + 897) = 58.68%` still have at least one recent expected-match coverage gap. Thus fixture-level coverage has substantial independent variation at fixed `n=20`; it is identifiable and not merely a duplicate transform of n.

The frozen corpus is sufficient to prove offline identifiability. It is not itself a production runtime authority. A runtime implementation requires an approved, point-in-time available expected-fixture denominator for the active 11 competitions.

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
- `lambda_sigma` must have one declared probability meaning shared by the simulation and `ev_se` paths.
- Expected fixtures and observed xG fixtures must be compared by canonical provider fixture identity.
- The latest-20 cap and `n>=3` lower bound remain unchanged unless separately approved.

## Owner decisions required before implementation

1. Declare whether `lambda_sigma` is a true standard deviation or a scenario-node distance, and approve one consistent propagation contract for both consumers.
2. Approve the runtime expected-match denominator authority and its point-in-time availability contract for the active 11 competitions.
3. Approve a formula family for recency and missing-coverage uncertainty. Coefficients remain unset at this gate.

Until those decisions are recorded, the correct state is `OFFLINE_DIAGNOSTIC_COMPLETE / MODEL_PARAMETER_CHANGE_NOT_AUTHORIZED`.
