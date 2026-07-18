# W2 R4 approval packs — 2026-07-18

These three gates are independent. Preparation is not approval and does not
change runtime flags.

## 1. Champion review — PREPARED, NOT APPROVED

Evidence available:

- fixed 24-fixture offline snapshot with chronological 12/12 split;
- deterministic paired bootstrap (1,000 samples, seed 7);
- log loss, multiclass Brier, RPS, ECE and coverage comparison;
- rolling-form state correction changed all validation feature rows, but the
  selected model does not consume that feature and probability deltas are zero;
- candidate remains shadow-only and the incumbent rollback path is unchanged.

Decision: no evidence currently justifies changing champion. A later explicit
user approval is required, after sufficient canonical forward evidence and
stability review. Read-only production approval cannot approve this gate.

## 2. RECOMMEND/lock review — PREPARED, NOT APPROVED

Contract evidence available:

- non-READY projections clear pick, current/executable odds, recommendation ID,
  lock eligibility and outcome tracking;
- RECOMMEND requires complete provenance and cannot silently degrade to
  ANALYSIS_PICK;
- DayView, Dashboard and analysis-card browser contracts cover READY, STALE,
  BLOCKED, INCOMPLETE and checkpoint-missing states;
- VALIDATION, OFFICIAL and SHADOW ledger outcomes are separate and capture to
  outcome identity is explicit.

Decision: RECOMMEND, lock and OFFICIAL remain unchanged. The 200 canonical
settled-fixture evidence target and an explicit later user approval still apply.
Champion approval, if it occurs, cannot approve this gate.

## 3. Read-only production review — CONDITIONALLY AUTHORIZED

The user authorized read-only production after three consecutive real Beijing
09:00 staging patrols pass on the same implementation SHA and images.

Current candidate:

- implementation SHA: `7e4c0aea790f2bce678b4ab6a2d20ba51d583316`;
- release identity, Alembic current/head and readiness artifacts: MATCH;
- original Dashboard layout retained with corrected VALIDATION figures;
- public-request provider delta 0, queue 0, restart/OOM/exit137 0;
- scheduler and watchdog active, rollback release/images retained;
- cycle state: `0/3`, next eligible patrol 2026-07-19 09:00 Asia/Shanghai.

Approval rule:

- each cycle must be a distinct natural-day 09:00 patrol;
- UNKNOWN or hard failure does not count;
- data-contract, statistics, implementation or runtime fixes reset the
  consecutive count to zero; copy-only changes do not;
- after 3/3 PASS, the existing public single-host deployment is recorded as
  read-only production without rebuilding or changing the candidate;
- this authorization excludes writes, champion, RECOMMEND/lock and OFFICIAL.

## Rollback checklist

If a cycle hard gate fails: restore the retained release, revision-scoped four
service images, migration image, `current` symlink and exact scheduler state;
verify health/readiness/version, queue 0, provider patrol delta 0 and restart/
OOM status before resuming collection. Consecutive cycles then restart at 0/3.
