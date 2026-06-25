# W2 Deploy Drift Audit

- Generated: 2026-06-25
- Scope: read-only audit from repository refs and recorded staging deployment reports
- No staging host access, no `.env` read, no deployment, no migration apply
- Current main baseline: `5e896d76297dcba0a4ee928984c6125d23dfdb12`
- Current stacked work branch: `feat/package-a-core-db-persistence`

## Evidence Sources

- `reports/W2_CURRENT_HANDOFF.md`
- `reports/W2_RELEASE_TRAIN_3A_RESULT.md`
- `reports/W2_RELEASE_TRAIN_3A_R1_RESULT.md`
- `reports/W2_RELEASE_TRAIN_3A_R2_RESULT.md`
- `reports/W2_RELEASE_TRAIN_3A_R3_RESULT.md`
- `reports/W2_RELEASE_TRAIN_3A*_DEPLOYMENT.json`
- Local git refs for `fix/release-train2-runtime-entrypoints`,
  `feat/stage9a-shadow-strategy`, and Release Train 3A repair commits

## Staging State Recorded In Handoff

| Item | Recorded value |
|---|---|
| Staging app revision | `23c89be4d2a32019d8d21bb9b102ae0b7ca15c16` |
| Branch containing revision | `fix/release-train2-runtime-entrypoints` |
| Alembic version table | `0017_create_stage9a_shadow_strategy` |
| Deployment freeze | `ACTIVE` |
| Gate3 | `PARTIAL` |
| Gate5 | `OPEN` |
| candidate | `false` |
| formal_recommendation | `false` |

The recorded staging revision is not the current `main` revision. It includes Release Train 2
runtime entrypoint work and the Stage9A shadow-strategy migration lineage.

## Current Staging Code Drift Against Main

`git log main..23c89be4d2a32019d8d21bb9b102ae0b7ca15c16` contains:

1. `7074aee` Stage10B live dashboard wiring
2. `9be4ce4` AH/totals market valuation correction
3. `9f76bbe` dashboard valuation field exposure
4. `b5d3543` Stage6B market value normalization
5. `397fdfa` Stage10C daily matchday
6. `db13b8e` Stage10D Beijing matchday reconciliation
7. `ed8cf00` Stage9A shadow strategy engine
8. `43b7d7f` Release Train 2 shadow/Gate5 preflight
9. `dd96c79` shadow runtime entrypoint packaging
10. `23c89be` virtualenv runtime command exposure

This branch also deletes or replaces several Gate3/Stage7I future-refresh files that are present
on main. Those deletions must not be blindly merged while Package A is restoring future-refresh.

## Migration Drift

| Revision | Present on current main before this fix | Present in recorded staging | Action |
|---|---:|---:|---|
| `0017_create_stage9a_shadow_strategy` | no | yes | Must be added to main migration history |
| `0018_create_future_refresh_persistence` | no | no | Must follow Stage9A as the next mainline head |

The previous Package A core branch used `0017_create_future_refresh_persistence`, creating a
revision collision with staging's actual Alembic head. This work fixes the graph by importing
Stage9A as `0017` and moving future-refresh persistence to `0018` with
`down_revision="0017_create_stage9a_shadow_strategy"`.

## Release Train 3A Attempts

Release Train 3A target revisions were attempted and rolled back. They are not the recorded
steady-state staging app revision.

| Attempt | Target revision | Result | Staging after rollback |
|---|---|---|---|
| 3A | `fcfba08824f42917d30bc8d0742ea99d2fc18349` | scheduler dispatch disabled | `23c89be4d2a32019d8d21bb9b102ae0b7ca15c16` |
| 3A-R1 | `2d80e04b52af2b6ec957c554968c2c60a3a0cec0` | policy unavailable in scheduler | `23c89be4d2a32019d8d21bb9b102ae0b7ca15c16` |
| 3A-R2 | `371a9cb8618e7f47324e6ea9a2c9be35ca63199e` | runtime permission denied | `23c89be4d2a32019d8d21bb9b102ae0b7ca15c16` |
| 3A-R3 | `5e1179f2502e6fe78c7a0a58c81dcacf9341dc53` | shared runtime not writable | `23c89be4d2a32019d8d21bb9b102ae0b7ca15c16` |

Those repair commits are now represented on main through the current `5e896d7` baseline and
Package A work, except the runtime-writability approach is superseded by DB persistence.

## Required Mainline Actions

1. Add `0017_create_stage9a_shadow_strategy` plus its SQLAlchemy table definitions to main.
2. Make future-refresh persistence revision `0018`, not `0017`.
3. Keep Package A DB persistence as the accepted fix for `SHARED_RUNTIME_NOT_WRITABLE`; do not
   continue ACL/chmod/chown/runtime-write retries.
4. Treat most of `fix/release-train2-runtime-entrypoints` as a separate drift bundle. It contains
   dashboard, matchday, shadow operations, runtime entrypoint, and many deletion-heavy changes that
   need their own reconciliation before any broad merge.

## Main Missing But Staging Running

The recorded staging app revision includes code paths not present on main:

- Stage10B dashboard live read-model wiring
- Stage6B market value engine changes
- Stage10C/10D matchday and Beijing matchday paths
- Stage9A shadow strategy runtime
- Stage9B/Gate5 preflight/runtime entrypoint packaging

These code paths are outside Package A. For this batch, only the Stage9A migration lineage is
required to unblock A5 safely.

## Disposition

- Must merge now: Stage9A migration lineage and models.
- Merge now as Package A: future-refresh DB persistence after Stage9A.
- Defer/re-audit separately: Stage10B/10C/10D, Stage6B, Stage9B/Gate5 runtime entrypoints, and
  deletion-heavy removal of Gate3/Stage7I files.
- No evidence in the recorded reports that staging/production migrations were applied during
  Release Train 3A attempts after rollback; the Alembic table stayed at
  `0017_create_stage9a_shadow_strategy`.
