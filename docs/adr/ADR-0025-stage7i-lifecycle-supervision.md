# ADR-0025: Stage7I Lifecycle Supervision

Status: Accepted for Package B B1/B2 implementation.

## Context

The previous Stage7I observer and lifecycle collector were independent
processes. The collector could stop emitting evidence while the observer still
finished a 24 hour window, leaving the run classified as
`BLOCKED_NON_QUALIFYING_LIFECYCLE_GAP`.

Package A removed the future-refresh dependency on shared runtime writability by
moving state to PostgreSQL. Stage7I lifecycle state should follow the same
persistence boundary and avoid treating runtime JSON as the authority source.

## Decision

Stage7I B1/B2 uses a single DB-backed supervisor/state machine in
`w2.monitoring.stage7i_supervision`.

The supervisor owns:

- run state: `IN_PROGRESS`, `FAILED`, `NON_QUALIFYING`, `COMPLETED`;
- observer and collector heartbeats;
- watchdog failure classification;
- lifecycle evidence events;
- final audit status.

The state machine persists to PostgreSQL through SQLAlchemy tables introduced in
Alembic revision `0019_create_stage7i_lifecycle_supervision`. Tests may use an
ephemeral SQLite database through the same repository API. Runtime files remain
supported for legacy tooling, but B1/B2 acceptance uses DB state as authority.

## Invariants

- If the collector heartbeat is missing, stale, or inactive, the run cannot
  become `COMPLETED`.
- Collector exit or heartbeat timeout is written as a watchdog audit event and
  marks the run `FAILED`.
- `check_w2_stage7i.py --mode final --db-run-id <run>` returns success only
  when actual kickoff, closing observation, result, settlement/evaluation, and
  final DB audit are complete.
- Scheduled kickoff is never accepted as actual kickoff.
- Result, settlement, evaluation, and final audit evidence are retrospective and
  must not be reclassified as forward evidence.
- Public flags remain `candidate=false` and `formal_recommendation=false`.

## Consequences

B1/B2 can be validated without deploying, starting a new 24 hour run, or calling
real providers. B3 remains a separate approval checkpoint for a new forward run,
provider budget, and deployment window.
