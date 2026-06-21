# Long Term Operations

Run:

```bash
uv run python scripts/run_stage15a_operations_dry_run.py
uv run python scripts/check_w2_stage15a.py
```

Defaults:

- `W2_OPERATIONAL_AUTORUN=false`
- `W2_EXTERNAL_ALERTING=false`
- `W2_PRODUCTION_RELEASE=false`

The dry-run writes local reports only. It sends no external notification and
does not release models.
