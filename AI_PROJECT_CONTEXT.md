# W2 AI Project Context

> **Purpose:** This is the first handoff document for any AI or human taking over W2.
> It is an AI-maintained summary, not a substitute for code inspection.
> For current machine status read [`PROJECT_STATE.yaml`](PROJECT_STATE.yaml);
> for task order and historical completion receipts read the
> [master checklist](docs/operations/architecture_convergence/W2_ARCHITECTURE_CONVERGENCE_MASTER_CHECKLIST.md);
> for the independent code audit read
> [`W2_INDEPENDENT_FINAL_AUDIT_20260731.md`](docs/operations/W2_INDEPENDENT_FINAL_AUDIT_20260731.md).

## Audit baseline

- Code baseline independently reviewed: `main@dbc8e1e8aa74a7613fd7121bf6026890c3ee06c6`.
- PR #449 is included in that baseline.
- The audit accepts code, database constraints, deployment configuration, and reproducible GitHub facts.
- PR descriptions and state-document self-claims are not treated as proof.
- This context update changes documentation, state summarization, and contract tests only; it does not authorize runtime changes or Provider calls.

## AI summary

### Completed

- P0/P1/P2 architecture convergence is complete.
- Phase A tasks are merged; `ARCH-GOVERNANCE-01` is historically complete but its post-merge consistency gate was later retired.
- EVAL-01A, EVAL-01B, EVAL-01C, and EVAL-02A are complete within their frozen implementation scopes.
- OPS-01 Runbook is complete as documentation; runtime enablement is not complete.
- EVAL-02B preregistration, Legacy 35 exclusion decision, and write-side Implementations 01–04 are complete.
- The EVAL-02B exact-pair core contract is implemented: `capture_at` boundary, same provider/bookmaker/market/selection/exact line, legal five-state distribution, ambiguity fail-closed.
- The split-line parser behavior such as `2/2.5 -> 2.25` is intentional and tested; it is **not** an accepted defect.
- `readiness.py` is a status calculator, not a Provider live-call entrypoint.

### Current state

- EVAL-02B end-to-end is **BLOCKED / NOT VALIDATED**.
- EVAL-03 is **NOT STARTED**.
- A148 proved only that a contradictory deployment precondition stopped execution before Provider calls.
- A148 result: `SAFE_FAIL_CLOSED_ONLY`; it did not validate Provider, raw payload, endpoint capture, lineup event, dynamic evaluation, five-state snapshot, or exact-pair production.
- Provider, real canary, persistent scheduler, Candidate, Formal, Lock, and Production are all unauthorized.

### Core engineering rules

1. **Default deny on missing or unknown.** Missing, malformed, stale, or unverifiable safety inputs mean `BLOCKED`, never “false means allowed”.
2. **Explicit failure after external side effect.** Once a Provider request may have reached the external service or incurred cost, every downstream failure must be persisted, surfaced, and stop further calls.
3. **Idempotency must be proven.** A conflict is a no-op only after the expected constraint and the existing row's business fields are verified.
4. **No silent success.** Empty required evidence, swallowed exceptions, missing locks, stale quota evidence, and `ALREADY_RUNNING` are not successful collection.
5. **Canary is an evidence-chain test, not a process-liveness test.**

### Real canary hard contract

A real canary may be recorded as `PASS` only when all required deltas are positive and belong to one reconciled lineage:

```text
actual_provider_calls_delta      > 0
provider_request_ledger_delta    > 0
raw_payload_delta                > 0
endpoint_capture_delta           > 0
lineup_event_delta               > 0
dynamic_evaluation_v2_delta      > 0
five_state_snapshot_delta        > 0
exact_pair_delta                 > 0
```

The lineage must reconcile at least:

```text
run_id
authorization_id
competition_id
season
fixture_id
provider
bookmaker
market
selection
exact_line
capture_at
raw_payload_sha256
endpoint_capture_id
lineup_input_hash
evaluation_id
pair_hash
exact_git_sha
```

Any required zero delta is failure. If any required delta is zero, or any lineage link is missing/conflicting:

```text
CANARY = FAILED
EVAL-02B = BLOCKED
AUTO_RETRY = FORBIDDEN
```

A precondition that cannot produce the required chain must stop before the Provider call with `PROVIDER_CALLS=0`; it must not spend quota and later explain a zero delta as “no data this time”.

## Critical remediation backlog

- **C1:** Provider kill switch and endpoint allowlist default fail-open.
- **C2:** Manual and other live paths lack one centralized runtime authorization contract.
- **C3:** CLI `--season` affects task identity but not the policy season used for collection.
- **C4:** `--execute` defaults to DB persistence.
- **C5:** DB-mode run locking is optional when Redis is absent.
- **C6:** Provider call, request ledger, and quota ledger are not one reconciled side-effect state machine.
- **C7:** Uncertain-delivery timeouts can be retried when attempts are raised above the default.
- **C8:** Provider schema drift or unexpected empty data can look like normal completion.
- **C9:** Lineup materialization failures and some integrity conflicts are swallowed or downgraded.
- **C10:** Staging scheduler declares `restart: unless-stopped` while the frozen rehearsal requires `restart: no`.
- **C11:** Request-ledger `IntegrityError` is silently swallowed; remaining-without-limit silently skips quota usage updates.

See the independent audit for trigger, consequence, reproduction, fix, and risk treatment for each item.

## Important work before continuous operation

- Atomic task and quota reservation across concurrent runs.
- Fencing/lease renewal and first-write concurrency protection for lineup/evaluation/supersession.
- Provider collection readiness separated from service liveness; real scheduler/worker progress checks.
- Migration success must fence worker and scheduler startup.
- Explicit Celery acknowledgement/retry contract.
- PostgreSQL/Redis/worker failure-injection suite.
- Cold-pull SLO, backup/restore, clock drift, resource exhaustion, supply-chain, permission, and secret/log review.

## Accepted or bounded issues

- Legacy 35 results remain immutable historical facts and are permanently excluded from EVAL-02B unless the exact original raw blob is recovered and its SHA-256 matches.
- The 22-package SCC and `schemas` investigation are bounded technical debt, not grounds to invent deletes.
- OPS-01's missing generic readiness producer may remain until a new competition enablement, but that enablement cannot claim readiness without it.
- Split-line averaging for valid Asian split lines is intentional; do not modify it without a real Provider payload proving an invalid input domain.

## Next action

Implement and independently review the EVAL-02B runtime-safety and concurrency remediation under the three engineering rules above.

Until that work is merged and verified:

```text
PROVIDER = OFF
REAL_CANARY = NOT_AUTHORIZED
PERSISTENT_SCHEDULER = OFF
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
```

## Handoff checklist for the next AI

1. Read this file, `PROJECT_STATE.yaml`, the final audit, and the EVAL-02B section of the master checklist.
2. Verify the current main SHA before making conclusions.
3. Inspect code and constraints; do not repeat a PR description as evidence.
4. Make no network Provider call and no business DB write unless an explicit scoped authorization is supplied.
5. Keep runtime fixes in narrow PRs, but validate the whole “missing denies / side-effect failure surfaces / idempotency proven” matrix.
6. Do not mark a canary complete unless every required positive delta and the full lineage are verified.
