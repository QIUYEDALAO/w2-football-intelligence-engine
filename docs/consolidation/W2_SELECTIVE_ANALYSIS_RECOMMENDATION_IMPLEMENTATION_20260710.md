# W2 Selective Analysis Recommendation Implementation - 2026-07-10

Status: code complete pending review. No staging or production deployment has been performed.

## Scope

The first scope is `eliteserien`, `allsvenskan`, and `chinese_super_league`, with
`ASIAN_HANDICAP` and `TOTALS` evaluated independently. Brazil remains disabled
for this release path. World Cup and other competitions are outside this phase.

## Implemented

- `FairMarketEstimate` is the shared model output for AH and totals. A single
  prematch score distribution produces both fair lines; the totals fair line is
  selected from quarter-ball settlement lines rather than using expected goals
  as a line directly.
- R4.1 serving and offline evaluation share the same strength transform and
  eight-match materialization window. Artifact use fails closed when its train
  cutoff is not before the target fixture. The proposed Eliteserien goals/Elo
  fallback remains disabled because that exact feature path has no accepted
  market-specific walk-forward evidence yet.
- AH and totals shadow picks have independent directions, quarter-line
  settlement, same-line decimal CLV, directional line CLV, and per-league-market
  coverage statistics.
- Outcome backfill reads completed fixtures from the all-window read model by
  ledger fixture id. FT, AET, and PEN settle from 90-minute fulltime scores.
- Capture deduplication keeps T-24, T-1, lock-window, and changed-evidence
  snapshots instead of appending unchanged state on every polling tick.
- `analysis_gate` separates data readiness from market/model/evidence
  eligibility. Missing lineups are advisory; model absence, no edge, and
  accumulating forward evidence remain explicit blockers.
- Eligible cards use the selected gate's matching market line and price. The
  strongest market is shown on L1 and the other market remains available in L2.
- At most three `ANALYSIS_PICK` cards are shown per football day. Zero is valid;
  thresholds are never lowered to fill the page.
- Dashboard evidence text reads `analysis_gate` blockers and advisories instead
  of reducing every WATCH card to “waiting for lineups”.

## Release Boundary

`direction_allowed` remains unchanged. Every league-market pair remains
fail-closed until the seven preregistered evidence conditions pass and a
separate approved release PR is merged. Passing AH does not release totals.

`ANALYSIS_PICK` remains outcome tracked and not lock eligible. `RECOMMEND`, EV,
lock, production, and league enablement are unchanged and remain closed.

## Staging Acceptance Still Required

After review and merge, a separately approved staging deployment must verify:

- sanitized staging evidence snapshot is consumed by R1.1;
- shadow picks become non-empty for validated fair-line cards;
- AH and totals snapshots form independent entry/closing pairs;
- completed fixtures produce idempotent outcomes;
- Dashboard reasons match `analysis_gate` and lineup remains advisory;
- a full matchday shows zero to three selective analysis picks when and only
  when the relevant league-market release gate has been approved;
- provider daily usage remains at or below 120.

No runtime data, raw provider payload, credential, report output, or artifact is
committed by this implementation.
