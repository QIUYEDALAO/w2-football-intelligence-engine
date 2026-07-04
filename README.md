# W2 Football Intelligence Engine

Current status: W2 is entering the Decision Contract V2 migration phase. The
system is freezing new stage expansion: no Stage 16 will be added, and the
existing stage checker scripts are regression safety nets rather than the
product operating surface.

The product runtime entrypoint will converge on `w2-matchday`. Recommendation
governance follows staging A / production B: staging may display and track
`ANALYSIS_PICK` cards to exercise dashboard, lock, settlement, and replay
plumbing after completeness gates pass; production actionability is stricter.
`ANALYSIS_PICK` is an analysis recommendation only, not a production actionable
recommendation. Production lockable recommendations come only from `RECOMMEND`.

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
