# Stage 10A Local Operations

Stage 10A exposes read-only APIs and a local/staging operations console.

## API

Run the API as usual, then inspect:

```bash
uv run uvicorn apps.api.main:app --reload
```

The operations API is available only outside production. Recommendation, candidate, DeepSeek,
mutation, and approval routes do not exist.

## Web

```bash
npm --prefix apps/web ci
npm --prefix apps/web run typecheck
npm --prefix apps/web run build
```

The console shows research and forward validation state only. It must display the notice:

`正式推荐尚未启用，当前仅为研究与前瞻验证。`

## Safety

- no Football-API calls are made by Stage 10A
- no autorun configuration is changed
- runtime cache files remain gitignored
- production operations API is disabled
