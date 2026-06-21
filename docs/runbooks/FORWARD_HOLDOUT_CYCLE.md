# Forward Holdout Cycle

Run:

```bash
uv run python scripts/run_stage7c_forward_cycle.py
uv run python scripts/check_w2_stage7c.py
```

The cycle is idempotent and supports `--dry-run` and `--budget`.

Operational rules:

- keep at least 2500 provider requests reserved
- do not print keys or auth headers
- do not request DeepSeek
- do not emit candidate or recommendation records
- do not backfill closing odds into earlier phases
- do not evaluate Gate 4 before the pre-registered sample size
