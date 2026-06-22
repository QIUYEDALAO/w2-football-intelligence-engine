# Stage10B Dashboard Live Wiring

## Scope

Stage10B wires the read-only dashboard to validated read models. It does not deploy to staging,
restart services, run migrations on the staging database, or enable recommendations.

## Project Current Matchday Snapshot

Run inside the API container or a local environment with `W2_DATABASE_URL` set:

```bash
uv run python scripts/project_stage10b_live_snapshot.py \
  --snapshot-root /path/to/matchday/snapshots \
  --fixture-id 1489399 \
  --latest \
  --database-url-from-env
```

Use `--dry-run` to validate the snapshot without writing read-model checkpoints.

## Web Routing

The browser uses same-origin paths only:

- `/api/v1/...`
- `/api/ops/...`

The web container proxies `/api/` to the API service. The browser should continue to access only the
web port.

## Safety

The projector rejects snapshots with hash mismatch, non append-only manifests, kickoff leakage,
non WATCH/SKIP decisions, or enabled formal recommendation fields. Runtime JSON remains a server-side
input to the projector only; the frontend never reads it directly.
