# W2 R0.4 Staging Canary — 2026-07-18

Result: `PASS_LOCAL_DIRECT_RELEASE`

## Release and gates

- Accepted implementation SHA: `7a5181f3b0cc0e12ae3dbade225d3725b7b06518`.
- Rollback release: `7e383e2f21fcd0b488ffc95cd58c6c6394291855`.
- Delivery used local `git archive`; no GitHub fetch, pull, push, workflow or PR.
- Local suite: `1118 passed, 4 skipped`; Ruff, Mypy (227 files), Web typecheck/build,
  acceptance, tracked-output, credential and diff gates passed.
- Isolated predeploy-e2e and staging-parity (`3 passed`) completed. The phase has
  no schema migration, so upgrade/downgrade/upgrade is not applicable.

## Deterministic materialization proof

- The canary namespace is `analysis-card:canary:v1:` and does not replace any
  dashboard or public checkpoint.
- Fixtures `1576804`, `1494701` and `1494210` were materialized with the explicit
  evaluation reference `2026-07-18T07:23:00Z`.
- Immediate repeated builds produced byte-identical payloads and identical source
  and artifact hashes:
  - `1576804`: `000ba4d8416fc3d5b80886c2678d649e3434d51fd608e6d76af485342c8c26ef`
  - `1494701`: `9be6b5064ff40ad94dff3ecbbbbea8485cd5f8e9bb2bee3bdb37e58f2fca916d`
  - `1494210`: `ca85ffb514db5739f33831b9d22334d3cf391f6a890da95227afb3576f1f48f8`
- Sequential and 24 concurrent checkpoint reads returned one hash per fixture.
  Unit contracts proved missing input, identity conflict, old schema and hash
  corruption fail closed; a blocked batch leaves no partial checkpoint.

## Product and runtime invariants

- Public reads were not switched. The three public analysis-card decision, tier,
  pick and card hashes remained unchanged.
- The R0.3 `window=all` DayView product projection remained byte-identical with
  SHA-256 `f2e282491966350c04a317d39d53424a25d6a09eee5421bb8e249f4b96917280`.
- Alembic stayed `0023_create_checkpoint_refresh_schedule`; provider requests
  stayed 673, observations 3,757,226 and raw payloads 2,223. Checkpoints changed
  only from 73 to 76 for the three canary artifacts.
- Recommendation, Gate 5, forward and shadow locks remained zero; queue stayed zero.
- API RSS was 213.8 MiB against its 296.2 MiB cap. All four services ended healthy
  with restart zero/OOM false; scheduler and watchdog returned to their exact
  active state.

R0.4 is accepted locally. `next_phase=R0.5`.
