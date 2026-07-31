# W2 Current Main Independent Final Audit

**Audit baseline:** `main@dbc8e1e8aa74a7613fd7121bf6026890c3ee06c6`  
**Audit date:** 2026-07-31  
**Repository:** `QIUYEDALAO/w2-football-intelligence-engine`  
**Decision:** `EVAL-02B = BLOCKED`; no Provider, real canary, persistent scheduler, Candidate, Formal, Lock, or Production authorization.

## 1. Method and evidence policy

This review treats the following as evidence:

- source code at the exact baseline commit;
- database constraints and migrations;
- effective deployment configuration;
- reproducible GitHub merge facts;
- tests only as supporting evidence, not as proof of runtime correctness.

The review does **not** accept a PR description, `PROJECT_STATE.yaml`, `NEXT_ACTION.md`, a Runbook, or a passing test suite as proof merely because it says a task passed.

Coverage limitations remain for backup/restore, clock drift, resource exhaustion, supply-chain dependencies, secret/log exposure, and operating-system/database least privilege. Those areas are not “passed”; they remain unproven.

## 2. Executive decision

### 2.1 What is genuinely complete

- P0/P1/P2 architecture convergence is complete.
- Phase A merged implementation tasks are complete within their frozen scopes.
- EVAL-01A/B/C and EVAL-02A are complete within their frozen scopes.
- OPS-01 is complete as a Runbook artifact, not as proof of runtime enablement.
- EVAL-02B preregistration, the Legacy 35 exclusion decision, and write-side Implementations 01–04 are complete.
- The exact-pair core contract is substantially implemented: `capture_at` is the Pre/Post eligibility boundary; Provider, bookmaker, market, selection, and exact line must match; five-state distributions are validated; ambiguity fails closed.

### 2.2 What is not complete

- EVAL-02B end-to-end evidence collection has never been validated with a real Provider run.
- A148 stopped before Provider execution because the effective scheduler restart policy contradicted the frozen rehearsal precondition.
- Actual Provider calls, request ledger, raw payload, endpoint capture, lineup event, dynamic evaluation v2, five-state snapshot, and exact pair deltas were all zero.
- EVAL-03 has not started.
- Continuous scheduler operation, quota accounting under concurrency, recovery, and operational health have not been proven.

### 2.3 A148 classification

A148 is correctly classified as:

```text
FAIL_CLOSED_BARRIER = PASS
PROVIDER_EXECUTION = NOT_EXECUTED
END_TO_END_CHAIN = NOT_VALIDATED
RUNTIME_COLLECTION_READINESS = NOT_PROVEN
EVAL_02B = BLOCKED
```

It must never be described as “the real chain passed”.

## 3. Root-cause pattern and engineering invariants

The findings repeatedly follow two unsafe patterns:

```text
missing input -> allow
exception -> silence or downgrade
```

Examples include a missing Provider kill switch allowing calls, a missing allowlist opening endpoints, missing Redis permitting an unlocked DB run, `IntegrityError` being swallowed, lineup persistence failure being passed over, and incomplete quota evidence silently stopping quota updates.

The remediation must enforce three repository-wide invariants:

1. **Default deny on missing or unknown.** Any missing, malformed, stale, or unverifiable safety input yields `BLOCKED`.
2. **Explicit failure after an external side effect.** Once a Provider request may have reached the external service, every downstream failure is persisted, surfaced, and stops further Provider calls.
3. **Idempotency must be proven.** A conflict is a no-op only after the expected constraint and the stored business fields are verified.

## 4. Critical findings

### C1. Provider kill switch and endpoint allowlist default fail-open

**Code:** `src/w2/providers/control.py:47-61`  
**Trigger:** `W2_PROVIDER_CALLS_DISABLED` is missing or malformed; API key is present; a caller uses `allow_live=True`.  
**Consequence:** the kill switch is interpreted as disabled, while a missing endpoint allowlist opens `status`, `fixtures`, `odds`, and `lineups`.  
**Reproduction:** unset the kill-switch and allowlist variables, provide a valid key, then invoke a live path.  
**Must fix:**

