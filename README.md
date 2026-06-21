# W2 Football Intelligence Engine

Current stage: Stage 2 Engineering Foundation, built on the protected Stage 1 Product Contract.

This repository now contains the W2 engineering base: Python src layout, minimal
FastAPI service, Celery worker, scheduler heartbeat, SQLAlchemy/Alembic database
foundation, React TypeScript status UI, Docker Compose local infrastructure,
tests, CI, and runbooks.

It still does not have real recommendation capability, does not call DeepSeek,
does not call Football-API, does not connect to odds providers for production
data, does not implement a model, and does not replace W1. Gate 0 remains
PROVISIONAL and cannot generate a real `RECOMMEND`.

## Quick Start

Install locked dependencies with Python 3.12:

```bash
make setup
```

Run local checks:

```bash
python3 scripts/check_w2_stage1_contracts.py
make lint
make typecheck
make test
make smoke
```

Start local infrastructure when Docker is available:

```bash
make up
make down
```

Render Stage 1 example cards:

```bash
python3 scripts/render_ai_card_text.py examples/recommend/card.json
python3 scripts/render_ai_card_text.py examples/watch/card.json
python3 scripts/render_ai_card_text.py examples/skip/card.json
```

## Stage Boundaries

- Stage 1 contracts remain protected and covered by
  `scripts/check_w2_stage1_contracts.py`.
- Stage 2 establishes runtime and delivery foundations only.
- Stage 3 may add football entities, ingestion, feature pipelines, models, and
  strategy work after a separate approval gate.
- API keys must come from environment variables or a future secret manager.
- Example values in `.env.example` are placeholders and must not be used as real
  credentials.
