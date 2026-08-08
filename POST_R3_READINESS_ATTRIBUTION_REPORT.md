# W2 Post-R3 Readiness Root-Cause Attribution

```text
TASK = W2_MI_POST_R3_READINESS_ROOT_CAUSE_ATTRIBUTION
RESULT = PASS_READ_ONLY_ATTRIBUTION
SELECTED_PATH = PATH_A_NATURAL_EVIDENCE_ACCUMULATION
ROUND_4 = NOT_STARTED
```

## Technical summary

The frozen Round-3 public cohort is reconciled exactly: 64 fixtures, 128
fixture-markets, timeline depth `0:92 / 1:9 / 2+:27`, and Model Lab status
`MARKET_NOT_READY:125 / MODEL_NOT_READY:2 /
INSUFFICIENT_BOOKMAKER_DEPTH:1`. The attribution grain is
`fixture_id + market + as_of`, fixed at `2026-08-08T10:19:12Z`.

The dominant blocker is the normal collection lifecycle, not a positive market
signal and not a proven recurring collection bug:

| Primary blocker | Rows | Share of 128 | Interpretation |
|---|---:|---:|---|
| `NO_CURRENT_SNAPSHOT` | 90 | 70.31% | No valid market snapshot yet; the next normal odds checkpoint had not entered its legal window. |
| `EXPECTED_STALE_BETWEEN_CHECKPOINTS` | 29 | 22.66% | A valid snapshot existed but was older than 3600 seconds while the next checkpoint was still not due. |
| `DUE_WINDOW_BUT_NO_FRESH_CAPTURE` | 6 | 4.69% | Three fixtures were inside an odds window at the frozen instant; the controlled Round-3 rollback/restore interval explains why the bridge task path had not produced a fresh capture. |
| `INSUFFICIENT_BOOKMAKER_DEPTH` | 1 | 0.78% | Fresh same-line market evidence existed, but only one paired bookmaker was available. |
| `MODEL_SIMULATION_NOT_READY` | 1 | 0.78% | The market was ready, but simulation inputs were insufficient. |
| `MODEL_CALIBRATION_NOT_READY` | 1 | 0.78% | Simulation was ready, but calibration status was not an accepted ready state. |

Thus 125 of 128 rows (97.66%) are collection-lifecycle blocked. No row is
attributed to a proven identity/lineage rejection, mainline construction
failure, missing two-sided quote pair, or incomplete market probability. The
only rejected observations in the frozen public cohort are the already
reported unsupported markets; inventing a deeper construction or identity
cause would exceed the evidence.

`PATH_A_NATURAL_EVIDENCE_ACCUMULATION` is selected. No remediation PR was
created because no recurring internal W2 defect was proven. The six due-window
rows occurred during a controlled, temporary bridge OFF/restore interval and
do not justify changing cadence, freshness, quota, checkpoint, whitelist, or
Model Lab gates.

## Authority, cohort and data-quality gate

```text
MAIN = f0fe9d332d05a84f1ef04be86fd9fb44b69d69e3
ROUND_3 = PASS_MARKET_RADAR_MODEL_LAB
FROZEN_AS_OF = 2026-08-08T10:19:12Z
CHECKPOINT_FIXTURES_READ = 69
FROZEN_FUTURE_FIXTURES = 64
FIXTURE_MARKETS = 128
PROVIDER_CALLS_FOR_THIS_TASK = 0
DATABASE_BUSINESS_WRITES_FOR_THIS_TASK = 0
NEW_COLLECTION_TASKS = 0
```

All 69 shadow checkpoints have the same Round-3 source event at the frozen
time. Filtering to kickoff after that instant yields exactly 64 fixtures and
two supported markets per fixture. Quality checks passed:

| Check | Result |
|---|---:|
| Composite-key duplicates at `fixture_id + market + as_of` | 0 |
| Missing required attribution fields | 0 |
| Post-kickoff rows in the frozen cohort | 0 |
| Projection source-event mismatches | 0 |
| Receipt count reconciliation | PASS |

The currently moving public window was also checked separately. At
`2026-08-08T12:24:13Z`, five fixtures had naturally kicked off, leaving 118
future fixture-markets with timeline `0:92 / 1:9 / 2+:17` and Model Lab
`115 / 2 / 1`. That is expected cohort roll-forward and does not replace the
Owner-mandated 128-row frozen baseline.

