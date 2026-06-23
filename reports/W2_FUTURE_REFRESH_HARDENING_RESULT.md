# W2 Future Fixture Refresh Hardening Result

## Summary

- Scope: future-data-refresh operational hardening and append-only market ledger
- Active observer: Stage7I successor run remains in progress
- Staging deployment: `PENDING_STAGE7I_COMPLETION`
- Gate5: `OPEN`
- Candidate output: `false`
- Formal recommendation output: `false`

This package hardens the future fixture refresh path without deploying it to
staging. The active Stage7I observer revision remains unchanged.

## Runtime Entry Points

- Scheduler: `apps/scheduler/main.py`
- Worker: `apps/worker/celery_app.py`
- Service: `src/w2/ingestion/future_refresh.py`
- Policy: `config/policies/future_fixture_refresh.v1.json`

The scheduler now dispatches Celery task `w2.future_fixture_refresh` only. It
does not call the provider client or refresh service directly.

## Hardening

- Deterministic task key:
  `future-refresh:<competition_id>:<season>:<time-bucket>`
- Redis-preferred singleton lock with owner-marker file fallback
- Duplicate active task result: `ALREADY_RUNNING`
- Task audit records task ID, key, owner, queued/started/finished time, status,
  and sanitized result summary
- Competition, season, horizon, budget, quota reserve, and freshness are loaded
  from policy
- Unregistered competitions are blocked
- Every provider attempt counts against request budget
- 401/403 stop without retry
- 429 retries are counted and backoff-controlled
- Each persisted raw payload records its own request audit reference
- Request audit remains sanitized

## Append-Only Market Ledger

Market observations are appended to:

`runtime/future_refresh/ledger/market_observations.jsonl`

The ledger uses a stable observation identity so replaying the same raw payload
does not duplicate rows, while genuinely new payloads append new observations.
Read models and odds timeline responses are projected from the ledger.

## Read Model

- Past fixtures still marked `NS` are hidden from the default fixture list
- `stale_data_count` is computed from stale `NS` fixtures
- Provider status includes last successful refresh, age, blockers, and quota
- Odds timeline can return future-refresh market observations without requiring
  `power_probabilities`
- Timeline points remain `snapshot_semantics=CAPTURED_AT` and `closing=false`

## Deployment

No staging deployment, service restart, migration, or `/opt/w2/current` switch
was performed. Deployment remains pending to preserve active Stage7I revision
continuity.
