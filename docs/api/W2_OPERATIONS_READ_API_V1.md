# W2 Operations Read API V1

The operations API is available under `/ops` for local/staging only. Production requests are
rejected.

Endpoints:

- `GET /ops/health`
- `GET /ops/quota`
- `GET /ops/tasks`
- `GET /ops/alerts`
- `GET /ops/mapping-conflicts`
- `GET /ops/forward-cycles`
- `GET /ops/locks`
- `GET /ops/settlements`
- `GET /ops/gates`

Rules:

- all endpoints are read-only
- no rerun, override, edit, delete, approve, or publish route exists
- responses must not include provider keys, auth headers, environment variables, or stack traces
- operational metrics remain internal structured data
