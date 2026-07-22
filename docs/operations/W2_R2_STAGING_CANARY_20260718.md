# W2 R2 staging canary — 2026-07-18

Result: `PASS_LOCAL_DIRECT_RELEASE`

## Exact candidate and gates

- Accepted implementation SHA: `6f300d028939bb227683cc644461a7dc67988a77`.
- Rollback baseline: R1 `103813d7e8ea422756472cb9b4369e3c80876d09`.
- Delivery used local `git archive`; no GitHub fetch, pull, push, workflow or PR.
- Final local suite: `1158 passed, 4 skipped`; Ruff, Mypy, all-stage verify,
  Web typecheck/build, five Chromium E2E cases, acceptance, tracked-output,
  credential-scan and diff gates passed.
- Exact-candidate staging-host parity passed `3/3`; isolated predeploy-e2e
  passed. R2 has no schema change, so upgrade/downgrade/upgrade is not
  applicable; isolated and formal `upgrade head` completed at
  `0023_create_checkpoint_refresh_schedule`.

## R2 corrections and offline result

- R2.1 persists rolling-form state and supports deterministic versioned snapshot
  restore/replay.
- R2.2 constrains the half-goal input contract to the implemented `0.5` market.
- R2.3 emits bookmaker heuristic `signal_strength`, accepts legacy
  `confidence` only at input projection, and labels the score as neither
  probability nor hit rate in Web.
- R2.4 used the fixed 24-fixture snapshot, chronological `12/12` split and
  paired bootstrap (`1,000`, seed `7`). Rolling-form features changed on all 12
  validation rows, while the selected model currently does not consume the
  feature; log loss, multiclass Brier, RPS and ECE deltas were all `0.0`.
- The result remains `SHADOW_CANDIDATE_ONLY`; champion, league/threshold scope,
  RECOMMEND/lock, OFFICIAL and production did not change.

Machine-readable offline evidence:
`W2_R2_OFFLINE_CORRECTION_EVALUATION_20260718.json`.

## Canary invariants

- The second canary froze provider requests `694`, future observations
  `3,776,149`, raw payloads `2,236`, checkpoints `120`, forward events `20`,
  all lock tracks `0`, queue `0`, and ledger hash
  `2b4dba0ce768e1a9f2947381d1e9a11990df051fccf9221046470a606c372c88`.
  All stayed unchanged through the stopped-scheduler canary.
- Three real legacy frozen checkpoints (`1576804`, `1494701`, `1494210`) passed
  15 sequential and 6 concurrent reads with one stable hash per fixture. Public
  bookmaker intent and market output contained `signal_strength` and no legacy
  heuristic `confidence`.
- A read-only R1 rollback sidecar proved all 39 DayView cards byte-equivalent
  after normalizing only the allowed `confidence → signal_strength`, derived
  `card_hash`, and request-time `next_eval_at` fields. Normalized semantic hash:
  `7d018fa8c285f003030b3e800f213df0a34c04e1c4847aefc6d849f1c4ef1383`.
  Pick and lock counts stayed zero.
- Root and deprecated readiness paths returned the same READY body; health,
  version, readiness manifest, artifact hashes and API/Web release identities
  matched the exact candidate.
- Final cgroup anonymous RSS was API `224,268,288`, worker `267,640,832`,
  scheduler `151,183,360`, and Web `3,801,088` bytes, each within the accepted
  R1 baseline times `1.20`. All services finished healthy with restart, OOM and
  exit137 zero; queue was zero.
- Scheduler and watchdog returned to their exact pre-canary active state. After
  restoration, normal scheduled collection advanced provider requests to `698`
  and raw payloads to `2,238`; this occurred after the zero-delta canary boundary
  and is not attributed to a public request.

## Failure, rollback and repair evidence

- The first full suite exposed a stale documentation test that required at least
  one phase to remain `implemented` after R1 acceptance. It was replaced by a
  structural four-state vocabulary/boundary check; the entire suite was rerun.
- The first formal canary exposed a real R2.3 gap: verified legacy frozen
  analysis-card payloads bypassed the new heuristic projection and returned
  `bookmaker_intent.confidence`. The release, five image tags, `current`, public
  metadata, scheduler and watchdog were restored to exact R1 before work
  continued. A frozen legacy regression was added, the public frozen projection
  was fixed without changing artifact identity, and every local/isolated/formal
  gate was rerun on `6f300d0`.
- An initially hand-expanded, incorrect candidate SHA label was quarantined
  before any formal switch. Subsequent identities were taken directly from
  `git rev-parse HEAD` and verified end to end.
- Temporary R1 comparison containers did not satisfy canonical readiness because
  they intentionally lacked full release mount identity; they were used only for
  read-only DayView comparison and removed. Formal candidate readiness remained
  the authoritative readiness gate.

R2 is `staging_accepted`; `next_phase=R3`. R3 is append-only forward shadow
evidence and does not authorize champion, RECOMMEND/lock, OFFICIAL or production.
