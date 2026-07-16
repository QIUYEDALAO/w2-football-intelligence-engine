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

## Pending frozen L2 audit recovery release · 2026-07-16

- Code target: `main@5005df4e4873e618399bedaf4f32c9e5bbb2ef8f`; deployed staging remains the known-good rollback release `c4bcceb5cb777639251e0db91a9c1f54f5b9c87b` until this docs-only gate merges and the single approved batch deployment begins.
- Recovery PRs #305–#307 replace public live analysis reconstruction with an exact, bounded frozen-capture projection, make `analysis-card` fail closed, and change Boss View's first L2 expansion from five requests to one identity-bound request. Odds timeline is a separate secondary lazy request.
- The projection is capped at 512 KiB, two estimates and 169 score cells per estimate. The client and server caches are capped at 64 entries with 15-minute TTL and per-key single-flight.
- The sanitized OOM regression fixture is `1576804`. Predeploy verification is `1406 passed, 4 skipped`; Ruff, Mypy, TypeScript, Web build, acceptance and tracked-output guards pass. Frozen denominator evidence remains VALIDATION `43/16/27`, Wide `60/22/38`, with duplicate/conflict/identity-unmatched/cross-track contamination all zero and Strict at zero.
- Deployment must preserve rollback images and manifest before switching services. Any API OOM, exit 137, restart or cgroup `oom_kill` increase, regression-fixture 5xx, response over 512 KiB, L1/L2 identity mismatch, denominator change, track contamination, RECOMMEND/lock/OFFICIAL activation, historical rewrite or credential exposure requires immediate rollback to `c4bcceb5cb777639251e0db91a9c1f54f5b9c87b`.
- Production remains excluded. Provider calls, timeout increases, model/gate/threshold/artifact changes and league enablement are not authorized by this release record.

## Rolled-back frozen L2 audit recovery release · 2026-07-16

- Attempted release: `2658d37f8ec7e69de5b5737ff37fb8e9cd822c35`. Image revision, artifact v1, migration head, API readiness and the DayView business gate passed before the four services were aligned on the attempted SHA.
- The public L1 gate failed before L2 stress testing: `today` returned 15/15 HTTP 200 but warm latency was about 1.70–1.84 seconds; `next36` returned 15/15 HTTP 200 with p95 about 4.99 seconds and max 5.10 seconds; `future` declared about 4.04 MB and timed out at 12 seconds after transferring only about 0.99–1.14 MB.
- The attempted release had no API OOM, cgroup `oom_kill`, exit 137 or restart. Observed API RSS rose from about 223.6 MiB to 328.9 MiB. Because L1 is a prerequisite, the historical OOM fixture and broader L2 stress matrix were not executed and L2 recovery was not claimed.
- The rollback manifest and four frozen service images restored `c4bcceb5cb777639251e0db91a9c1f54f5b9c87b`. All four services are running with restart count 0; readiness and watchdog are healthy. Provider and queue deltas are zero. Historical ledger hashes are unchanged through 2026-07-14 and the active 2026-07-15 file preserves the complete predeploy byte prefix.
- Canonical evidence remains VALIDATION `43/16/27` and Wide `60/22/38`, with duplicate/conflict/identity-unmatched/cross-track contamination zero and Strict at zero. The required next change is a separate bounded/paginated L1 `future` projection; raising timeouts or changing recommendation, model, threshold, artifact or league policy is not an acceptable fix.

## Pending bounded future DayView and frozen L2 recovery release · 2026-07-16

- Code target: `main@b72005b6364dfbf3adaea4de98c448157d9dcab0`; staging remains on rollback target `c4bcceb5cb777639251e0db91a9c1f54f5b9c87b` until the approved batch deployment begins.
- PRs #310–#312 replace full-ledger/raw-capture L1 projection with a bounded capture index, stable cursor pagination and explicit Boss View load-more. Page/card limits are 512 KiB/24 KiB; page size is 20 by default and 50 maximum.
- Full-window counts remain separate from page counts. Cursor identity includes release, requested window, fixture and ledger fingerprints; stale cursors return 409 and cannot merge snapshots. Frozen L2 identity remains unchanged.
- Predeploy verification is `1422 passed, 4 skipped`, with Ruff, Mypy, TypeScript, Web build, acceptance and tracked-output checks passing. Each code PR passed verify, staging-parity and predeploy-e2e.
- Deployment order remains scheduler stop, safety baselines and rollback images, builds/revision check, migration smoke/migration, API readiness, worker, Web and scheduler. L1 public pagination gates must pass before any L2 stress request.
- Immediate rollback triggers include page/card limit violation, page union mismatch, duplicate fixture, snapshot mixing, timeout/502/504, API OOM/restart/exit137, L2 regression, identity mismatch, denominator/track change, historical rewrite, RECOMMEND/lock/OFFICIAL activation or credential exposure.
- Production, provider calls, timeout changes, model/gate/threshold/artifact changes and league enablement are not authorized.

