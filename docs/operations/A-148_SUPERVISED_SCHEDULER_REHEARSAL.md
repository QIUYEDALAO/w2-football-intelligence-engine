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

- Remaining daily provider quota is at least 50%.
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
