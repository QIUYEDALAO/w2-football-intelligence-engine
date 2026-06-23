# W2 Stage7I-R1B2 Result

## Summary

- Stage package: W2-STAGE7I-R1B2 dynamic successor selection and observer bootstrap
- Baseline commit: `7126f7540e8171dab83c1e2f81ab9a2b6c04fbbc`
- R1B2A CI run: `28010736953`
- R1B2A CI result: `success`
- Staging revision: `23c89be4d2a32019d8d21bb9b102ae0b7ca15c16`
- Gate5: `OPEN`
- Candidate output: `false`
- Formal recommendation output: `false`
- Final status: `SUCCESSOR_OBSERVATION_IN_PROGRESS`

R1B2 closed the legacy observer conflict, recovered future provider fixture
evidence, selected a dynamic successor fixture, synchronized runtime tooling, and
started a global-lock Stage7I observer. The stage does not claim Gate5 closure or
24-hour completion.

## Legacy Observer Disposition

User explicitly approved stopping the old Stage7I observer.

- Old PIDs: `723787`, `723789`
- Old PGID: `723782`
- Signal: `TERM`
- Stop result: exited after 1 second
- Runtime dir:
  `/opt/w2/shared/runtime/stage7i/runs/stage7i_20260622T183939Z_397fdfa`
- Runtime audit:
  `/opt/w2/shared/runtime/stage7i/runs/stage7i_20260622T183939Z_397fdfa/R1B2_LEGACY_TERMINATION_AUDIT.json`
- Sample count: `177`
- `COMPLETED` marker: absent
- `summary.json`: absent
- Candidate: `false`
- Formal recommendation: `false`

The old run remains non-qualifying for Gate5 forward evidence.

## Root Cause And Recovery

Read-model diagnosis found that staging `/v1/fixtures` only exposed an expired
World Cup fixture summary (`1489399`, kickoff `2026-06-22T17:00:00Z`). Scheduler
and worker inspection showed the deployed scheduler is heartbeat-only and the
worker only exposes `w2.ping`; no deployed scheduled task refreshes future
fixture read-model evidence.

Recovery used the existing W2 `ApiFootballClient` provider path inside the
staging API container. No curl key construction, `.env` read, service restart,
deployment, migration, W1 write, candidate output, or formal recommendation was
performed.

- Recovery dir:
  `/opt/w2/shared/runtime/stage7i/r1b2_recovery/stage7i_r1b2_recovery_20260623T095348Z`
- Provider requests: `3`
- Future fixtures recovered: `4`
- Future fixture IDs: `1489404`, `1489402`, `1489403`, `1539008`
- Selected fixture market coverage: `14` bookmakers, `607` market rows
- Quota after provider recovery: `7089`
- Provider blockers: none

## Candidate Manifest And Selection

The R1B2 run used explicit `fixtures`, `mappings`, and `markets` evidence files.
Fixture summaries alone were not accepted as candidate manifests.

- Candidate manifest count: `1`
- Rejected manifest rows: `3`
- Selector exit: `0`
- Selected fixture: `1489404`
- Scheduled kickoff: `2026-06-23T17:00:00Z`
- Selection source: `W2_STAGING_PROVIDER_DATA`
- Candidate: `false`
- Formal recommendation: `false`
- Selector blocker: none

## Runtime Tooling Fixes

Two ordinary tooling issues were fixed before bootstrap validation:

- `run_stage7i_observer.py` Alembic static parser now accepts typed Alembic
  fields such as `revision: str = "..."`
- `check_w2_stage7i.py` accepts legacy bootstrap `start.json` files without
  `runtime_dir` by deriving it from `selection_json_path`; newer observer starts
  now write `runtime_dir`

Regression coverage was added in
`tests/unit/test_stage7i_successor_tooling.py`.

## Successor Observer Bootstrap

- Runtime dir:
  `/opt/w2/shared/runtime/stage7i/runs/stage7i_20260623T095944Z_1489404`
- Observer PID: `1435421`
- Observer PGID: `1435396`
- Observer started at: `2026-06-23T09:59:44.331436Z`
- Expected end: `2026-06-24T09:59:44.331436Z`
- Global lock: `/opt/w2/shared/runtime/stage7i/observer-global.lock`
- First sample count: `1`
- Latest sample timestamp: `2026-06-23T09:59:44.331763Z`
- Latest sample blockers: none
- Latest quota remaining: `6323`
- Bootstrap checker: `PASS`

