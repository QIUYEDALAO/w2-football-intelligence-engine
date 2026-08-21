# Production coverage window — implementation and runbook

## Purpose

Collect one week of execution evidence for dead-code and dead-state reachability analysis without changing W2 business logic, Scheduler policy, Provider behavior, model thresholds, or database writes.

Coverage is evidence of execution, not proof of semantic liveness. A line not observed during the window remains a removal candidate only after static call-graph, migration, capability, and Owner-intent checks.

## Implementation

- Standard dependency: `coverage.py` 7.15.4, locked by `uv.lock` and included in the runtime base.
- Offline base update: `infra/local-release/Dockerfile.runtime-base-coverage` installs the exact locked Linux wheel on top of the fixed dependency base; it never inherits from a prior release.
- Configuration: `config/coverage/production.coveragerc`.
- Compose overlay: `infra/compose/production-coverage.override.yml`.
- Reboot persistence: `infra/systemd/w2-staging-coverage.conf` adds only the coverage overlay to the existing unit commands and is removed when the window ends.
- Measured packages: `/app/src/w2` and `/app/apps` only.
- Data path: existing shared runtime volume, `/app/runtime/coverage/.coverage.*`.
- Separate static contexts: `production-api`, `production-worker`, and `production-scheduler`.
- Multi-process handling: parallel data files, multiprocessing support, and standard subprocess/fork/`os._exit` patches.
- SIGTERM persistence is enabled so a graceful Compose stop writes data before the normal non-instrumented command is restored.

## Preconditions

1. Build a new runtime base because the locked dependency set changed.
2. Build the release image only `FROM` that runtime base, with `--pull=false --network=none`.
3. Run `/usr/local/bin/w2-release-preflight <image>` and the standard image config/readiness checks.
4. Create `/opt/w2/shared/runtime/coverage` with write permission for uid/gid 10001; do not alter existing runtime data.
5. Capture baseline API latency, container CPU/RSS, `/ready`, `/v1/version`, scheduler/worker health, and exact quota/ledger counters.

## Activation

Add the overlay after the existing production Compose files. Only the `api`, `worker`, and `scheduler` commands change. Database, Redis, migration, web, ports, volumes, capability flags, and Provider settings remain inherited from the current authority.

Perform a short production canary first. Fail closed and restore the original Compose command set if any of these occur:

- readiness or workspace endpoint failure;
- worker/scheduler restart loop or missed natural checkpoint;
- material API latency, CPU, RSS, or disk-growth regression;
- quota, provider-request, integrity, opportunity, or attempt anomaly;
- coverage data cannot be persisted by the unprivileged `w2` user.

If the canary passes, keep the same instrumented containers for seven continuous days. Record exact UTC start/end timestamps and image digest in the completion section below.

## Finalization

1. Gracefully stop the instrumented `api`, `worker`, and `scheduler` so SIGTERM data is saved.
2. Copy the raw `.coverage.*` files to a timestamped, read-only evidence directory before combining them.
3. Restore the normal Compose command set and verify `/ready`, `/v1/version`, worker, scheduler, and natural checkpoint continuity.
4. Run `coverage combine`, then emit JSON and HTML reports from the exact release image/config.
5. Record hashes for raw files and combined reports. Do not delete raw coverage data.
6. Use the report only to complete dead-state reachability and removal proposals; do not delete code or schema automatically.

## Run record

- Status: `ACTIVE`.
- Exact release: `eab6dca7997a21a215b9929a3ac2a7365cf27631`.
- Python digest: `sha256:e648c2ddd8efc2898e6905230c19403f37b512b3eaf3b009531ff89dc324a3cf`.
- Runtime-base lock hash/tag: `b79cee9bde52d8f099b6fdf8e6a733dfc3e321729300b69b8c5c8f8054acfef1` / `b79cee9bde52d8f0`.
- Runtime-base digest: `sha256:28da7ee884208ff33bb5936a9ced1463db58302a9ae1c20cc85c8cf79307105b`.
- Image acceptance: `w2-release-preflight` PASS, RootFS `15/20`, image write smoke PASS.
- Predeploy backup: `/opt/w2/backups/db/20260821T042406Z/w2-20260821T042406Z.dump`, 107,468,216 bytes.
- Active seven-day window: `2026-08-21T04:37:34Z` through `2026-08-28T04:37:34Z`.
- Reboot-persistent window record: `/opt/w2/shared/runtime/coverage/window.json`.
- Release record: `/opt/w2/shared/releases/eab6dca7997a21a215b9929a3ac2a7365cf27631.json`, SHA-256 `6d8df77a41f419e4979e6b4148b361da54e98e30d439e37c7b5ce3370bb88a59`.
- Failed/paired canary raw files are retained under `failed-canary-20260821T0426Z/` and `canary-control-rollback-20260821T0429Z/`; they are excluded from the active window.
- Paired busy-stage observation: Scheduler CPU was about 78–82% without coverage and 83–85% with coverage; API `/ready` averaged about 0.111 s without coverage and 0.140 s with coverage. Worker busy spikes returned to idle, all services stayed healthy with zero restarts, and memory remained within configured limits.
- Activation checks: schema `0069_outcome_ledger_run_state`, workspace HTTP 200, measurement status `MEASURABLE`, opportunity/attempt identity integrity all zero, no active claim or near-term due slot at switch, and no Provider error or 429.
- Final raw-data manifest and combined report hashes: pending window completion.
