# W2 R0.5 Staging Canary — 2026-07-18

Result: `PASS_LOCAL_DIRECT_RELEASE`

## Release and gates

- Accepted implementation SHA: `4b880b49acb0b33376c61d2cf8bba608a8682c47`.
- Rollback release: `7a5181f3b0cc0e12ae3dbade225d3725b7b06518`.
- Delivery used a local `git archive`; no GitHub fetch, pull, push, workflow or PR.
- Local suite: `1125 passed, 4 skipped`; Ruff, Mypy (227 files), Web typecheck/build,
  acceptance, tracked-output, credential and diff gates passed.
- Isolated predeploy-e2e and staging-parity (`3 passed`) completed. The phase has
  no schema migration, so upgrade/downgrade/upgrade is not applicable.

## Frozen-only canary proof

- Only fixtures `1576804`, `1494701` and `1494210` use the frozen-only read path.
  A non-canary fixture (`1523206`) remained on the bounded legacy path and did not
  expose frozen provenance.
- One initial request, five sequential requests and concurrent cross-fixture
  requests all returned HTTP 200. Each fixture returned one stable response hash
  and the R0.4 artifact hash:
  - `1576804`: `000ba4d8416fc3d5b80886c2678d649e3434d51fd608e6d76af485342c8c26ef`
  - `1494701`: `9be6b5064ff40ad94dff3ecbbbbea8485cd5f8e9bb2bee3bdb37e58f2fca916d`
  - `1494210`: `ca85ffb514db5739f33831b9d22334d3cf391f6a890da95227afb3576f1f48f8`
- An in-container tripwire replaced fixture/raw/global observation readers and the
  legacy analysis builder with fail-on-call functions. The three requests made
  exactly three verified checkpoint reads and zero forbidden calls. Provider and
  model paths were not invoked, and the response path did not read wall-clock time.
- Missing, invalid, identity-conflicting, hash-invalid and schema-incompatible
  checkpoints are covered by contracts that return structured `NOT_READY` without
  rebuilding through the legacy path.

## Product and runtime invariants

- Decision, tier, pick, current odds, quote identity/freshness status, blockers and
  card hash were byte-identical to the pre-switch projection for all three fixtures.
  The only raw audit difference for two fixtures was `evaluated_at`: request time
  was replaced by the frozen manifest reference `2026-07-18T07:23:00Z`. This is an
  evaluation reference, not quote time; authoritative `captured_at` did not change.
- The DayView product projection remained byte-identical with SHA-256
  `f2e282491966350c04a317d39d53424a25d6a09eee5421bb8e249f4b96917280`.
- Provider requests stayed 673, observations 3,757,226, raw payloads 2,223 and
  checkpoints 76 (three canary rows). Recommendation, Gate 5, forward and shadow
  locks stayed zero; queue stayed zero; no business table or ledger write occurred.
- Final RSS was API 231.5 MiB, worker 267 MiB, scheduler 152.2 MiB and Web
  5.484 MiB. Web was 0.968 MiB above its 4.516 MiB baseline; the absolute increase
  is recorded and did not coincide with restart, OOM or product mutation.
- All four services ended healthy with restart zero/OOM false. Scheduler and
  watchdog returned to their exact active state, and canonical readiness stayed 200.

R0.5 is accepted locally. `next_phase=R0.6`.
