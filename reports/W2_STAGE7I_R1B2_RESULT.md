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

## Validation

Executed locally before commit:

- `uv run pytest -q tests/unit/test_stage7i_successor_tooling.py`
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