Current gate state from the first sample:

- `GATE_4_NATIONAL_1X2=PROVISIONAL_FORWARD_HOLDOUT_PENDING`
- `GATE_4_AH=BLOCKED_FORWARD_ONLY`
- `STAGE_9=BLOCKED`
- `target_n=50`
- `market_comparable_n=5`
- `current_settled_n=0`

## Runtime Safety

Confirmed during R1B2:

- `w2-staging.service`: enabled and active
- Long-running containers: healthy
- API `/health` and `/ready`: OK
- Public business ports: none
- `.env`: mode `600`; content not read or printed
- Active observer count before bootstrap: `0`
- Global lock before bootstrap: absent or unlocked

## Parallel Mainline Future Refresh Implementation

While the successor observer continues on staging revision
`23c89be4d2a32019d8d21bb9b102ae0b7ca15c16`, the mainline code now includes the
future fixture refresh implementation and operational hardening. This work is
code-only and is not deployed to staging until the active Stage7I observer
naturally completes.

Formal runtime entries:

- Scheduler: `apps/scheduler/main.py`
- Worker: `apps/worker/celery_app.py`

Implementation:

- `config/policies/future_fixture_refresh.v1.json`
- `src/w2/ingestion/future_refresh.py`
- `apps.scheduler.main.future_fixture_refresh_tick`
- `apps.worker.celery_app.future_fixture_refresh`
- `runtime/future_refresh/` is gitignored
- read API repository merges `runtime/future_refresh/read_model` fixtures,
  provider status, and append-only market ledger projections

Safety and quality controls:

- scheduler dispatches Celery only; provider calls run in worker context
- deterministic task key:
  `future-refresh:<competition_id>:<season>:<time-bucket>`
- cross-process singleton lock with Redis preferred and file fallback
- owner-marker lock release
- task audit with task ID, key, owner, queue/start/finish time, status, and
  summary
- policy-driven competition/season/horizon; unregistered competitions do not
  run
- uses existing `ApiFootballClient.request_live`
- no direct external URL/key construction in scheduler or worker
- every real provider attempt counts against request budget
- quota reserve
- retry/backoff with 401/403 no-retry and 429 counted retry
- raw payload SHA256
- per-response request audit linked to each persisted raw payload
- provider mapping evidence
- append-only market observation ledger
- stable observation identity dedup for replayed raw payloads
- latest read model and odds timeline projected from the ledger
- idempotent raw writes
- failure audit
- `candidate=false`
- `formal_recommendation=false`

Deployment status:

- `pending_staging_deployment=true`
- reason: preserve active Stage7I revision continuity
- no migration added
- no service restart performed
- no `/opt/w2/current` switch performed

## Validation

Executed locally before commit:

- `uv run pytest -q tests/unit/test_stage7i_successor_tooling.py`
- `uv run pytest -q tests/unit/test_future_fixture_refresh.py tests/unit/test_runtime.py tests/unit/test_stage10a_read_api.py`
- `uv run python scripts/check_w2_stage7i.py --mode bootstrap --expected-fixture-id 1489404 /tmp/w2-stage7i-bootstrap-verify/start.local.json`
- `make verify`
- `uv run python tests/secret_scan.py`
- `git diff --check`

Validation result:

- Stage checkers through `make verify`: `PASS`
- Ruff: `PASS`
- Mypy: `PASS`
- Pytest: `154 passed`
- Stage7I bootstrap checker: `PASS`
- Secret scan: `PASS`
- `git diff --check`: `PASS`

## Remaining Work

- Stage7I successor 24-hour observation is still in progress.
- Actual kickoff has not yet been captured by the continuous forward run.
- Closing observation has not yet been captured by the continuous forward run.
- Settlement and evaluation are not complete.
- Final Shadow DB audit is pending.
- Gate5 remains `OPEN`.
- Stage10E remains undeployed by design.

## Rollback

No rollback is required. The active observer is the intended R1B2 successor
process. Staging code, services, containers, database schema, deployment
revision, W1, sensitive values, GitHub settings, and production configuration
were not modified.

## Lifecycle Evidence Capture Readiness

This continuation audited whether the active Stage7I observer already captures
fixture-specific lifecycle evidence for fixture `1489404`.

Observer continuity at audit time:

- Observer PID: `1435421`
- Observer PGID: `1435396`
- Runtime dir:
  `/opt/w2/shared/runtime/stage7i/runs/stage7i_20260623T095944Z_1489404`
- Global lock holder: `1435421`
- Observer count: `1`
- Server revision: `23c89be4d2a32019d8d21bb9b102ae0b7ca15c16`
- API/Web health: `OK`
- Public business ports: none
- `.env`: mode `600`; content not read

Observer evidence audit found that `observations.jsonl` records service health,
quota summaries, forward counters, Gate state, and scheduler heartbeat. It does
not persist fixture-specific provider status, market payload hash, provider
market update time, result status, actual kickoff source, or closing resolver
evidence. A separate lifecycle collector was therefore required.

Implemented local tooling:

- `src/w2/monitoring/stage7i_lifecycle.py`
- `scripts/capture_stage7i_fixture_lifecycle.py`
- `scripts/build_stage7i_final_evidence.py`

The tooling was validated locally, copied to versioned runtime tooling, and
checked by SHA256 before runtime use:

- Tooling dir:
  `/opt/w2/shared/runtime/stage7i/tooling/lifecycle_8e467e6`
- Tooling archive SHA256:
  `2e25edb6bfbdad1cab60069a8a359d16d8374d8c8d64a5061e3b2bb82e4026de`

A single `--once` lifecycle probe was attempted through the staging API
container so the existing `ApiFootballClient` and injected runtime environment
were used without printing credentials or reading `.env`.

Runtime evidence generated:

- Lifecycle dir:
  `/opt/w2/shared/runtime/stage7i/runs/stage7i_20260623T095944Z_1489404/lifecycle`
- `request_audit.jsonl`: `1` event
- Last endpoint: `fixtures`
- HTTP status: `200`
- Raw payload hash: present
- Remaining provider quota: `299`

Quota authority correction:

- Previous blocker root cause: `x-ratelimit-remaining` was incorrectly treated
  as daily quota.
- Corrected semantics:
  - `x-ratelimit-requests-remaining`: daily quota
  - `x-apisports-requests-remaining`: daily quota
  - `response.requests.remaining`: daily quota from status payload
  - `x-ratelimit-remaining`: burst/short-window quota only
- Status probe: `2026-06-23T12:23:45.969614Z`
- Sanitized header names only were recorded; no key or auth header was printed.
- Daily remaining: `6925`
- Daily source: `x-ratelimit-requests-remaining`
- Burst remaining: `299`
- Burst source: `x-ratelimit-remaining`

Collector decision after quota fix:

- `stage7i_lifecycle_capture_status=ACTIVE`
- Reserve policy: `1500`
- Collector wrapper PID: `1549476`
- Lifecycle lock:
  `/opt/w2/shared/runtime/stage7i/lifecycle-1489404.lock`
- Lifecycle lock holder: `1549476`
- Tooling dir:
  `/opt/w2/shared/runtime/stage7i/tooling/lifecycle_dd98498_quota`
- Tooling archive SHA256:
  `09fb26f5bb2f5003d8f0d86f613e61188855bcfcbf8025b33c78515ddac80914`
- Observer PID/PGID/global lock unchanged.

First synced lifecycle evidence:

- `fixture_status.jsonl`: `1`
- `market_observations.jsonl`: `1`
- `result_status.jsonl`: `0`
- `request_audit.jsonl`: `2`
- Fixture provider status: `NS`
- Market bookmaker count: `14`
- Market live: `false`
- Market suspended: `false`
- Latest daily remaining: `6923`
- Latest burst remaining: `298`
- Latest daily source: `x-ratelimit-requests-remaining`

Final evidence builder output:

- File:
  `/opt/w2/shared/runtime/stage7i/runs/stage7i_20260623T095944Z_1489404/lifecycle/final_evidence.in_progress.json`
- Status: `IN_PROGRESS`
- Actual kickoff status: `ACTUAL_KICKOFF_SOURCE_UNAVAILABLE`
- Closing status: `PENDING_ACTUAL_KICKOFF`
- Blockers:
  - `OBSERVER_SUMMARY_NOT_COMPLETE`
  - `ACTUAL_KICKOFF_SOURCE_UNAVAILABLE`
  - `PENDING_ACTUAL_KICKOFF`
- Candidate: `false`
- Formal recommendation: `false`

No actual kickoff, closing, settlement, evaluation, or Shadow DB completion was
fabricated. Gate5 remains `OPEN`.