## Exact-main semantics proved from code

The following source hashes bind the semantics used by this audit:

| Source | SHA-256 |
|---|---|
| `src/w2/markets/round3_intelligence.py` | `dcae4e11e47a7e35b65eaa708dda26e1d3345a177c15c0f25e31afa8eb036701` |
| `src/w2/ingestion/free_fixture_runtime.py` | `47c59bc0a5b5bdf62e610d8bdaa339c50d71f766201698d61e52d2f8eb314bcf` |
| `src/w2/matchday/intake_v2.py` | `b03349ef8000bdafc8b818c81ca7ef2d582a94f70e1ff28bc1e15a116f07ee8b` |
| `apps/scheduler/main.py` | `338e21979ccf5d37b7785638c9eedd2a8f4b1fe38d3a2cffbc4d23d831ea2b29` |
| `src/w2/matchday/repository.py` | `54f0c22365c5d928eb7a9667c7a52c74d792b10c44709ab94244943e9b0ccec1` |

The code contract is:

1. `_market_radar()` groups eligible observations by real capture identity and
   timestamp. `_snapshot()` returns no snapshot unless canonical mainline
   selection is ready and at least one two-sided same-line bookmaker pair
   exists. Timeline state is strictly 0, 1, or 2+ real snapshots; no points are
   copied or interpolated.
2. `_snapshot()` sets freshness to `COMPLETE` only when
   `age_seconds <= freshness_seconds`; exact main passes 3600 seconds.
3. `_model_lab_market()` uses strict precedence: missing/stale current market;
   then fewer than three bookmakers; then model/simulation/calibration blockers;
   then score matrix; then canonical line and complete probability range. Only
   after every gate can a row be comparable or outside the observed range.
4. The bridge policy keeps odds max age at 3600 seconds and normal odds
   checkpoints at `T12`, `T6`, `T3`, and `T60`, with respective grace windows
   30, 30, 30, and 20 minutes.
5. A checkpoint is `DUE` only within its inclusive legal window. After the
   window it is `MISSED`; before it, it is `PLANNED`.
6. The bridge reuses a capture only when it is both within the 3600-second
   freshness bound and no earlier than the due window. With no due fixture, it
   records `NO_DUE_TARGET_FIXTURES_NO_IDLE_POLLING` and makes no follow-up call.
7. The scheduler checks bridge mode, scheduler permission, and a five-minute
   dedupe gate before queueing. If bridge mode is disabled, it returns
   `DISABLED` with zero Provider calls.

These semantics prove why a market can have a valid 2+ historical timeline and
still be correctly unavailable to Model Lab at the present instant.

## Deterministic attribution precedence

The matrix uses the following primary-blocker order. Every additional true
condition is retained in `secondary_blockers`:

```text
IDENTITY_OR_LINEAGE_REJECTED
> DUE_WINDOW_BUT_NO_FRESH_CAPTURE
> EXPECTED_STALE_BETWEEN_CHECKPOINTS
> CURRENT_SNAPSHOT_STALE
> NO_CURRENT_SNAPSHOT
> MAINLINE_NOT_READY
> TWO_SIDED_QUOTE_PAIR_MISSING
> MARKET_PROBABILITY_INCOMPLETE
> INSUFFICIENT_BOOKMAKER_DEPTH
> MODEL_SIMULATION_NOT_READY
> MODEL_CALIBRATION_NOT_READY
> other code-proven model blockers
```

This order puts evidence-integrity failure first, then an actionable missed
authorized window, then expected temporal state, market construction, depth,
and model readiness. A stale row inside a legal due window is not counted as
expected between-checkpoint staleness. A stale row outside a due window with a
future legal checkpoint is not counted as a defect.

The 90 no-snapshot rows were not relabeled as construction failures because no
current valid snapshot exists and the persisted rejection distribution does
not prove identity, mainline, pair, or probability failure. The matrix keeps
raw/capture lineage as `NO_VALID_MARKET_SNAPSHOT`, rather than falsely calling
it complete or rejected; fixture identity remains complete.

## Timeline depth × Model Lab status