- missing, empty, or invalid kill-switch values must disable Provider calls;
- missing allowlist must be empty;
- a scoped runtime authorization must explicitly open each endpoint;
- contract tests must cover missing and invalid values.

**Acceptable risk:** none.

### C2. Manual and other live paths lack one runtime authorization contract

**Code:** `scripts/run_prematch_refresh.py:124-152`; Provider transport in `src/w2/providers/api_football.py`.  
**Trigger:** a user or process has shell execution, environment access, a Provider key, and DB configuration.  
**Consequence:** `--execute` can call `run_future_refresh_task()` without proving current authorization, exact Git SHA, competition/season scope, endpoint scope, persistence target, call cap, or expiry. `PROJECT_STATE.yaml` is documentation, not a runtime enforcement plane.  
**Reproduction:** invoke `python scripts/run_prematch_refresh.py --execute` in an environment where the transport gates happen to permit calls.  
**Must fix:** implement one authorization check at or below the shared Provider transport. The authorization must bind exact Git SHA, environment, competition, policy season, endpoints, persistence, maximum calls, expiry, purpose, and run ID.  
**Acceptable risk:** none.

### C3. CLI `--season` changes task identity but not collection policy

**Code:** `scripts/run_prematch_refresh.py:33, 49-63, 114-152`; `src/w2/ingestion/future_refresh.py` policy loading.  
**Trigger:** operator supplies a season different from the registry policy.  
**Consequence:** the task key and audit identity can claim one season while Provider parameters and DB writes use another. Changing only the CLI season can also create a new dedupe key for the same real season.  
**Reproduction:** run with `--season 2099` against a competition whose policy season is 2026.  
**Must fix:** remove the argument or treat it solely as an assertion against `policy.season`; mismatch must produce zero Provider calls and zero writes.  
**Acceptable risk:** none.

### C4. `--execute` defaults to DB persistence

**Code:** `scripts/run_prematch_refresh.py:129-131`; `src/w2/ingestion/future_refresh.py:2005-2010`.  
**Trigger:** operator uses `--execute` without `--persistence`.  
**Consequence:** a manual command can write raw payloads, captures, observations, projections, and task audit to the configured business DB without an explicit persistence decision.  
**Reproduction:** execute the CLI with no persistence argument and no overriding environment variable.  
**Must fix:** default to plan/no persistence or isolated file evidence. DB persistence must require an explicit flag, runtime authorization, and target-database identity verification.  
**Acceptable risk:** none.

### C5. DB-mode run locking is optional when Redis is absent

**Code:** `src/w2/ingestion/future_refresh.py:2000-2041`.  
**Trigger:** DB persistence is configured, Redis is not configured, and two same-key manual/worker runs overlap.  
**Consequence:** both runs can pass the `task_key_exists()` precheck before the end-of-run audit exists; the code then sets `lock_acquired=True` without a lock. Both runs may call the Provider and write concurrently.  
**Reproduction:** unset Redis configuration and start two same-bucket `--execute` processes concurrently.  
**Must fix:** absence of a lock backend must deny execution. Prefer an atomic DB reservation (`INSERT ... ON CONFLICT DO NOTHING`) or advisory lock with owner/fencing identity.  
**Acceptable risk:** none.

### C6. Provider call, request ledger, and quota ledger are not a reconciled side-effect state machine

**Code:** `src/w2/providers/api_football.py`; `src/w2/providers/ledger.py:55-123`.  
**Trigger:** Provider has received or completed a request, then local request-log or quota persistence fails.  
**Consequence:** external cost may exist without a complete local ledger; local call counts and hard-cap decisions may be understated. Request log and quota usage are separate transactions.  
**Reproduction:** inject a DB failure after a successful HTTP response but before request or quota ledger completion.  
**Important correction:** `provider_http_max_attempts()` defaults to 1, so automatic duplicate charging is not the default behavior. The duplicate-call amplification appears when `W2_PROVIDER_HTTP_MAX_ATTEMPTS >= 2`. The structural accounting defect exists regardless.  
**Must fix:** create a stable logical request ID and a state machine such as `INTENT -> SENT/UNCERTAIN -> RESPONSE_RECEIVED -> LEDGER_COMPLETE`. A ledger failure after a response must not cause another HTTP request.  
**Acceptable risk:** none for a real canary.

