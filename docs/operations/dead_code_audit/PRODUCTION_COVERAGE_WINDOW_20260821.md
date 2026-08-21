# Production coverage window — implementation and runbook

## Purpose

Collect one week of execution evidence for dead-code and dead-state reachability analysis without changing W2 business logic, Scheduler policy, Provider behavior, model thresholds, or database writes.

Coverage is evidence of execution, not proof of semantic liveness. A line not observed during the window remains a removal candidate only after static call-graph, migration, capability, and Owner-intent checks.

## Implementation

- Standard dependency: `coverage.py` 7.15.4, locked by `uv.lock` and included in the runtime base.
- Offline base update: `infra/local-release/Dockerfile.runtime-base-coverage` installs the exact locked Linux wheel on top of the fixed dependency base; it never inherits from a prior release.
- Configuration: `config/coverage/production.coveragerc`.
- Compose overlay: `infra/compose/production-coverage.override.yml`.
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

- Status: implementation prepared; production canary not yet recorded.
- Exact release/image digest: pending.
- Canary UTC start/end: pending.
- Seven-day UTC start/end: pending.
- Final raw-data manifest and report hashes: pending.