| Timeline depth | `MARKET_NOT_READY` | `MODEL_NOT_READY` | `INSUFFICIENT_BOOKMAKER_DEPTH` | Total |
|---|---:|---:|---:|---:|
| 0 | 92 | 0 | 0 | 92 |
| 1 | 9 | 0 | 0 | 9 |
| 2+ | 24 | 2 | 1 | 27 |
| **Total** | **125** | **2** | **1** | **128** |

Historical movement readiness and present market readiness are independent.
The 27 rows with two or more snapshots answer only whether factual historical
movement can be compared; they do not waive freshness, depth, simulation, or
calibration gates.

## The 27 movement-comparison-eligible rows

Exactly 24 of 27 (88.89%) remain `MARKET_NOT_READY`:

| Requested reason | Rows |
|---|---:|
| Current quote stale, residual outside the two checkpoint categories | 0 |
| No current snapshot | 0 |
| Expected between-checkpoint stale | 21 |
| Checkpoint due but no fresh capture at frozen instant | 3 |
| Market construction failure | 0 |
| Identity/lineage failure | 0 |
| Other `MARKET_NOT_READY` | 0 |
| Non-market readiness: depth/model/calibration | 3 |

| Fixture | Competition | Market | Valid snapshots | Same-line snapshots | Model Lab | Primary blocker |
|---|---|---|---:|---:|---|---|
| 1492320 | brasileirao_serie_a | ASIAN_HANDICAP | 2 | 2 | MARKET_NOT_READY | EXPECTED_STALE_BETWEEN_CHECKPOINTS |
| 1492320 | brasileirao_serie_a | TOTALS | 2 | 2 | MARKET_NOT_READY | EXPECTED_STALE_BETWEEN_CHECKPOINTS |
| 1492321 | brasileirao_serie_a | TOTALS | 2 | 2 | MARKET_NOT_READY | EXPECTED_STALE_BETWEEN_CHECKPOINTS |
| 1492323 | brasileirao_serie_a | ASIAN_HANDICAP | 2 | 2 | MARKET_NOT_READY | EXPECTED_STALE_BETWEEN_CHECKPOINTS |
| 1492323 | brasileirao_serie_a | TOTALS | 2 | 2 | MARKET_NOT_READY | EXPECTED_STALE_BETWEEN_CHECKPOINTS |
| 1492324 | brasileirao_serie_a | ASIAN_HANDICAP | 2 | 2 | MARKET_NOT_READY | EXPECTED_STALE_BETWEEN_CHECKPOINTS |
| 1492324 | brasileirao_serie_a | TOTALS | 2 | 2 | MARKET_NOT_READY | EXPECTED_STALE_BETWEEN_CHECKPOINTS |
| 1492326 | brasileirao_serie_a | TOTALS | 2 | 2 | MARKET_NOT_READY | EXPECTED_STALE_BETWEEN_CHECKPOINTS |
| 1492327 | brasileirao_serie_a | ASIAN_HANDICAP | 2 | 2 | MARKET_NOT_READY | EXPECTED_STALE_BETWEEN_CHECKPOINTS |
| 1492327 | brasileirao_serie_a | TOTALS | 2 | 2 | MARKET_NOT_READY | EXPECTED_STALE_BETWEEN_CHECKPOINTS |
| 1492328 | brasileirao_serie_a | ASIAN_HANDICAP | 2 | 2 | INSUFFICIENT_BOOKMAKER_DEPTH | INSUFFICIENT_BOOKMAKER_DEPTH |
| 1492328 | brasileirao_serie_a | TOTALS | 3 | 3 | MODEL_NOT_READY | MODEL_SIMULATION_NOT_READY |
| 1492329 | brasileirao_serie_a | TOTALS | 2 | 2 | MARKET_NOT_READY | EXPECTED_STALE_BETWEEN_CHECKPOINTS |
| 1494237 | allsvenskan | TOTALS | 2 | 2 | MODEL_NOT_READY | MODEL_CALIBRATION_NOT_READY |
| 1494729 | eliteserien | TOTALS | 3 | 3 | MARKET_NOT_READY | DUE_WINDOW_BUT_NO_FRESH_CAPTURE |
| 1494730 | eliteserien | ASIAN_HANDICAP | 4 | 4 | MARKET_NOT_READY | EXPECTED_STALE_BETWEEN_CHECKPOINTS |
| 1494730 | eliteserien | TOTALS | 4 | 4 | MARKET_NOT_READY | EXPECTED_STALE_BETWEEN_CHECKPOINTS |
| 1494731 | eliteserien | ASIAN_HANDICAP | 4 | 4 | MARKET_NOT_READY | EXPECTED_STALE_BETWEEN_CHECKPOINTS |
| 1494731 | eliteserien | TOTALS | 4 | 4 | MARKET_NOT_READY | EXPECTED_STALE_BETWEEN_CHECKPOINTS |
| 1523228 | chinese_super_league | ASIAN_HANDICAP | 2 | 1 | MARKET_NOT_READY | DUE_WINDOW_BUT_NO_FRESH_CAPTURE |
| 1523228 | chinese_super_league | TOTALS | 2 | 2 | MARKET_NOT_READY | DUE_WINDOW_BUT_NO_FRESH_CAPTURE |
| 1523229 | chinese_super_league | ASIAN_HANDICAP | 4 | 3 | MARKET_NOT_READY | EXPECTED_STALE_BETWEEN_CHECKPOINTS |
| 1523229 | chinese_super_league | TOTALS | 4 | 3 | MARKET_NOT_READY | EXPECTED_STALE_BETWEEN_CHECKPOINTS |
| 1523230 | chinese_super_league | ASIAN_HANDICAP | 4 | 4 | MARKET_NOT_READY | EXPECTED_STALE_BETWEEN_CHECKPOINTS |
| 1523230 | chinese_super_league | TOTALS | 4 | 4 | MARKET_NOT_READY | EXPECTED_STALE_BETWEEN_CHECKPOINTS |
| 1523231 | chinese_super_league | ASIAN_HANDICAP | 4 | 4 | MARKET_NOT_READY | EXPECTED_STALE_BETWEEN_CHECKPOINTS |
| 1523231 | chinese_super_league | TOTALS | 4 | 3 | MARKET_NOT_READY | EXPECTED_STALE_BETWEEN_CHECKPOINTS |

