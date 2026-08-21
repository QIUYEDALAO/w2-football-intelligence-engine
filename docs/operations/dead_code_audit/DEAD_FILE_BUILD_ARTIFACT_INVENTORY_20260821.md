# Dead files and build-artifact inventory — 2026-08-21

## Result

The worktree measured 848,092 KiB (828.2 MiB). A first-pass cleanup can reclaim at most 451,636 KiB (441.1 MiB, 53.3%) without removing active dependency trees. No file has been deleted.

The 441.1 MiB is a candidate ceiling, not an approved deletion set: `.local` contains release-build workspaces, including a recently modified directory, so exact age/ownership protection must be applied before cleanup.

## Inventory

| Path class | Measured KiB | MiB | Treatment |
|---|---:|---:|---|
| `.local` | 403,936 | 394.5 | Rebuildable release-build workspaces; inventory per directory, protect current/recent builds |
| `.mypy_cache` | 26,696 | 26.1 | Safe cache candidate |
| Project `__pycache__` under `src/tests/scripts/migrations/apps` | 16,452 | 16.1 | Safe cache candidate |
| `apps/web/test-results` | 2,976 | 2.9 | Safe generated test-output candidate after confirming no retained evidence links |
| `apps/web/.local` | 976 | 1.0 | Generated local app artifact candidate |
| `.pytest_cache` | 340 | 0.3 | Safe cache candidate |
| `apps/web/dist` | 260 | 0.3 | Rebuildable frontend output |
| **Low-risk candidate ceiling** | **451,636** | **441.1** | **53.3% of worktree** |
| `.venv` | 210,476 | 205.5 | Active local Python dependency tree; rebuildable, but not dead |
| `apps/web/node_modules` | 153,904 | 150.3 | Active frontend build/test dependency tree; rebuildable, but not dead |

Including both active dependency trees would raise the theoretical reclaimable total to 816,016 KiB (796.9 MiB, 96.2%), but doing so would convert routine work into a reinstall and is not recommended as dead-file cleanup.

## Protected paths and constraints

- Protect `.local/release-build-72ded8c7`: it was last modified at `2026-08-21T04:14:20+0800`. No matching build process was observed at measurement time, but recent activity is sufficient to fail closed.
- Preserve `docs/review_packages/SC21_FACTOR_INPUT_CHAIN/`, `oracle/`, `scripts/`, and `contracts/`; they are release runtime inputs.
- Preserve `.venv` and `apps/web/node_modules` during the first cleanup pass.
- Preserve any test result referenced by a review package, acceptance record, or current branch evidence.
- Cleanup must enumerate exact paths, reject symlinks/reparse points, and use a recoverable move-to-trash/quarantine step before permanent removal.

## Proposed first cleanup batch (not yet executed)

1. `.mypy_cache`, `.pytest_cache`, and project `__pycache__` directories.
2. Unreferenced `apps/web/test-results`, `apps/web/.local`, and `apps/web/dist`.
3. `.local/release-build-*` directories only after applying an age threshold, protecting the newest/current build, and confirming no process, release manifest, evidence document, or local tag references the directory.

This sequencing makes the small cache batch independently reversible and keeps the high-yield `.local` decision evidence-driven.
