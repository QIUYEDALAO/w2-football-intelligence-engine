# World Cup Dry Run

Run:

```bash
uv run python scripts/run_stage13a_world_cup_dry_run.py
uv run python scripts/check_w2_stage13a.py
```

The dry-run is offline. It reads the versioned World Cup profile and local
Stage5B fixture data, then generates:

- collection phases
- lineup check time
- closing cutoff
- WATCH/SKIP lock windows
- settlement time
- Gate audit time
- explanatory-only match importance context

Forbidden:

- API calls
- production enablement
- true Shadow runtime
- DeepSeek
- CANDIDATE
- RECOMMEND
