# A-148 Supervised Scheduler Rehearsal

## Scope

A-148 restores automatic matchday refresh under supervision. The rehearsal is
not complete unless the full runtime chain works:

1. checkpoint selection
2. controlled provider refresh
3. raw/audit persistence
4. read-model materialization
5. static report/dashboard regeneration

Validating provider calls alone is insufficient.

## Preconditions

- W2 daily provider budget is 100 calls/day.
- Matchday checkpoint refresh should consume at most 80 calls/day.
- Trickle backfill is capped at 5 calls/day and may only use leftover budget
  after matchday projection plus reserve.
- Daily reserve is 20 calls.
- Provider account quota headers are recorded separately from the W2 daily
  operating budget. The rehearsal hard cap uses W2 provider-request ledger
  usage; provider account exhaustion still fails closed when observed.
- Remaining daily provider quota is sufficient for the W2 100-call rehearsal
  budget.
- No live prematch window is being displaced by the rehearsal.
- Scheduler starts in the foreground with `restart=no`.
- Production deploy, lock capture write, and settlement write are not part of
  this rehearsal.
- Provider endpoints remain limited to `status`, `fixtures`, `odds`, and
  `lineups`.
- Per-tick hard cap, endpoint allowlist, ledger accounting, quota hard-stop, and
  task-key dedupe remain enabled.

Record the quota value and container restart policy before starting.

## Required Observations

For one complete checkpoint cycle, record:

- projected provider calls by checkpoint type
- actual provider calls by checkpoint type
- request count by endpoint
- memory peak for scheduler, worker, API, and web containers
- provider request ledger delta
- quota usage delta
- checkpoint audit row count and completeness
- hard-stop or reserve blocker count
- duplicate task suppression count
- W2 daily budget used before/after
- provider account quota header observed before/after, if available

## Materialization Gate

The rehearsal must prove that automatic refresh includes read-model
materialization and page regeneration.

For every executed checkpoint with refreshed odds or lineups:

- raw payload/audit rows must be present
- read-model market or lineup state must advance when the raw payload contains
  newer usable data
- the authoritative dashboard payload must reflect the read-model change
- the generated static HTML page must show the same data time as the dashboard
  payload
- the public page watermark must remain the deployed renderer version

If raw provider data advances but the read-model or public page data time does
not roll forward, the rehearsal fails even when provider calls are within
budget.

## Acceptance Criteria

The rehearsal passes only if all criteria hold:

- actual provider calls are within plus or minus 20% of projection
- zero hard-stop or reserve violations
- every executed checkpoint has an audit row
- raw payload persistence and provider ledger deltas match actual calls
- read-model materialization advances for usable refreshed data
- public page data time advances after materialization
- health, ready, version, and page watermark checks pass after the cycle

After a pass, observe for 24 hours before changing scheduler restart policy to
`always`.

## Failure Handling

If any acceptance criterion fails:

- stop the scheduler
- keep restart policy as `no`
- return to manual controlled refresh mode
- create an incident note with the failed checkpoint, projected calls, actual
  calls, materialization status, and page data-time status

Do not retry by widening provider endpoints, disabling hard caps, or enabling
legacy frequency-based refresh.

## 2026-07-04 Rehearsal Attempt

Status: FAILED_CLOSED

The supervised rehearsal was started as a one-off foreground checkpoint task on
the single production/staging host. The persistent scheduler container was not
started and its restart policy stayed `no`.

Runtime identity:

- Host: 43.155.208.138
- Web/API SHA: f15f28c3c4af138339881864b03c1085fc9d60a0
- Local branch at launch: feat/w2-canonical-ah-materialization
- Launch time: 2026-07-04T11:05:41Z

Preflight:

- Scheduler state: exited
- Scheduler restart policy: no
- Celery queue length: 0
- Endpoint allowlist: status, fixtures, odds, lineups
- XG/history/H2H/statistics/injuries: not enabled
- Selected checkpoint count: 25
- Projected provider calls: 26
- Tick hard cap: 30

Checkpoint projection:

- OPEN: 6
- RESULT_POLL: 2
- T12: 4
- T15M_CLOSE: 2
- T1_LINEUPS: 2
- T24: 4
- T3: 2
- T6: 3

Actual result:

- Provider calls actual: 2
- Request count by endpoint: fixtures=1, status=1
- Provider request log delta: 2
- Raw payload delta: 2
- Future refresh run audit delta: 1
- Future refresh checkpoint audit delta: 25
- Task status: BLOCKED
- Blocker: DAILY_QUOTA_UNKNOWN
- Quota usage observed after status request was later classified as a
  header-basis accounting artifact: the old ledger inferred `used=7400` from a
  7500-call assumed limit when the provider only exposed the 100-call remaining
  header.
- Materialization: not run after blocker
- Public page data-time roll: not attempted after blocker

Memory observation:

- API: 168.8MiB before, 172.5MiB after, limit 1GiB
- Worker: 150.0MiB before, 150.1MiB after, limit 2GiB
- Web: 4.734MiB before and after, limit 256MiB
- Scheduler: 0B, container remained exited

Decision:

The rehearsal correctly failed closed before odds/lineups refresh, but the
reason was a mixed-basis quota instrument rather than confirmed quota leakage.
Manual mode remains active. Scheduler remains stopped with restart policy `no`.
The next attempt must use the corrected header-basis preflight: provider header
remaining must be at least 50, and quota usage must not be inferred unless the
provider also returns the matching limit.

## 2026-07-05 Rehearsal Budget Contract

The next rehearsal uses the 100-call W2 operating budget and the provider
header-basis remaining check rather than the prior large-account quota
assumption.

World Cup checkpoint mode:

- OPEN: odds only
- T1_LINEUPS: odds plus lineups
- T15M_CLOSE: odds only

Event-driven exceptions remain allowed but budgeted:

- T45/T30 lineups retry only after `PROVIDER_EMPTY` / `MISSING_LINEUPS`
- LINE_JUMP_CONFIRMATION only after a line move of at least 0.5 goals

Backfill plan:

- Backfill is trickle-only during matchday operations.
- Daily trickle cap: 5 calls.
- Backfill is skipped when matchday projected calls plus reserve leave no room.
- Statistics, injuries, H2H, history, and XG remain outside the supervised
  matchday scheduler.

Pass criteria for the 100-call rehearsal:

- selected checkpoint projection is at or below 30 calls for the tick
- daily W2 projected calls stay at or below 100
- actual calls are within plus or minus 20% of projection
- raw/audit rows are written for executed requests
- materialization runs after collection
- public page data time rolls after materialization
- scheduler remains `restart=no` during observation
