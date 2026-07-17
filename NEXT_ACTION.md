# W2 Next Action

Status: `MA03_IMMEDIATE_DISPLAY_PASS_WAITING_NATURAL_CYCLES`

The Dashboard has real fixture-scoped observations, but the deployed read path
misclassifies non-clinical stale markets as unavailable because old observations
are not reconciled into the database-frozen card consumed by direct DayView.
The existing schedule also leaves a large OPEN-to-T1 gap.

## Execute next

### MA-01 — Read-only root-cause trace — COMPLETE

Trace fixtures `1492291`, `1492299`, and `1494706` through:

1. persisted `future_market_observation` rows;
2. latest observation projection and fixture identity mapping;
3. canonical AH/TOTALS market and selection-line filtering;
4. MarketQuote construction, source, capture time and hash binding;
5. FME input assembly, semantic status and evidence eligibility;
6. Dashboard DecisionCard blocker precedence.

Confirmed result: fixture-scoped reads returned `6057/6164/3574` observations
for fixtures `1492291/1492299/1494706`, and both AH and TOTALS selectors were
`READY` for all three. The first broken boundary is the missing background
analysis-evidence materialization between successful refresh persistence and the
frozen Dashboard/forward-ledger consumers.

The public HTTP and ledger paths correctly avoid live model rebuilds, but no
background job currently creates a new immutable frozen analysis checkpoint.
The forward ledger therefore recaptures an unavailable frozen card indefinitely.

A direct offline fallback also attempts the unbounded global observation query
when the request cache is not fixture-primed. One diagnostic exec process was
OOM-killed; the API main process stayed healthy with restart count 0. This path
must not be repeated.

### MA-02 — Smallest upstream repair — COMPLETE

PR #333 merged as `main@a9b42a5730f4fea700ec91035874bb67d2e5248c` and implemented a bounded background materializer that:

- reads only the target fixture IDs through the existing fixture-scoped repository API;
- builds analysis evidence outside the public HTTP request path;
- persists an immutable frozen analysis checkpoint consumed by Dashboard and the
  forward ledger;
- prevents per-fixture offline reconstruction from falling back to the unbounded
  global observation query;
- leaves the public `analysis-card` and DayView routes frozen/no-live-rebuild.

Repair that boundary without changing:

- quote freshness thresholds or timestamp provenance;
- FME mathematics, Snapshot v2 semantics or evidence eligibility;
- recommendation, EV, lock, OFFICIAL or production gates;
- league enablement, provider budget or scheduler policy;
- canonical denominator or track isolation.

Local and GitHub validation passed. On staging, fixture-scoped materialization for
`1492291/1492299/1494706` read `6057/6164/3574` observations, generated two
Snapshot v2 records per fixture, and reproduced the same three content hashes on
an identical-input rerun. Public HTTP remained frozen/no-live-rebuild.

### MA-03A — Dashboard stale-market directed repair — IN PROGRESS

Implement and merge one bounded change set that:

- projects database-frozen analysis cards when no forward capture exists;
- keeps odds older than 30 minutes visible as `STALE` with source, capture time
  and source hash, while `NOT_READY`, recommendation, lock and OFFICIAL remain closed;
- runs an idempotent fixture-scoped reconcile for at most 10 kickoff-ordered
  fixtures in the existing zero-provider background cycle;
- writes a new immutable checkpoint only when the input source signature changes;
- binds FME provenance to immutable artifact ID/hash, version, training cutoff,
  feature-as-of and input source hash, failing closed when incomplete;
- adds odds-only `T6_ODDS` between OPEN and T1, never backfills missed T6, and
  retains the existing 30-call tick cap, 120-call daily cap, dedupe and reserve;
- populates existing per-card `next_eval_at` and header `next_refresh_tick` from
  pending legal checkpoint plans;
- counts only true `BLOCKED` cards as data blocked; reports `STALE` separately.

The hourly MA-03 patrol is paused. Do not use its former passive waiting result
as acceptance evidence.

