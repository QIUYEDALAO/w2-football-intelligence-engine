# W2 Release and Rollback V1

Release governance objects:

- ModelCard
- ReleaseCandidate
- ReleaseApproval
- RollbackManifest
- ChangeFreeze
- ReleaseAudit

Rules:

- New versions require complete walk-forward, ablation, calibration, and Shadow.
- Old artifacts are immutable.
- Single-match results cannot trigger release.
- Gate 4/5/6 must be closed before production release.
- Stage 15A publishes no model.
- P2 governance documents do not authorize production release, FORMAL/CANDIDATE,
  runtime `beats_market=true`, or runtime competition whitelist expansion.
- Analysis-only is an acceptable long-term state when S2 evidence is
  insufficient.

## Staging release record · 2026-07-15

- Release: `staging-3d67a769704e544fb544979c96cf3162328d090c`.
- API, Web, worker and scheduler revisions are all
  `3d67a769704e544fb544979c96cf3162328d090c`.
- Database revision: `0023_create_checkpoint_refresh_schedule (head)`; the database was already at
  the target head, so the release added no migration data writes.
- The rollback manifest is stored outside Git at
  `/opt/w2/shared/rollback-manifest-3d67a769704e544fb544979c96cf3162328d090c.json` with mode 600.
  Previous images and release metadata remain available; rollback was not performed.
- Staging operations authentication is enabled with a service credential and evidence-based Compose
  network CIDRs. Credentials and environment contents must never be copied into repository context.
- Initial cold-cache concurrency produced seven transient 504 responses. This is an open performance
  warning, not a reason to raise timeouts without evidence and not an authorization to modify decision
  thresholds.
- Production remains unchanged. `RECOMMEND`, recommendation locks, league enablement and model
  artifacts remain unchanged.

## Pending staging validation-recovery release · 2026-07-15

- Target: `main@51baa80fc4a8878b6a76e3782ff6586f1f39f269`; currently deployed staging remains `3d67a769704e544fb544979c96cf3162328d090c` until the single approved batch deployment completes.
- Included recovery PRs: #295 canonical outcome denominator, #296 Dashboard/ledger single-flight cache, #297 FME blocker precedence, and #298 Strict AH canary checker.
- The protected predeploy ledger baseline is `/opt/w2/shared/validation-baselines/denominator-20260715-20260715-071647Z`; its manifest SHA-256 is `a7b92f76197c30008b78a4cfaa7efc508b15087f34217003f79595f37c21e5f4`. Rollback and acceptance must never modify this baseline or the source ledger.
- Frozen-baseline release gate: VALIDATION canonical=16, Wide Shadow canonical=22, duplicate/conflict/cross-track contamination=0, Strict checker=`NO_CORRECTED_STRICT_CANDIDATE_YET`. A mismatch blocks deployment or triggers rollback.
- Deployment order remains scheduler stop, safety/watermark capture, image build and revision verification, migration smoke/migration, API readiness, worker, Web, scheduler, and final SHA alignment. A rollback manifest must be created before service replacement.
- Postdeploy cold-key acceptance must produce HTTP 200 at concurrency 1/2/4/8, one owner per key, no repeated ledger parse per fingerprint, no 502/504 and no timeout increase. The warm 225-request matrix must have no 5xx, provider calls or queue growth.
- Production remains excluded. The release must not change thresholds, artifacts, league enablement, `RECOMMEND`, locks or OFFICIAL data.

## Completed staging validation-recovery release · 2026-07-15

- Release: `staging-c4bcceb5cb777639251e0db91a9c1f54f5b9c87b`; API, Web, worker and scheduler are healthy on the same revision with restart count 0 and no OOM event.
- The pre-switch rollback manifest is `/opt/w2/shared/rollback-manifest-c4bcceb5cb777639251e0db91a9c1f54f5b9c87b.json` with mode 600. Previous images and release metadata remain available; rollback was not required.
- Migration stayed at `0023_create_checkpoint_refresh_schedule (head)`. Deployment and acceptance performed no business-database write, provider request, historical ledger rewrite, OFFICIAL write or lock creation; scheduler provider delta and Celery queue delta were both 0.
- Frozen and live denominator acceptance both produced VALIDATION `43/16/27` and Wide Shadow `60/22/38` for raw/canonical/audit-only rows, with zero canonical duplicates, conflicts, identity-aware unmatched outcomes or cross-track contamination.
- Cold concurrency 1/2/4/8 produced 15/15 HTTP 200, one owner per key, expected waiters and no 502/504. The warm matrix produced 225/225 HTTP 200. Cold p95 remained 109.6345 seconds and warm p95 18.4901 seconds, so latency remains a separate performance warning; nginx timeout was not increased.
- FME acceptance observed 40 fixtures and 80 snapshots: READY=38, INSUFFICIENT=42, integrity/semantic invalid=0 and accidental promotion=0. Corrected Strict remains `NO_CORRECTED_STRICT_CANDIDATE_YET` at 0/35 and 0/100.
- Production remains unchanged and blocked. `RECOMMEND`, locks, thresholds, artifacts and league enablement remain unchanged.

## Rolled-back Boss View performance release · 2026-07-15

- Attempted release: `4dbaf517f62af47fbfbc11acfb21092e8b1380f2`; rollback manifest: `/opt/w2/shared/rollback-manifest-4dbaf517f62af47fbfbc11acfb21092e8b1380f2.json` (mode 600).
- Lightweight DayView passed the public nginx cold/warm latency and single-flight checks with no L1 5xx. A lazy L2 `analysis-card` request returned 502; kernel evidence confirmed a memory-cgroup OOM kill at roughly 1022048 KiB anonymous RSS, followed by Docker exit-137 restart. The release therefore failed its L2 isolation gate.
- Staging was restored to `c4bcceb5cb777639251e0db91a9c1f54f5b9c87b`; API, Web, worker and scheduler are healthy and aligned on that revision. Provider and queue deltas were zero, and canonical denominator evidence was unchanged.
- The performance commits remain merged on `main` for follow-up correction, but are not deployed. Production remains unchanged; no timeout, recommendation, lock, threshold, artifact or league setting was changed.
