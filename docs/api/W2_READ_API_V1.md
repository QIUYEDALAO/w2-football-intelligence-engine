# W2 Read API V1

The public read API is available under `/v1`. It is read-only and exposes fixture, market, model,
health, provider, backtest, and forward holdout state.

Endpoints:

- `GET /v1/fixtures`
- `GET /v1/fixtures/{fixture_id}`
- `GET /v1/fixtures/{fixture_id}/odds-timeline`
- `GET /v1/fixtures/{fixture_id}/market-probabilities`
- `GET /v1/fixtures/{fixture_id}/model-probabilities`
- `GET /v1/data-health`
- `GET /v1/providers/status`
- `GET /v1/backtests/latest`
- `GET /v1/forward-holdout/status`

Rules:

- all business timestamps are stored and returned with UTC source fields
- `timezone` only controls display timestamps
- market fair probabilities are separate from independent model probabilities
- WATCH/SKIP are lifecycle states, not recommendations
- `first_seen` must not be labelled opening
- no candidate, recommendation, or DeepSeek route exists