PR #336 merged as `main@7e4d8b7e6011c006952bc14a260f65c76a0e3e79` with all three CI checks passing.
Its first staging attempt passed image revision, artifact, migration, health and
four-service alignment. A zero-provider reconcile processed fixtures
`1523207/1523203/1523204/1523205` and persisted AH/OU cards from 2,980 scoped
observations for the sampled fixture. Immediate DayView acceptance still showed
`MARKET_UNAVAILABLE` because an older forward capture with empty `current_odds`
overrode the newer database-frozen display card. The release was automatically
rolled back to `7ad56cd`; Provider logs remained 532 and the queue remained 0.

The only allowed correction is: when a forward capture has no current odds and
the database-frozen card has real odds, use the database-frozen card for the
bounded display projection. It must already be freshness-degraded to STALE and
must not supply a pick, recommendation, lock or audit identity.

PR #337 merged as `main@81e5c71165da245a209ad30e5779df78e017bfb3`. The second staging attempt
passed revision, artifact, migration, health and four-service alignment. The
same four fixtures displayed AH/OU as STALE; reconcile proved idempotent with
`materialized_count=0`, `unchanged_count=4`, `provider_calls=0`. Their newer
forward captures still carried `decision_tier=WATCH`, so they would enter the
worth-watching region. This triggered a second rollback to `7ad56cd`.

The remaining correction is a source-independent final projection invariant:
every `data_status=STALE` card must be `decision_tier=NOT_READY`, with pick,
recommendation, lock and outcome tracking removed and reason
`DATA_STALE_ODDS`. Full-window counts must apply the same invariant. If an older
forward summary has odds but lacks capture time, provider source or source hash,
the complete database-frozen card must supply the bounded display projection;
the incomplete summary must not hide the stored identity.

PR #338 merged as `main@d571ea1ab16ad0dcda4e857e2249ba5acda62715`
with all three CI checks passing. Its third staging deployment passed image,
artifact, migration, health and four-service SHA alignment. The first bounded
zero-provider run remained fixture-scoped and analysis reconcile was idempotent
(`materialized=0`, `unchanged=4`, `provider_calls=0`), but auto checkpoint mode
wrote four `T-6h` records for fixtures `1523203/1523204` from observations
captured on 2026-07-15. This is not eligible current-cycle evidence.

`DATA-06` is the active blocker: stale observations may power a STALE display,
but the timeline writer must reject them as inputs to a current T6/T1/T15
checkpoint. Keep bounded analysis reconcile independent from timeline writes
when no eligible current quote exists. The four services were immediately
rolled back to `7ad56cd`; do not delete or rewrite the immutable failed-attempt
records.

The directed repair is implemented on
`codex/w2-data06-stale-checkpoint-guard`: every non-opening timeline artifact
requires an observation at most 30 minutes old at execution time, including the
exact 30-minute boundary. The Worker also supports bounded analysis reconcile
with timeline writes disabled, so immediate display verification cannot create
checkpoint artifacts. Scheduler defaults, due windows, quota policy and opening
baseline behavior are unchanged. Targeted validation is `41 passed` plus Ruff
and Mypy PASS; the full suite is `1497 passed, 4 skipped`.

PR #340 passed all three checks and merged as
`main@ebeea00984ebf0d6ade539e9a53c88a1cf2d39c5`. Its staging deployment passed
image, artifact, migration, health and four-service alignment. Immediate public
DayView then reported index counts `STALE=4/BLOCKED=6/WATCH=0`, but all four
materialized cards were replaced by `L1_CARD_TOO_LARGE` fail-closed cards with
empty odds. The full database-frozen `current_odds` contains candidate and
rejected line evidence that does not belong in the bounded public display card.

`DATA-07` is now the only code blocker. Keep the unchanged L1 payload limit and
trim only the public display projection to existing essential odds fields:
line/prices, capture time, provider source, source hash and display line. Do not
delete evidence detail from the frozen checkpoint or expand the public API.
Staging was immediately rolled back to `7ad56cd`; health/ready and public API/Web
release identity confirm the rollback.

The DATA-07 repair is implemented on `codex/w2-data07-bounded-odds`. It replaces
the full database analysis-card spread with an explicit public DayView field
projection and bounds each displayed market to line/prices, capture time,
provider source, source hash, selection policy and display line. Candidate and
rejected line evidence remain in the immutable database checkpoint but do not
enter L1. A 200-candidate regression remains STALE/NOT_READY with visible source
identity and does not become `L1_CARD_TOO_LARGE`. Validation is `1497 passed,
4 skipped`, Ruff PASS and Mypy PASS.

