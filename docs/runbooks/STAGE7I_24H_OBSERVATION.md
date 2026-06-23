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

Start it once with `flock` and `nohup`:

```bash
flock -n /opt/w2/shared/runtime/stage7i/observer.lock \
  nohup python3 /opt/w2/shared/runtime/stage7i/run_stage7i_observer.py \
  --current-dir /opt/w2/current \
  >/opt/w2/shared/runtime/stage7i/nohup.out 2>&1 &
```

If the lock is already held, do not start another observer.

When a new observation is intentionally started after an approved release train,
write it to a new runtime subdirectory and pass the intended release revision
explicitly:

```bash
flock -n /opt/w2/shared/runtime/stage7i/runs/<run_id>/observer.lock \
  nohup python3 /opt/w2/shared/runtime/stage7i/run_stage7i_observer.py \
  --runtime-dir /opt/w2/shared/runtime/stage7i/runs/<run_id> \
  --current-dir /opt/w2/current \
  --baseline-revision <current_deployment_revision> \
  >/opt/w2/shared/runtime/stage7i/runs/<run_id>/nohup.out 2>&1 &
```

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
