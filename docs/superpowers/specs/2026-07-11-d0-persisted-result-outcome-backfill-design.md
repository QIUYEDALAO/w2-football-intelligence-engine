# D0 Persisted Result Source and Outcome Backfill

## Problem

The staging forward ledger is growing, but every row is a capture and no outcome rows exist. The backfill task requests the Dashboard `all` window, which is scoped to the current operational date. Finished fixtures disappear from that surface before the ledger can settle them.

## Design

Use the existing `forward_result_event` table as the sanitized, persistent result source.

1. Normalize FT/AET/PEN fixtures from persisted API-Football fixture responses into result events containing only fixture identity, status, 90-minute fulltime score, confirmation time, provider, and evidence hash.
2. Persist those events idempotently whenever the future-refresh fixture response contains finished fixtures.
3. Read result events by the fixture IDs present in `runtime/forward_outcome_ledger`.
4. During migration, derive equivalent sanitized events read-only from already persisted fixture raw payloads when the result-event table has no row. This allows existing staging evidence to settle without another provider request.
5. Feed the persisted result source directly to `backfill_outcomes`; do not use DayView or the future window as the result source.

## Safety

- No provider call is added by the backfill task.
- Result persistence is part of the already approved fixture refresh transaction surface.
- Outcome rows remain append-only JSONL evidence and are idempotent.
- AET/PEN settle on `score.fulltime`; missing 90-minute scores remain unsettled.
- No recommendation, lock, EV, direction, or production behavior changes.

## Acceptance

- A finished fixture that has left DayView can still create an outcome row.
- Re-running result persistence and outcome backfill writes zero duplicates.
- FT/AET/PEN use the 90-minute score.
- Missing fulltime score is counted and not settled.
- Mixed legacy capture and outcome rows remain readable.
- Provider calls remain zero in tests and dry-run acceptance.
