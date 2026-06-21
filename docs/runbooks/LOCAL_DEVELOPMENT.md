# Local Development

## Requirements

- Python 3.12 through `uv`
- Docker with Compose for containerized local infrastructure
- Node is only needed when working directly on `apps/web`

## Setup

```bash
make setup
```

## Checks

```bash
python3 scripts/check_w2_stage1_contracts.py
make lint
make typecheck
make test
make smoke
```

## Local Services

```bash
make up
make down
```

The API exposes `/health` and `/ready`. Both report service name, version,
environment, database status, and Redis status. They never print passwords or
environment variables.

Stage 2 does not call Football-API, DeepSeek, odds providers, or any paid
service.

