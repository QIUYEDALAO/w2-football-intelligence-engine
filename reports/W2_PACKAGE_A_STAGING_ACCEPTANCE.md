# W2 Package A Staging Acceptance

## Summary

Package A is accepted on staging at revision
`3e79fdfa34cdf13e3c1e71159625aaa2535a7b9f` with Alembic head
`0018_create_future_refresh_persistence`.

This closure performed read-only reconciliation only. It did not deploy,
restart services, run migrations, trigger scheduler work, call providers, read
`.env` contents, modify W1, or change production.

## Classification

`EXPECTED_FORWARD_ACCUMULATION`

Future-refresh is a continuous forward collection system. Live database counts
are dynamic and expected to grow monotonically after initial acceptance. The
initial acceptance counts are retained as minimum baselines, not equality
contracts.

## Baseline Minimums

| Table | Minimum |
| --- | ---: |
| `future_market_observation` | 65285 |
| `future_refresh_task_audit` | 1 |
| `future_refresh_run_audit` | 1 |
| `raw_payload` | 11 |

## Observed Read-Only Snapshot

Observed at `2026-06-25T02:39:16Z` in one read-only repeatable-read
transaction.

| Metric | Value |
| --- | ---: |
| `future_market_observation` | 71799 |
| `future_refresh_task_audit` | 5 |
| `future_refresh_run_audit` | 5 |
| `raw_payload` | 16 |
| distinct `observation_id` | 71799 |
| duplicate `observation_id` | 0 |
| completed tasks | 5 |
| completed runs | 5 |
| candidate true count | 0 |
| formal recommendation true count | 0 |

Observation window:

- min `captured_at`: `2026-06-25T01:32:03.651795+00:00`
- max `captured_at`: `2026-06-25T01:47:08.301919+00:00`

Latest task:

- status: `COMPLETED`
- request count: `12`
- candidate: `false`
- formal recommendation: `false`

## System Readiness

- systemd: enabled and active
- containers: 6 healthy
- API `/health`: `200`
- API `/ready`: `200`
- Web: `200`
- read endpoints: all 7 expected endpoints returned `200`
- business ports: bound to localhost only
- `.env`: stat-only check, mode `600`, owner `ubuntu`
- worker uid: `10001`
- runtime writable by worker: `false`
- runtime writability required: `false`

## Outcome

`SHARED_RUNTIME_NOT_WRITABLE_FOR_NON_ROOT_WORKER` is resolved by PostgreSQL
persistence for future-refresh. Package A A1 through A5 are complete on
staging. A6 remains pending as `A6_OBJECT_STORAGE`.
