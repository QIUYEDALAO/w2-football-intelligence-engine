# ADR-0002: Engineering Foundation

## Status

Accepted for W2 Stage 2.

## Context

W2 Stage 1 defined product boundaries, recommendation card contracts, examples,
and gate language. Stage 2 needs an engineering base without turning on data
collection, model inference, strategy generation, or real recommendations.

## Decision

Use a Python 3.12 src-layout service foundation with FastAPI, Pydantic V2,
SQLAlchemy 2, Alembic, Celery, Redis client support, PostgreSQL driver support,
pytest, Ruff, mypy, and pre-commit. Use React and TypeScript for a minimal web
status application. Docker Compose provides local placeholders for API, worker,
scheduler, web, PostgreSQL, Redis, and MinIO.

The first database migration creates only `system_metadata`. Football entities,
market models, candidate generation, settlement models, and recommendation
strategy are explicitly out of scope.

## Consequences

The repository can now run checks, migrations, health endpoints, and CI without
calling Football-API, DeepSeek, paid providers, or W1. Gate 0 still cannot
produce a real `RECOMMEND`.

