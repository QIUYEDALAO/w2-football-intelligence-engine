# W2 FAH Private Data Handoff V1

Private FAH data is expected outside Git at:

`/Users/liudehua/.hermes/data/w2/fah`

The same path can be supplied with `W2_FAH_DATA_ROOT`. The master pipeline only reads that directory or the explicit `--data-root`; it does not scan the home directory, connect to staging/production, call providers, or write private data into Git.

Required schemas live in `docs/data/contracts/`:

- `formal_ah_source_registry.v1.schema.json`
- `historical_market_observation.v1.schema.json`
- `historical_result.v1.schema.json`
- `team_crosswalk.v1.schema.json`
- `player_crosswalk.v1.schema.json`
- `registered_roster_snapshot.v1.schema.json`
- `player_valuation.v1.schema.json`

Run without private data:

```bash
uv run --python 3.12 python scripts/run_fah_master_pipeline.py \
  --artifact-root /tmp/w2-fah-final-artifacts \
  --pr-number 0 \
  --dry-run
```

Run with private data in an isolated database:

```bash
W2_FAH_DATA_ROOT=/Users/liudehua/.hermes/data/w2/fah \
uv run --python 3.12 python scripts/run_fah_master_pipeline.py \
  --artifact-root /tmp/w2-fah-final-artifacts \
  --database-url "$W2_TEST_POSTGRES_URL" \
  --pr-number 0 \
  --write
```

The required terminal state remains `MANUAL_APPROVAL_REQUIRED`; this handoff does not approve formal AH, lock recommendations, production recommendations, OFFICIAL capture, or any deployment.
