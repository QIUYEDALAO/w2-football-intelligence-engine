# Live Ingestion Verified

Stage 4B verifies one controlled API-Football live smoke only when
`W2_API_FOOTBALL_API_KEY` is present in the process environment and the script is
run with `--live`.

Rules:

- Allowed domain: `https://v3.football.api-sports.io`
- Target request count: 20 or fewer
- Hard request limit: 200
- Runtime raw responses are stored under ignored `runtime/live_smoke/<run_id>/`
- Reports are sanitized and must not contain API keys or Authorization headers
- No recommendation, model, strategy, or AI behavior is enabled

Run:

```bash
uv run python scripts/run_stage4b_live_smoke.py --live
```

Validate:

```bash
uv run python scripts/check_w2_stage4b_live_smoke.py
```

