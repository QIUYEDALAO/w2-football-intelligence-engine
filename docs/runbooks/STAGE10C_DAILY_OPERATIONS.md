# Stage10C Daily Operations

Run a local dry-run:

```bash
uv run python scripts/run_stage10c_daily_cycle.py --dry-run
uv run python scripts/check_w2_stage10c.py
```

Deployment is intentionally paused in Stage10C. Staging Scheduler wiring must be
approved separately. Do not enable production, DeepSeek, candidates, or formal
recommendations.
