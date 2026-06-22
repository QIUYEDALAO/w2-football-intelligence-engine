# W2 Release Train 2 Runtime Patch Result

Status: LOCAL_PATCH_READY

Original blocker:

- `SHADOW_CLI_NOT_AVAILABLE_IN_RUNTIME_IMAGE`

Root cause:

- Release Train 2 runtime validation attempted to execute `/app/scripts/run_stage9b_shadow_cycle.py` inside the scheduler container.
- Runtime images intentionally did not copy `scripts/`, so script-path commands were unavailable after deployment.
- Several related commands also depended on repository cwd, reports, or W1-local paths.

Runtime command inventory:

- Stage9B Shadow Cycle: `w2.strategy.shadow_cycle_cli` / `w2-shadow-cycle`
- Gate5 Preflight: `w2.gates.gate5_preflight_cli` / `w2-gate5-preflight`
- W1/W2 sanitized comparison importer: `w2.shadow.comparison_import_cli` / `w2-shadow-comparison-import`
- Stage7I observer: `w2.observability.stage7i_observer_cli` / `w2-stage7i-observer`

Packaging change:

- Runtime Dockerfiles install the W2 package with `uv sync --no-dev --frozen --no-editable`.
- Runtime Dockerfiles copy `src/`, `apps/`, and `config/`, but do not copy `scripts/` or `reports/`.
- `.dockerignore` excludes runtime, reports, raw/processed data, logs, cache, and `.env` files.

Contract tests:

- Module `--help` entrypoints are covered.
- Console script `--help` entrypoints are covered.
- Temporary-directory execution is covered.
- Wheel install entrypoints are covered.
- Gate5 cannot return `CLOSED`.
- Shadow CLI cannot emit formal candidate or recommendation output.

Docker runtime validation:

- `LOCAL_DOCKER_UNAVAILABLE`; local Docker server was not available.
- Wheel/venv packaging contract was used instead.

Server state:

- Server remains unchanged.
- No release upload, `/opt/w2/current` switch, staging migration, systemd restart, container recreation, Stage7I observer start, W1 modification, DeepSeek call, CANDIDATE, or RECOMMEND occurred.

Deployment:

- Patch 1 deployment is pending explicit approval.
