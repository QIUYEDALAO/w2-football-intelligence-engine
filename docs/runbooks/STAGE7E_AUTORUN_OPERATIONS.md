# Stage 7E Autorun Operations

Stage 7E enables live forward holdout operation only for local or staging. Production remains
disabled.

## Enablement

Use a local/staging environment only:

```bash
W2_ENVIRONMENT=local uv run python scripts/enable_stage7e_autorun.py
```

The script writes `runtime/stage7e/local_autorun_config.json`. That file is gitignored and must not
contain secrets. API keys remain environment-only.

## Controlled Cycle

Run one immediate cycle and one scheduler-triggered cycle:

```bash
W2_ENVIRONMENT=local uv run python scripts/run_stage7e_live_cycle.py
uv run python scripts/check_w2_stage7e.py
```

The cycle order is:

1. status/quota check
2. cached fixture discovery first
3. eligible WATCH/SKIP lock
4. CAPTURED_AT market snapshot only for newly eligible locks
5. append-only result sync
6. Gate audit

If there is no eligible fixture, the cycle must not request odds.

## Safety Stops

Stop immediately on:

- production environment
- frozen hash mismatch
- DeepSeek enabled
- recommendation enabled
- quota remaining unknown
- quota remaining below `1500`
- HTTP 401, 403, or 429
- duplicate lock overwrite attempt
- kickoff-after-lock violation
- provider key or auth header appearing in logs

External notifications remain disabled. Operational alerts are local artifacts only.

## Expected Status

- `STAGE_7E=COMPLETED`
- `FORWARD_HOLDOUT_AUTORUN=ENABLED_LOCAL_OR_STAGING`
- `GATE_4_NATIONAL_1X2=PROVISIONAL_FORWARD_HOLDOUT_PENDING`
- `STAGE_9=BLOCKED`
