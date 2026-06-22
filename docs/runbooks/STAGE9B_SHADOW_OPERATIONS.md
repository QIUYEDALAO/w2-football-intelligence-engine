# Stage9B Shadow Operations

Local replay:

```bash
uv run python scripts/run_stage9b_shadow_cycle.py --dry-run
uv run python scripts/run_stage12b_shadow_comparison.py
uv run python scripts/check_w2_gate5_preflight.py
```

This stage does not deploy, migrate staging, restart containers, or unlock the
deployment freeze. Runtime statuses are read from PostgreSQL shadow tables when
available. Reports remain audit artifacts.

Allowed public states remain `NOT_READY`, `SKIP`, and `WATCH`.