### C7. Uncertain-delivery timeouts are not idempotent when retries are enabled

**Code:** `src/w2/providers/api_football.py` (`urlopen(..., timeout=20)`); `src/w2/ingestion/future_refresh.py` request loop.  
**Trigger:** request reaches Provider and may be charged, but the client gets a read timeout; max attempts is configured above 1.  
**Consequence:** W2 can buy the same logical request again.  
**Reproduction:** inject a timeout after server-side request acceptance with attempts set to 2 or 3.  
**Must fix:** distinguish connection-establishment failure from uncertain delivery. Uncertain delivery must end the run without automatic Provider retry.  
**Acceptable risk:** default attempts=1 reduces exposure but is not a correctness proof.

### C8. Provider schema drift and unexpected empty evidence can look like normal completion

**Code:** `src/w2/ingestion/future_refresh.py`, especially `_future_fixtures`, market/enrichment filtering, and `_diagnostic_code_for_response()` at approximately lines 1208-1221. Tests currently accept empty lineup data with no blocker.  
**Trigger:** Provider schema changes, permissions change, competition/season is wrong, bookmaker data disappears, or required lineup data is unexpectedly empty.  
**Consequence:** zero fixtures, markets, lineup events, or pairs can be recorded as a non-blocked run or only a diagnostic.  
**Reproduction:** return an unexpected response shape or `{response: []}` for required evidence.  
**Must fix:** endpoint-specific schema contracts, an explicit legal-empty policy, and minimum evidence assertions for the canary.  
**Acceptable risk:** a legally empty lineup window may be allowed only when the checkpoint policy explicitly predicts it; it cannot count as a canary pass.

### C9. Lineup materialization failures and some integrity conflicts are swallowed

**Code:** `src/w2/ingestion/future_refresh.py:1105-1158`; `src/w2/ingestion/future_refresh_repository.py` lineup persistence.  
**Trigger:** incomplete XI, duplicate player, two-team incompleteness, identity conflict, DB constraint failure, or other lineup persistence error.  
**Consequence:** raw payload may be preserved while lineup snapshot/event/evaluation/pair production fails; the caller catches `FutureRefreshPersistenceError` and executes `pass`. Repository `IntegrityError` may return zero without proving idempotency.  
**Reproduction:** inject a lineup persistence error after raw payload save.  
**Must fix:** preserve raw evidence but set explicit stage failure and overall `BLOCKED/PARTIAL_FAILED`. Verify the expected constraint and stored business fields before treating an integrity conflict as a no-op.  
**Acceptable risk:** preserving raw evidence is correct; hiding the downstream failure is not.

### C10. The frozen rehearsal restart policy still contradicts staging Compose

**Code:** `infra/compose/compose.staging.yml:229` (scheduler service).  
**Trigger:** rerun A148 against the current effective Compose.  
**Consequence:** the same precondition failure repeats before Provider execution.  
**Reproduction:** inspect effective Compose and compare `restart: unless-stopped` with the frozen `restart: no` requirement.  
**Must fix:** create an explicit rehearsal deployment profile or override whose effective configuration is verified as `restart: no`.  
**Acceptable risk:** none for the canary.

### C11. Ledger integrity and incomplete quota evidence can fail silently

#### C11-A. Request-ledger `IntegrityError` is swallowed

**Code:** `src/w2/providers/ledger.py:72-94`; unique constraint in `src/w2/infrastructure/persistence/ingestion_models.py`.  
**Trigger:** request-log commit raises any `IntegrityError` after an external Provider request.  
**Consequence:** the code rolls back and continues without identifying the constraint, reading the existing row, comparing business fields, emitting a metric, or surfacing failure. A real request may have no ledger record.  
**Reproduction:** inject a non-idempotent request-log integrity failure.  
**Must fix:** only the expected uniqueness conflict may enter a duplicate path; read back and compare all business fields. Every other integrity failure must raise a dedicated ledger exception and stop further calls.

