# W2 Stage 3 Result

## Scope

W2 Stage 3 establishes the unified football data model. It does not call the
network, Football-API, DeepSeek, W1, collectors, model training, or strategy
engines. It does not enable real recommendation capability.

## Delivered

- Domain entities with UUID identity and UTC time validation
- Pydantic schemas with unknown fields forbidden
- SQLAlchemy persistence models with relationships, foreign keys, unique
  constraints, idempotency keys, and time indexes
- Alembic migration `0002_create_stage3_domain_model`
- Provider identity mapping, raw payload reference, and provenance contracts
- Decimal odds/line primitives and AH/OU settlement helpers
- Data layer policy: RAW, NORMALIZED, FEATURE, PREDICTION_STRATEGY
- Stage 3 checker and tests

## Validation Log

Executed and passed:

- `uv sync --all-groups`
- `uv run python scripts/check_w2_stage1_contracts.py`
- `uv run python scripts/check_w2_stage3_data_model.py`
- `uv run ruff check .`
- `uv run mypy src apps`
- `uv run pytest -q`
- `W2_ENVIRONMENT=test W2_DATABASE_URL=sqlite+pysqlite:///.local/stage3-validation.db uv run alembic upgrade head`
- `W2_ENVIRONMENT=test W2_DATABASE_URL=sqlite+pysqlite:///.local/stage3-validation.db uv run alembic downgrade base`
- `W2_ENVIRONMENT=test W2_DATABASE_URL=sqlite+pysqlite:///.local/stage3-validation.db uv run alembic upgrade head`
- `make smoke`
- `git diff --check`

WARN_ONLY:

- pytest reports a FastAPI TestClient upstream deprecation warning from
  `httpx`; no W2 behavior is affected.

## Audit Artifacts

- `reports/W2_STAGE3_W1_READONLY_AUDIT.txt`
- `reports/W2_STAGE3_W2_SHA256.txt`
