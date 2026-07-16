# W2 Frozen L2 Exact Capture Identity and Evidence Capture Design

Date: 2026-07-17
Status: APPROVED_FOR_IMPLEMENTATION
Scope: internal forward-evidence capture, exact frozen occurrence identity, L1/L2 binding, and staging acceptance

## Problem

The forward-ledger command builds an authoritative Dashboard card containing
immutable FairMarketEstimate Snapshot v2 evidence, then passes that card through
the public bounded DayView projection before writing the capture. The public
projection intentionally removes full snapshots. Using it as an evidence source
therefore creates later capture rows with no snapshots or estimate identity.

For fixture `1492140`, content hash `720d570...` has two such occurrences. Both
contain zero Snapshot v2 rows and no estimate identity. Older eligible-v2
captures are not decision/quote/card/evidence equivalent and must not be
substituted.

## Invariants

- Public L1 remains bounded to 24 KiB per card and never exposes full snapshots.
- Forward evidence is derived from the authoritative same-request Dashboard card,
  never from the public L1 projection.
- Existing ledger rows remain immutable. Recovery is append-only.
- A controlled recapture uses the real execution time and must occur before
  kickoff; it never backdates evidence.
- Controlled recapture performs no provider request, business database write,
  model retraining, or historical rewrite.
- FME mathematics, Snapshot schema, estimate/model/quote IDs, score matrix,
  settlement, denominator, tracks, thresholds, pagination, timeout,
  recommendation policy, locks, OFFICIAL, artifacts, league enablement, and
  provider scheduling do not change.

## Architecture

### Internal evidence adapter

Add an internal adapter that converts the full Dashboard payload into the
forward-capture view expected by `build_forward_outcome_records`. It reuses the
existing DayView decision semantics for fixture and decision fields while
copying only the immutable evidence fields required by the ledger:

- `fair_market_estimate_snapshots`
- `fair_market_estimate_ids`
- `fair_market_estimates` compatibility view
- `analysis_gate` and `analysis_gates`
- pick/non-pick and frozen market context

The CLI uses this adapter instead of the public bounded DayView builder. The HTTP
DayView path does not call the adapter and cannot opt into full evidence.

The adapter fails closed per card. A card with no eligible Snapshot v2 can still
be represented as NOT_READY/WATCH evidence, but it cannot advertise an audit
estimate or corrected evidence.

### Shared frozen identity helper

Create `src/w2/tracking/frozen_capture_identity.py` as the only implementation of:

- `capture_content_hash(record)`
- `audit_capture_id(record)`
- `capture_estimate_identity(record)`

`capture_content_hash` preserves the existing capture/evidence/card hash
precedence without changing stored hashes.

`audit_capture_id` derives `aci_<sha256>` over canonical JSON containing schema
`w2.audit_capture_identity.v1` and the frozen fields fixture ID, football day,
environment, captured time, checkpoint, content hash, and record type. It is
computed at read time and never written back to historical rows.

`capture_estimate_identity` accepts only estimates belonging to the same record
and only eligible Snapshot v2 rows whose integrity and semantics verify. Its
selection precedence is pick, top-level capture, analysis gate, unique matching
audit strategy identity, then a unique eligible snapshot. Multiple unresolved
candidates fail closed with `AUDIT_ESTIMATE_IDENTITY_AMBIGUOUS`; absence fails
closed with `AUDIT_ESTIMATE_IDENTITY_MISSING`.

### L1 binding

The DayView capture index continues selecting the latest valid prematch capture.
It exposes:

- `audit_capture_id`
- `audit_capture_hash`
- `audit_estimate_id`
- `audit_identity_status`
- `audit_blocker`
- `audit_available`

`audit_available=true` requires the occurrence ID, content hash, and eligible
estimate to resolve from that same row. Older v2 rows never replace a newer
different row.

### Frozen L2 lookup

Lookup order is occurrence ID, fixture cross-check, content hash cross-check,
and estimate cross-check. An occurrence ID bypasses hash aggregation but never
bypasses the cross-checks.

Legacy callers without occurrence ID retain fail-closed compatibility. Hash plus
estimate may select a unique row. Hash-only duplicates, or duplicates sharing
the same estimate, remain HTTP 409.

### HTTP and Web

`GET /v1/fixtures/{fixture_id}/audit-detail` accepts `capture_id` and returns
`source_capture_id`, `source_capture_hash`, and `source_estimate_id`.

Boss View sends occurrence ID, content hash, and estimate ID together. Its cache
key includes all three identities, fixture ID, and API release SHA. A failed
triple-bound request never retries hash-only and never falls back to live model
reconstruction or another capture.

## Controlled recapture

After the code PR merges and the release is deployed, run one explicit
append-only forward capture before fixture `1492140` kickoff. The command builds
the authoritative full Dashboard from existing read-model data, uses the new
internal evidence adapter, and writes through existing atomic append/dedup logic.

Before committing the write, a dry run must prove:

- the target record is prematch;
- at least one same-record Snapshot v2 passes integrity and semantics;
- one authoritative estimate is selected;
- provider calls and business writes remain zero.

If any condition fails, do not write and classify the result as
`HARD_BLOCKER_CURRENT_SCOPE`.

## Error handling

- Missing or invalid occurrence ID: fail closed.
- Capture ID/hash mismatch: HTTP 409.
- Capture ID/estimate mismatch: HTTP 409.
- Ambiguous eligible estimate: L1 audit unavailable and explicit blocker.
- Missing eligible estimate: L1 audit unavailable and explicit blocker.
- Oversized/corrupt ledger input: retain existing bounded lookup errors.
- Post-kickoff controlled recapture: forbidden; no write.

## Verification

Tests cover deterministic/distinct occurrence IDs, estimate precedence and
same-record membership, ambiguity, lookup ordering, triple mismatch, legacy
compatibility, bounded public L1, no live rebuild, the sanitized fixture
regressions, unchanged denominator, and unchanged track isolation.

Required local gates are full pytest, Ruff, Mypy, Web typecheck/build,
acceptance, tracked-output guard, and diff check. GitHub verify,
staging-parity, and predeploy-e2e must pass before merge.

Staging then runs L1 pagination/performance regression and the complete Frozen
L2 matrix. Any identity mismatch, 409 for the current v2 fixture, OOM/restart,
5xx/timeout, denominator change, track contamination, provider request,
business write, historical rewrite, RECOMMEND/lock/OFFICIAL activation, or SHA
misalignment triggers rollback.