#### C11-B. Remaining-without-limit silently stops quota usage updates

**Code:** `src/w2/providers/ledger.py:95-123`; quota parsing in `src/w2/providers/quota.py`.  
**Trigger:** response provides `daily_remaining` but no `daily_limit`.  
**Consequence:** the current request can continue, while `QuotaUsageModel` is not updated and no warning/metric/status is emitted. Request ledger and quota ledger diverge.  
**Reproduction:** return a valid remaining header without any limit header or payload limit.  
**Must fix:** return/persist structured ledger status with missing quota fields, emit `PROVIDER_QUOTA_EVIDENCE_INCOMPLETE`, and block subsequent calls when quota evidence is a safety boundary.  
**Correction:** if `daily_remaining` itself is missing, future refresh explicitly blocks with `DAILY_QUOTA_UNKNOWN`; that case is not silent.

**Acceptable risk:** only a versioned Provider contract may supply a configured limit, and its source must be recorded.

## 5. Important findings

### I1. Current state documents were stale after PR #449

**Files:** `PROJECT_STATE.yaml`, `NEXT_ACTION.md`.  
PR #449 merged, yet both still said the next action was independent receipt review. This is conservative drift, but it hides the real remediation step. The context/state update accompanying this report corrects that condition.

### I2. The post-merge consistency gate that would catch drift was retired

**File:** master checklist, `ARCH-GOVERNANCE-01`.  
The task is historically complete, but the dedicated post-merge checklist consistency gate was later removed, leaving only `CI_REQUIRED`. Restore at least a visible post-merge consistency check.

### I3. One frozen artifact is atomic; the full Provider-to-pair chain is not

**Code:** `src/w2/prematch/read_model_projection.py:838-963` and `materialize_projection_events()`.  
Lineup event, post-lineup plan, evaluations, supersessions, checkpoint, and readback reconciliation share one Session within one artifact. Provider ledger, raw payload, endpoint capture, lineup snapshots, observations, and projection are separate transactions. Multiple projection events are committed one by one. Model the chain as an explicit saga with stage states and replay rules.

### I4. First-write concurrency remains for evaluation, lineup, and supersession

**Code:** `src/w2/prematch/repository.py`; `src/w2/infrastructure/persistence/dynamic_prematch_models.py`.  
`SELECT previous -> INSERT evaluation -> INSERT supersession` has no row/advisory lock. Lineup uniqueness is `(fixture_id, lineup_input_hash)`, not one authoritative fixture event. Add fixture/market serialization and database constraints/fencing.

### I5. Daily quota preflight races across runs

**Code:** `src/w2/ingestion/future_refresh.py:1223-1235`.  
Two different keys can read the same old usage and both reserve none of it. Use an atomic quota reservation or serialized advisory lock, with Provider headers and local ledger reconciled conservatively.

### I6. Collection readiness can be false while top-level `/ready` is green

**Code:** `src/w2/monitoring/readiness.py:193-294`; `apps/api/main.py`.  
`readiness.py` is **not** a live Provider entrypoint. It only calculates status. The problem is aggregation: `matchday_intake.ready` does not affect top-level service `status`, so service readiness can be 200 while collection is disabled/unready. Split service liveness/readiness, collection readiness, and evaluation readiness.

### I7. Migration success does not fence worker/scheduler startup

**Code:** `infra/compose/compose.staging.yml`.  
Worker and scheduler do not depend on successful migration completion. Add schema-head fencing before either process can execute tasks.

### I8. Celery delivery semantics rely on framework defaults

The repository does not explicitly freeze acknowledgement, worker-lost, failure/timeout, autoretry, and publish-retry settings. Record the intended at-most-once/at-least-once trade-off in code and kill-test it.

### I9. Tests overuse mocks and static source assertions for runtime claims