PR #342 passed all three GitHub checks and merged as
`main@1e444d3b7ba952ab9ee829f3e648f58d21946bb8`. Staging image, artifact,
migration, health and four-service SHA gates passed with restart=0 and OOM=false.
Reconcile-only selected four fixtures with `dry_run=true`, timeline writes 0,
`materialized=0`, `unchanged=4` and Provider calls 0.

Immediate public DayView acceptance passed: four cards display AH/OU, capture
time, `api_football` source and source hash as STALE; all 10 cards are NOT_READY,
WATCH/RECOMMEND/lock are 0, and no card is `L1_CARD_TOO_LARGE`. The earliest
`next_refresh_tick` is `2026-07-17T10:00:00Z` (18:00 Beijing).

Current adjudication is `MARKET_DATA_HEALTH=YELLOW` and
`EVIDENCE_ELIGIBILITY=NOT_READY`: display recovery is complete, but current
naturally refreshed quotes and eligible Snapshot v2 evidence do not yet exist.
Do not manually trigger refresh; observe only naturally due T1/T15 cycles.

The production frontend code fixes its Dashboard request mode to `future`, so
that exact public window was also verified. It returns total=40, first page=20,
STALE=4 and true BLOCKED=36. The first four current fixtures have visible odds;
the remaining fixtures have no materialized observations and correctly remain
BLOCKED. WATCH/RECOMMEND/lock and `L1_CARD_TOO_LARGE` are all zero.

### MA-03B — Staging acceptance after merge

The first `a9b42a5` staging attempt passed artifact v1, migration, health and
four-service SHA alignment. Materialized cards restored AH/OU current odds,
capture times, provider source and source hashes. Decision Contract construction
also produced deterministic MarketQuote IDs wherever a selection edge existed.

The attempt was rolled back because sampled observations were stale and all
three fixtures used fallback estimates without complete artifact, train-cutoff
and feature-as-of provenance. They remained correctly blocked by
`DATA_STALE_ODDS`, `MODEL_FAIR_LINE_UNAVAILABLE` and
`DECISION_SOURCE_INCONSISTENT`. Snapshot mathematical reproducibility alone does
not satisfy decision evidence eligibility.

Keep the deployed release and let the scheduler produce naturally due
`T1_LINEUPS` and `T15M_CLOSE` checkpoints. Do not manually invoke the combined
refresh task, force Provider calls or fabricate missed historical T6 records.

GitHub `main@1e444d3b7ba952ab9ee829f3e648f58d21946bb8` is the currently deployed
staging release. It has passed the immediate display gate but not the natural
cycle evidence gate.

Require three consecutive real refresh cycles to demonstrate:

- provider fixtures and odds request success is measured but is not sufficient;
- selected MarketQuote exists for every market claimed available;
- `quote_captured_at`, provider source, quote ID and raw payload hash agree;
- expected Snapshot v2 records are complete, integrity-valid, semantically
  verified and evidence-eligible;
- identical inputs reproduce stable content-addressed artifacts;
- blocker distribution no longer shows systemic `MARKET_UNAVAILABLE` or
  `QUOTE_CAPTURE_TIME_MISSING` when eligible observations exist;
- no recommendation gate, denominator, track, provider budget or historical
  evidence regression.

Acceptance output must be exactly:

- `MARKET_DATA_HEALTH=GREEN`
- `EVIDENCE_ELIGIBILITY=READY`

### MA-04 — Resume frozen acceptance only after MA-03

After `GREEN + READY`, rerun the controlled current capture pre-write gate,
deploy merged main under the existing rollback contract, and complete L1,
Frozen L2, exact identity, denominator, three-track and safety acceptance.

### MA-05 — Policy sequencing

After data and evidence recovery, wait for the Draft Policy ADR. Do not enter
U04 or M2 from this workstream.

## Forbidden now

- treating raw observation volume or HTTP 200 as evidence readiness;
- weakening or bypassing market, freshness, provenance, FME or Snapshot gates;
- changing recommendation, EV, lock, OFFICIAL or production behavior;
- treating the previous passive natural-cycle patrol as sufficient acceptance;
- entering U04 or M2.