## Due-window trace reaches the real gate

At the frozen instant, three fixtures generated six due fixture-market rows:

| Fixture | Checkpoint window | AH state | Totals state |
|---|---|---|---|
| 1523228 | T60, 10:00–10:20Z | stale snapshot from 08:03Z | stale snapshot from 08:03Z |
| 1494238 | T3, 10:00–10:30Z | no valid snapshot | stale snapshot from Aug 3 |
| 1494729 | T6, 10:00–10:30Z | no valid snapshot | stale snapshot from Aug 3 |

Quota was available: the accepted same-day bridge evidence reported Provider
remaining 93 at `07:46:03Z`, and the frozen 100/80/20 gates remained intact.
Later accepted automatic calls also succeeded, excluding quota exhaustion as
the stop.

The traced chain is:

```text
Scheduler
  -> bridge was in the controlled Round-3 OFF/restore interval at frozen as_of
Task gate
  -> free_fixture_bridge_tick returns DISABLED, provider_calls=0
Cache
  -> not reached
Provider request ledger
  -> no request for the frozen due windows
Endpoint capture
  -> no fresh capture at or before frozen as_of
Normalization
  -> no fresh capture available to normalize
```

The Round-3 receipt records the intentional OFF rollback test and the final
restoration to `SHADOW_ONLY`. The three due windows ended before the final
restore. A DB-backed public collection-status follow-up at
`2026-08-08T12:35:17Z` then showed later current captures for fixtures 1523228
(`10:32:28Z`) and 1494238 (`12:31:11Z`); fixture 1494729 still held the Aug-3
capture and exposed the next authorized checkpoint at `13:00Z`.

This is a real `DUE_WINDOW_BUT_NO_FRESH_CAPTURE` state at the frozen instant,
but it is not evidence of a recurring scheduler/cache/ledger/capture/
normalization defect. It is attributable to the controlled acceptance-state
transition. A production-code remediation would be a fake fix.

Severity is low for the current decision and confidence is high: the missing
instantaneous freshness makes Model Lab correctly fail closed, while later
normal collection demonstrates that the path remained functional after the
accepted bridge restore.

## Why PATH_A is the only supported direction

```text
PATH_A = NATURAL_EVIDENCE_ACCUMULATION
PATH_B = NOT_SELECTED_NO_PERSISTENT_DUE_WINDOW_DEFECT_PROVEN
PATH_C = NOT_SELECTED_STRUCTURAL_BLOCKERS_ARE_3_OF_128_NOT_THE_DOMINANT_CAUSE
```

