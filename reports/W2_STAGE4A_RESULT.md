# W2 Stage 4A Result

## Scope

Stage 4A establishes the offline data ingestion foundation. It does not execute
live API calls, does not call Football-API or DeepSeek, does not ingest W1 data,
does not model, and does not recommend.

## Delivered

- Provider ports and API-Football offline adapter
- Generic secondary odds provider port with undecided status
- Raw payload store with SHA256 and append-only semantics
- API-Football normalizer for offline fixture and odds payloads
- Ingestion replay service for RAW -> NORMALIZED -> FEATURE
- Quota manager
- Retry/backoff and circuit breaker primitives
- Freshness evaluator
- Snapshot scheduler for T-72h through Closing
- Ingestion run, request log, quota usage, sync cursor, and freshness alert tables
- Offline Gate 2 PROVISIONAL replay fixture and scripts

## Validation Log

Executed and passed:

- `uv sync --all-groups`
- `uv run python scripts/check_w2_stage1_contracts.py`
- `uv run python scripts/check_w2_stage3_data_model.py`
- `uv run python scripts/check_w2_stage4_ingestion.py`
- `uv run python scripts/replay_provider_fixture.py`
- `uv run ruff check .`
- `uv run mypy src apps`
- `uv run pytest -q`
- `W2_ENVIRONMENT=test W2_DATABASE_URL=sqlite+pysqlite:///.local/stage4a-validation.db uv run alembic upgrade head`
- `W2_ENVIRONMENT=test W2_DATABASE_URL=sqlite+pysqlite:///.local/stage4a-validation.db uv run alembic downgrade base`
- `W2_ENVIRONMENT=test W2_DATABASE_URL=sqlite+pysqlite:///.local/stage4a-validation.db uv run alembic upgrade head`
- `make smoke`
- `git diff --check`

Offline replay result:

```json
{
  "gate2_status": "PROVISIONAL",
  "raw_payload_count": 2,
  "provider_mapping_count": 4,
  "odds_observation_count": 4,
  "odds_replay_duplicate_count": 0,
  "feature_snapshot_count": 1,
  "freshness_alert_count": 2
}
```

WARN_ONLY:

- pytest reports a FastAPI TestClient upstream deprecation warning from
  `httpx`; no W2 behavior is affected.

## Required Future Checkpoint

```text
LIVE_INGESTION_CHECKPOINT_REQUIRED
```

User approval is required for W2 API key injection, a single controlled network
request, and test fixture scope.

## Audit Artifacts

- `reports/W2_STAGE4A_W1_READONLY_AUDIT.txt`
- `reports/W2_STAGE4A_W2_SHA256.txt`
