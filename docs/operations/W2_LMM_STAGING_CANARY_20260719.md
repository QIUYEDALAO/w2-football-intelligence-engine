# W2 LMM0–LMM8 staging acceptance — 2026-07-19

## Outcome

LMM0–LMM8 is `staging_accepted` on the exact local implementation
`198c603db424371014e1f738596a9befa8a9486c`. The release was built and
deployed directly from the local repository; GitHub was not accessed or
synchronized.

The three consecutive Beijing 09:00 read-only cycles are reset to `0/3`.
Because this deployment was accepted after the 2026-07-19 patrol window, the
first eligible cycle is 2026-07-20 09:00 Asia/Shanghai. The same implementation
SHA, images and data contract must remain in place for all three cycles.

## Immutable candidate

- Release: `/opt/w2/releases/198c603a037d4dd11744b1c898a559f2368077eb`
- Source archive: `/tmp/w2-lmm-198c603.tar`
- Archive SHA-256:
  `ee0f54ba6a6abec4a0e24f5b894b4af70e65cceaa1c4207728dc8d6a4cbb5722`
- Alembic revision: `0024_create_lineup_intelligence`
- API image:
  `sha256:013598a195f74bd4fd8ae94ab377cfa3bfa1aace2a09c49aafc93a759aef738c`
- Worker image:
  `sha256:2a5f0a3d941ae4f972d7802dcf2c99c19beb87a33796710255cdfea4287b15f9`
- Scheduler image:
  `sha256:70f128684d35b50122836d5c3c8181cf5ed9e798b4897c2700c6a90ac6c841b4`
- Web image:
  `sha256:de356348794a010c6db18187044e12a9ea76f6f6ea7a89f186c59ac4e81570c9`

## Gate evidence

- Python: `1206 passed / 4 skipped`; Ruff, Mypy and all repository stages PASS.
- Web: TypeScript, production build and Playwright `8/8` PASS.
- Acceptance, tracked-output guard, secret scan and `git diff --check` PASS.
- Exact-archive isolated predeploy PASS, including policy packaging, 0024,
  fake refresh, frozen artifact, analysis-card and database assertions.
- Exact-archive staging parity: `3 passed`.
- Isolated Alembic upgrade/downgrade/upgrade: `3 passed`.
- Public request tripwire: provider call `0`, model rebuild `0`, global reader
  `0`, DB/ledger/lock write `0`.

## Imported and materialized authority

- Transfermarkt player references: `50,149`
- Valuation observations: `31,507`
- Structured lineup snapshots: `60`
- Structured lineup players: `1,527`
- Team lineup baselines: `60`
- Player identity mappings: `660`
- Read-model checkpoints: `122`, unchanged in count through canary

The versioned policy classifies the current canary coverage as C, so numeric
lineup adjustments remain disabled and equal to zero. This is deliberate:
LMM4 does not apply a public xG adjustment until the frozen offline evaluation
meets its pre-registered sample and quality gates. Lineup readiness,
provenance, explanation and independent AH/OU selection remain active.

## Public canary

Fixture `1494210` was read once, then five times sequentially. Fixtures
`1494210`, `1494212` and `1494213` were then read concurrently. The card hash
was stable and the frozen artifact remained `VERIFIED`.

The tested WATCH card had no manufactured recommendation: `pick` was absent,
`secondary_picks=[]`, `scoreline_picks=[]` and
`scoreline_reference=null`. Health, canonical readiness, legacy readiness,
version, DayView, Dashboard API and the Web root all returned HTTP 200.

Canary deltas were zero for provider requests, observations, raw payloads,
checkpoints, results, locks, queue and ledger. Final observed counts included
provider requests `738`, observations `3,812,702`, raw payloads `2,263`,
checkpoints `122`, results `20`, locks `0` and queue `0`.

## Runtime and rollback discipline

All four services finished healthy with restart count `0`, OOM false and no
exit 137. Final RSS was API `165.9 MiB`, worker `299 MiB`, scheduler
`132.7 MiB` and Web `5.488 MiB`, all within the accepted bound. Scheduler and
watchdog were restored to their pre-canary active state.

Earlier candidates were rejected and fully rolled back before acceptance:

- non-ready cards leaked directional scorelines;
- lineup baselines were not persisted and frozen artifacts remained old;
- the runtime policy path was hidden by the shared config mount;
- `uv run` attempted a runtime dependency sync and caused a restart.

Regression tests and release/runtime corrections were added for each cause.
One later probe incorrectly expected HTTP 200 from the API root; the API's 404
was correct, and the Web-root probe subsequently passed. It was not a product
failure and did not mutate staging.

## Authorization boundary

This acceptance changes only read-only `ANALYSIS_PICK` AH/OU selection and its
supporting lineup contract. Champion, formal RECOMMEND, lock, OFFICIAL and
write-enabled production remain disabled or unchanged. Read-only production
recognition remains conditional on three consecutive eligible 09:00 patrols.
