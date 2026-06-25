# Stage7I 24h Observation

Stage7I observation must run through the installed W2 package entrypoint, not a
repository script path.

```bash
w2-stage7i-observer \
  --expected-revision "$EXPECTED_REVISION" \
  --runtime-root runtime/stage7i \
  --duration-hours 24 \
  --sample-interval-seconds 300 \
  --json
```

For a one-sample validation:

```bash
uv run python -m w2.observability.stage7i_observer_cli \
  --expected-revision "$EXPECTED_REVISION" \
  --runtime-root runtime/stage7i-check \
  --once \
  --json
```

The observer reads actual revision from `/opt/w2/current/DEPLOYMENT_REVISION`
unless `--current` is supplied. It does not read `.env`, API keys, database
credentials, reports, W1 files, or runtime provider payloads.
