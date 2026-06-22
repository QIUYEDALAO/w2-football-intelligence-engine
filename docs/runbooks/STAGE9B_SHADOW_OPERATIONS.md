# Stage9B Shadow Operations

Local replay:

```bash
uv run python -m w2.strategy.shadow_cycle_cli --execution-kind RETROSPECTIVE --dry-run --json
uv run python -m w2.shadow.comparison_import_cli --dry-run --json
uv run python -m w2.gates.gate5_preflight_cli --dry-run --json
```

Runtime containers use installed package entrypoints, not `/app/scripts`:

```bash
w2-shadow-cycle --execution-kind FORWARD --dry-run --database-url-from-env --json
w2-gate5-preflight --dry-run --database-url-from-env --json
```

This stage does not deploy, migrate staging, restart containers, or unlock the
deployment freeze. Runtime statuses are read from PostgreSQL shadow tables when
available. Reports remain audit artifacts.

Allowed public states remain `NOT_READY`, `SKIP`, and `WATCH`.
