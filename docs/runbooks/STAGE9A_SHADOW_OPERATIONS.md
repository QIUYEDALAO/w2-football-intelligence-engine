# Stage 9A Shadow Operations

Run the offline replay:

```bash
uv run python scripts/run_stage9a_shadow_replay.py
uv run python scripts/check_w2_stage9a.py
```

The replay does not call the network, does not deploy to staging, and does not
modify runtime services. Outputs are written under `reports/`.

Ops read endpoints:

- `GET /ops/shadow-strategy/status`
- `GET /ops/shadow-strategy/locks`
- `GET /ops/shadow-strategy/evaluations`
- `GET /ops/shadow-strategy/replay`

All endpoints are read-only and disabled in production by the existing
operations API guard.