Examples include monkeypatching the real refresh task and `urlopen`, and testing transaction behavior by checking source strings. Add PostgreSQL, Redis, worker-kill, timeout, schema-drift, and multi-event failure injection.

### I10. Cold pull, recovery, clock, resources, supply chain, permissions, and secret exposure remain unproven

Cold-pull SLO blocks continuous operation. Backup/restore and the other areas block Production approval until independently tested.

## 6. Minor findings

### M1. `ALREADY_RUNNING` returns exit code 0

**Code:** `scripts/run_prematch_refresh.py:166`.  
A caller can mistake “did not execute” for successful collection. Use a distinct exit code and explicit `executed=false`.

### M2. Pair `exact_line` uses float serialization

This is not a proven current data error. Decimal string or quarter-unit integer would improve cross-implementation reproducibility.

### M3. Current state had regrown into a duplicate task ledger

The previous EVAL-02B state block copied extensive receipts and evidence already owned by the master checklist. The accompanying state v4 keeps machine status and current blockers while leaving historical receipts in the checklist.

## 7. Corrected non-findings

### 7.1 Valid split-line averaging is intentional

`src/w2/ingestion/future_refresh.py` intentionally maps valid Asian split lines such as `2/2.5` to `2.25` and `-0/0.5` to `-0.25`. Tests freeze this behavior. No real Provider payload proves an invalid input domain. Do not change the parser without such evidence.

### 7.2 `readiness.py` is not a live-call path

It reads DB/Redis/schema/mount/config/registry state and constructs readiness output. The defect is readiness aggregation, not hidden Provider execution.

## 8. Real canary acceptance contract

A real canary is an evidence-chain acceptance test, not a process-liveness test.

All required deltas must be positive:

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

All evidence must belong to one reconciled lineage containing at least:

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

If any required delta is zero or lineage cannot be reconciled:

```text
CANARY = FAILED
EVAL_02B = BLOCKED
AUTO_RETRY = FORBIDDEN
```

If preconditions cannot reasonably produce the full evidence chain, the command must stop before the Provider call with zero cost. “No data this time” is not a canary pass.

## 9. Retained issues and risk acceptance

- **Legacy 35:** acceptable only as immutable facts permanently excluded from EVAL-02B. Reopen identity remediation solely if the exact original raw blob is recovered and its SHA-256 matches.
- **22-package SCC and `schemas`:** bounded technical debt with owner/exit criteria; do not invent deletes.
- **OPS-01 generic readiness producer:** may wait until another competition enablement, but enablement cannot claim readiness without it.
- **Cold-pull SLO:** may not block a tightly controlled foreground canary after C1-C11, but blocks persistent scheduler and Production.
- **Backup/restore and security review gaps:** block Production.

## 10. Required remediation sequence

1. Implement a shared default-deny runtime authorization and empty allowlist behavior.
2. Bind command identity to policy competition/season and require explicit persistence.
3. Add atomic task and quota reservations with fencing.
4. Replace Provider/ledger flow with a reconciled external-side-effect state machine.
5. Classify retry-safe versus uncertain-delivery failures.
6. Make schema/required-empty/lineup/ledger failures explicit.
7. Provide an effective rehearsal profile with `restart: no`.
8. Separate service readiness from collection/evaluation readiness.
9. Add migration fencing, explicit Celery semantics, and failure-injection tests.
10. Independently review the remediation before authorizing one real canary.

## 11. Final answers

### Are completed tasks really complete?

Yes within their frozen implementation scopes. EVAL-02B write-side 01–04 is code-complete, but runtime safety remediation is required and end-to-end is not validated.

### Can EVAL-02B start real collection now?

No. C1-C11 must be closed and independently reviewed first.

### Is the system ready for continuous operation?

No. Locking, cross-run quota reservation, readiness, migration fencing, Celery semantics, SLO, and recovery are incomplete.

### What must remain closed?

```text
PROVIDER = OFF
REAL_CANARY = NOT_AUTHORIZED
PERSISTENT_SCHEDULER = OFF
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
```