## Rolled-back bounded future DayView pagination release · 2026-07-16

- Attempted release: `22d1357bba6fc4b761c8cafae98dd917ea0caf25`; rollback target: `c4bcceb5cb777639251e0db91a9c1f54f5b9c87b`. All four services were aligned before acceptance and all four were restored after the gate failed.
- The payload fix worked: future returned 40 fixtures over two pages of about 41 KiB each, maximum card size about 1.8 KiB, union 40, duplicates 0 and stale cursor HTTP 409. There were no 502, 504, browser timeout, API restart, exit 137 or cgroup OOM event.
- The release still failed the latency gate. Warm public requests were about 1.6–2.0 seconds versus the 1.5-second p95 target, and the second page took 3.87 seconds versus the 3-second target. Frozen L2 staging stress was therefore not run.
- Rollback readiness and API/Web release sync passed with restart count 0. Provider count remained 485, queue remained 0 and the before/after ledger manifest hash was identical. Production, recommendations, locks and OFFICIAL writes remain excluded.

## Public edge observer evidence gate · 2026-07-16

- Repository target is `main@b303588d6a3a2e7288c46877206f7f5ef31eeb87` after PRs #324 and #325. Stable staging remains `c89555b98cbcf2c41ecf999eefce9f5c0a9627f5`; API, Web, worker and scheduler were read-only verified healthy and aligned with restart count 0.
- GitHub-hosted run `29492624556` produced a preliminary latency PASS, while the current external host exceeded the future page 1 warm reused p95 gate at `2.086251s`. Neither artifact is formal evidence because every retained request ID is empty and per-sample timestamps are absent.
- The current formal classification is `OBSERVER_COVERAGE_INSUFFICIENT`. No release, migration, service replacement or rollback occurred, so the known stable staging release remains active.
- The next change is observer-only evidence collection. It must preserve no-proxy IPv4, actual fresh/reused connection behavior, all original thresholds and the 12-second timeout. Existing non-qualifying artifacts must not be reused after the fix.
- Production, provider calls, business database writes, historical rewrites, `RECOMMEND`, locks and OFFICIAL writes remain excluded.

## Rolled-back final observer/L1/Frozen-L2 acceptance release · 2026-07-16

- Attempted release: `461e4973b957981132cfcfd9fc370e0021f8bae2`; rollback target: `c89555b98cbcf2c41ecf999eefce9f5c0a9627f5`. The pre-switch four-service rollback manifest is `/opt/w2/shared/rollback-manifest-461e4973b957981132cfcfd9fc370e0021f8bae2.json` with mode 600.
- All migration/API/Web/worker/scheduler images carried the target revision. Artifact v1 passed, migration remained `0023_create_checkpoint_refresh_schedule (head)`, and the release switched API → worker → Web → scheduler with all four services healthy and restart count 0.
- L1 passed: today `3/3`, next36 `13/13`, future `40/40` over pages `20+20`, duplicate 0, max page 43,249 bytes, max card 1,697 bytes, stale cursor 409 and concurrency 1/2/4/8 all HTTP 200. Direct API/isolated-nginx warm p95 were `0.048960s/0.041900s`.
- Frozen L2 legacy fixture `1576804` returned HTTP 200 with `historical_compatibility=true` and `corrected_evidence=false`. Current fixture `1492140` failed before the stress matrix: L1 exact capture `720d570b...`, estimate `null`, returned HTTP 409 `AMBIGUOUS_CAPTURE`. A different v2 capture passed integrity and semantics but cannot replace the L1-bound identity.
- The exact-identity hard gate triggered immediate rollback. API, Web, worker and scheduler are again healthy on `c89555b...`, restart=0, OOM/oom_kill=0 and `/health`/`/ready` pass. Provider count stayed `508`, active provider calls `0`, Redis queue `0`, ledger manifest stayed `4cb1568b...` with the same 36,430,067 bytes, and no migration or historical rewrite occurred.
- Final status is `BLOCKED_STAGING_ACCEPTANCE`. The only next release work is a minimal unambiguous Snapshot-v2 identity selection for the L1 card; production, timeout, thresholds, FME, model artifacts, RECOMMEND, lock and OFFICIAL remain unchanged.
