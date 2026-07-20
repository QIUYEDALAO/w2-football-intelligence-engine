# W2 Football Intelligence Engine

## Sol / Codex Context

Start here for every Web Sol review or Codex handoff:

`docs/context/W2_GITHUB_CONTEXT.md`

That file is the single human-facing GitHub context entrypoint. Older roadmap,
handoff, and status files remain as internal evidence sources referenced from
that entrypoint; do not use them as the first review prompt.

Current stage: Stage 3 Unified Football Data Model, built on the protected Stage 1 Product Contract and Stage 2 Engineering Foundation.

This repository now contains the W2 engineering base plus the Stage 3 unified
football data model: domain entities, Pydantic schemas, SQLAlchemy persistence
models, Alembic migrations, odds canonicalization, and settlement primitives.

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

Run Stage 3 data-model checks:

```bash
uv run python scripts/check_w2_stage3_data_model.py
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
- Stage 2 establishes runtime and delivery foundations.
- Stage 3 establishes football data identity, time, odds, persistence, and
  provenance foundations only.
- Later stages may add ingestion, feature pipelines, models, and strategy work
  after a separate approval gate.
- API keys must come from environment variables or a future secret manager.
- Example values in `.env.example` are placeholders and must not be used as real
  credentials.