The completion condition is event-based, not “wait four weeks” or any other
calendar duration:

1. Keep the existing bridge continuously in accepted `SHADOW_ONLY` mode; do
   not change Provider frequency, checkpoint cadence, 3600-second freshness,
   quota, whitelist, or product gates.
2. Let real fixtures in each currently represented active competition
   (Allsvenskan, Brasileirão Série A, Chinese Super League and Eliteserien)
   naturally cross the existing applicable `T12/T6/T3/T60` lifecycle.
3. Require every crossed due window to have persisted terminal evidence:
   `CAPTURED`, `PROVIDER_EMPTY`, an explicit quota/policy blocker, or another
   code-proven terminal reason. An unexplained due window is not silently
   accepted.
4. After the lifecycle events, reproject the same read model and rerun this
   attribution at a new frozen as-of. Compare the exact timeline-depth × Model
   Lab matrix and separately re-audit any due-window gaps.
5. Return the new evidence to the Owner. This condition does not authorize
   Round 4 automatically.

No minimum READY count is imposed. Sparse or insufficient evidence remains a
valid product result.

## Scope, limitations and non-claims

- Checkpoint state at the historical as-of is deterministically reconstructed
  from exact-main policy, kickoff, and inclusive window rules. It is labeled as
  reconstruction in the machine-readable matrix rather than passed off as a
  historical status-table snapshot.
- The frozen checkpoint payload is the public read authority and contains the
  accepted/rejected evidence, canonical snapshots, lineage, timeline and Model
  Lab result. No read-time Provider call or business write was used.
- Because a missing valid snapshot does not expose which rejected raw candidate
  would have won canonical construction, those rows remain
  `NO_CURRENT_SNAPSHOT`. No mainline, quote-pair, probability, or identity leaf
  is fabricated.
- The report is descriptive and diagnostic. It proves neither model quality nor
  market edge. It does not rerun Phase 0.5.
- Exact lookup belongs in the 128-row JSON matrix; a chart was intentionally
  omitted because the requested evidence is categorical audit detail and exact
  row lookup, for which tables are less misleading.

## Repository hygiene and final stop line

The one-time read-only audit script was untracked and deleted after generation.
No production runtime file, dependency, scheduler, feature flag, persistence
model, fixture, or collection configuration was added. No bounded remediation
PR was warranted.

- `KEEP`: `CURRENT_STATE.yaml`, `NEXT_ACTION.md` and
  `CURRENT_TASK_CHECKLIST.md` as current authority.
- `RETAIN_FOR_EVIDENCE`: this report and the 128-row machine-readable matrix.
- `DELETE`: the single one-time read-only audit script; deletion completed.
- Runtime/CLI/route/scheduler/config/test/CI reference impact: none, because the
  retained artifacts are context authority/evidence and the deleted file was
  never tracked or referenced.

```text
REPOSITORY_HYGIENE = PASS
DEAD_ASSETS_FOUND = 1
DEAD_ASSETS_DELETED = 1
OBSOLETE_CODE_LINES_REMOVED = 0
RETAINED_FOR_EVIDENCE = POST_R3_READINESS_ATTRIBUTION_REPORT_AND_128_ROW_MATRIX
UNRESOLVED_HYGIENE_ITEMS = 0

DATA_SPARSE != PRODUCT_FAILURE
INSUFFICIENT_EVIDENCE_IS_A_VALID_PRODUCT_RESULT
EMPTY_OR_SPARSE_COCKPIT_MUST_NOT_BE_FILLED_WITH_SYNTHETIC_SIGNAL
MODEL_MARKET_DIVERGENCE != MARKET_OPPORTUNITY

ROUND_4 = NOT_STARTED
API_FOOTBALL_PRO_RENEWAL = NOT_AUTHORIZED_NOW
ACTIVE_WHITELIST = 13_UNCHANGED
FREE_BRIDGE_MODE = SHADOW_ONLY
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
```

Machine-readable evidence:

```text
POST_R3_READINESS_ATTRIBUTION_MATRIX.json
SHA256 = 01999b11e5eea10cf4d68460bb5ba6d1f71c83820709adaaa104a1e5992c58fa
ROWS = 128
```
