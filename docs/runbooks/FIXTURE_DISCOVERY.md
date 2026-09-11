# Fixture discovery operations

Fixture discovery is a mode of the canonical `w2.future_fixture_refresh` task.
It has no separate worker, Provider client, quota ledger, or evidence writer.

## Contract

- The scheduler rotates across the eight UTC dates needed to cover the next
  seven Asia/Shanghai football days.
- Each UTC date uses `fixtures?date=YYYY-MM-DD` at most once per operational
  day and only persists exact-13 fixture identities.
- Discovery never requests odds or lineups, creates recommendations, or
  materializes public analysis. Existing checkpoint planning creates and
  executes T168/T72/T48/T24/T12/T6/T3/T60/T45/T30 captures.
- The same Provider hard cap, request ledger, raw payload, endpoint capture,
  repository, and Celery task used by checkpoint collection remain authoritative.

Enable only on the scheduler:

```text
W2_FIXTURE_DISCOVERY_ENABLED=true
W2_FIXTURE_DISCOVERY_INTERVAL_SECONDS=300
```

Rollback sets `W2_FIXTURE_DISCOVERY_ENABLED=false`; valid persisted evidence is
retained. Dashboard/API reads remain Provider-free.
