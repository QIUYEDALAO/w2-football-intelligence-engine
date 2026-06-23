# Stage7I 24H Staging Observation

Stage7I observes the Seoul VPS staging runtime for 24 hours without changing
runtime logic, schema, model configuration, Gate state, or service topology.

## Scope

- Observe existing `w2-staging.service` and its long-running containers.
- Sample every 5 minutes for at least 24 hours.
- Write runtime-only files under `/opt/w2/shared/runtime/stage7i/`.
- Keep API/Web bound to localhost and keep production, DeepSeek, CANDIDATE, and
  RECOMMEND disabled.

## Runtime Files

- `observations.jsonl`
- `observer.log`
- `observer.pid`
- `summary.json`
- `COMPLETED`

These files are runtime artifacts and must not enter Git.

## Start Command

The observer is copied to:

`/opt/w2/shared/runtime/stage7i/run_stage7i_observer.py`

R1B is split into three steps:

- `Stage7I-R1B1 successor tooling readiness`: code, tests, and documentation
  only. It does not select a real fixture and does not start an observer.
- `Stage7I-R1B2A live selection contract closure`: proves the staging
  `/v1/fixtures` response shape, builds the candidate manifest contract, and
  keeps selection dry-run only. It does not choose a formal successor fixture
  and does not start an observer.
- `Stage7I-R1B2B dynamic successor selection and observer bootstrap`: copies
  the CI-validated tooling to staging, performs the actual local/staging
  selection, and starts a new observer when approved.

## Candidate Manifest Builder

`/v1/fixtures` returns a `FixtureSummary` intended for read API and dashboard
display. It is not a complete Stage7I candidate manifest because it does not
prove provider mapping reliability or market evidence by itself.

Build a manifest with explicit fixture, mapping, and market evidence:

```bash
python3 scripts/build_stage7i_successor_candidates.py \
  --api-base http://127.0.0.1:18000 \
  --mapping-input /path/to/provider-mapping-evidence.json \
  --market-input /path/to/market-observation-evidence.json \
  --output /tmp/stage7i-successor-candidates.json
```

The builder is read-only. It does not start an observer, write the database, or
read `.env`. Evidence must contain:

- provider mapping source, confidence, conflict state, and evidence SHA;
- market source/provenance, captured time, bookmaker count, live/suspended
  flags, freshness limit, and evidence SHA;
- `candidate=false` and `formal_recommendation=false`.

Missing mapping evidence, missing market evidence, missing freshness policy, or
missing evidence SHA is a rejection reason, not something the builder infers.

## Successor Selector

The selector is dry-run by default and is read-only:

```bash
python3 scripts/select_stage7i_successor.py \
  --candidate-manifest /tmp/stage7i-successor-candidates.json \
  --output /tmp/stage7i-successor-selection.json
```

For hermetic tests, `--input-json` is accepted as an alias for a candidate
manifest. Raw `FixtureSummary` responses are rejected. Non-localhost API URLs
are rejected.

The selector requires:

- `status=NS`;
- kickoff later than `now + 6h`;
- kickoff earlier than `run_end - 6h`;
- reliable provider mapping with no conflict;
- real and fresh pre-match market observation;
- mapping and market evidence SHA values;
- no active Stage7I global observer lock;
- no active legacy Stage7I observer PID under the runtime root;
- fixture is not the archived fixture `1489401`.

The selector does not use team popularity, external schedules, score sites, or
hardcoded fixture IDs. Dry-run mode must not create a global lock file, runtime
directory, or selection/start evidence; only an explicit `--output` file may be
written.

The 6h/6h observation window is a Stage7I evidence policy, not an odds or model
threshold. It exists to cover multiple pre-match market observations, closing,
actual kickoff, the full match, result synchronization, settlement/evaluation,
and final audit. Do not lower it automatically when no fixture qualifies.

## Start Command

All runs must use one global singleton lock:

`/opt/w2/shared/runtime/stage7i/observer-global.lock`

The Python observer also acquires this lock internally with non-blocking
`fcntl.flock`; external `flock` is optional belt-and-braces, not the only
protection.

Start a successor observer only in R1B2 after a valid selection JSON exists:

```bash
flock -n /opt/w2/shared/runtime/stage7i/observer-global.lock \
  nohup python3 /opt/w2/shared/runtime/stage7i/run_stage7i_observer.py \
  --runtime-dir /opt/w2/shared/runtime/stage7i/runs/<run_id> \
  --current-dir /opt/w2/current \
  --fixture-id <selected_fixture_id> \
  --scheduled-kickoff-utc <selected_fixture_kickoff_utc> \
  --baseline-revision <current_deployment_revision> \
  --expected-alembic-head 0017_create_stage9a_shadow_strategy \
  --selection-json /opt/w2/shared/runtime/stage7i/runs/<run_id>/selection.json \
  --global-lock-path /opt/w2/shared/runtime/stage7i/observer-global.lock \
  >/opt/w2/shared/runtime/stage7i/runs/<run_id>/nohup.out 2>&1 &
```

If the lock is already held, do not start another observer.

## Safety Rules

- Do not restart systemd or containers during observation.
- Do not run migration, prune Docker, or edit `.env`.
- Do not manually run forward cycles.
- Do not read or print environment values, provider credentials, auth headers,
  PostgreSQL credentials, or full database URLs.
- Continue recording when blockers appear; do not auto-fix them.
- If an approved deployment interrupts the 24-hour window, record the
  interruption as evidence and restart the 24-hour clock only after an explicit
  recovery decision.
- If the interrupted fixture has already kicked off, do not restart the same
  fixture and do not backfill it into forward evidence.
- An interrupted run for an already-started fixture must be archived as
  `BLOCKED_NON_QUALIFYING`.
- Do not infer actual kickoff from polling time, scheduled kickoff, or status
  transitions. If no internal source exists, record
  `ACTUAL_KICKOFF_SOURCE_UNAVAILABLE`.
- Closing can only be derived after an internally sourced actual kickoff exists,
  and only from the last real market observation strictly before actual kickoff.

## Pass Criteria

- Current revision remains unchanged.
- systemd remains active.
- PostgreSQL, Redis, API, Worker, Scheduler, and Web avoid abnormal restarts.
- Worker remains healthy, or never has two consecutive unhealthy samples.
- Scheduler heartbeat remains fresh.
- API `/ready` never fails twice consecutively.
- Quota remains at or above reserve.
- Public business ports remain closed.
- Gate 4 remains pending and Stage 9 remains blocked.

## Recovery Point

The Stage7I archive for fixture `1489401` is non-qualifying. The next valid
recovery is:

`Stage7I-R1B successor forward observation bootstrap`

The successor fixture must be selected dynamically from W2 staging/provider data
and must satisfy all of the following:

1. `status=NS`.
2. Actual kickoff has not occurred.
3. Provider mapping is reliable.
4. A real pre-match market observation exists.
5. No other active observer conflicts with the successor run.
6. The observation window covers pre-match, actual kickoff, legal post-match
   settlement, and final audit.

The successor fixture must not be hardcoded. External news or score sites must
not replace the internal evidence chain.

A successor run remains blocked until a single observer run reaches 24 hours on
one stable deployment revision and its runtime summary proves:

- no unexplained service or container restart loop;
- no public business port exposure;
- no candidate or formal recommendation output;
- closing observation, actual kickoff, settlement, and evaluation boundaries
  are recorded without forward/retrospective mixing;
- final Shadow DB audit remains clean.
