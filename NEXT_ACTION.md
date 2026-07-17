# W2 Next Action

Status: `DATA_PIPELINE_BLOCKED`

The Dashboard fixtures are present, but every fixture observed in the latest
three refresh cycles fails closed because the decision path has no selected
MarketQuote, no quote capture time, and no evidence-eligible FME Snapshot v2.

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

### MA-03 — Three-cycle staging acceptance — ACTIVE/BLOCKED ON NATURAL CYCLES

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

Do not force refreshes or bypass the provider interval. The next eligible real
cycles are naturally due Super League checkpoints beginning at
`2026-07-17T10:00:00Z`. Redeploy merged main under the existing rollback
contract, then require three consecutive post-merge cycles.

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
- deploying before MA-01 and MA-02 are complete;
- entering U04 or M2.
