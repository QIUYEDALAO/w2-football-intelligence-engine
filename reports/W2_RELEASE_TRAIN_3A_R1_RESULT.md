# W2 Release Train 3A-R1 Staging Retry Result

## Summary

- Release train: `W2-RELEASE-TRAIN-3A-R1`
- Target revision: `2d80e04b52af2b6ec957c554968c2c60a3a0cec0`
- Previous staging revision: `23c89be4d2a32019d8d21bb9b102ae0b7ca15c16`
- Result: `ROLLED_BACK_CONTRACT_FAILURE`
- Rollback revision: `23c89be4d2a32019d8d21bb9b102ae0b7ca15c16`
- Gate3: `PARTIAL`
- Gate5: `OPEN`
- `candidate=false`
- `formal_recommendation=false`

## Preflight

- Local target and both remote refs matched `2d80e04b52af2b6ec957c554968c2c60a3a0cec0`.
- Repair CI run `28124696214` was `success`.
- Staging started on `23c89be4d2a32019d8d21bb9b102ae0b7ca15c16`.
- `w2-staging.service` was enabled and active.
- Six containers were healthy.
- API `/health` and `/ready` returned healthy responses.
- Web returned HTTP `200`.
- Public business ports were closed.
- `.env` was checked by `stat` only; content was not read.
- Alembic version table was `0017_create_stage9a_shadow_strategy`.
- No active Stage7I observer or collector was found.

## Deployment

The target revision was deployed without migration:

- `/opt/w2/current` was switched to `2d80e04b52af2b6ec957c554968c2c60a3a0cec0`.
- Only `api`, `worker`, `scheduler`, and `web` were built/recreated with `--no-deps`.
- PostgreSQL and Redis were not recreated.
- Production, Stage10E, Stage7I observer/collector, permission changes, sensitive material changes, and W1 changes were not performed.

## Contract Failure

The API, worker, and web containers became healthy, but the scheduler healthcheck failed.

Observed scheduler health failure:

`FUTURE_REFRESH_POLICY_INVALID`

The health contract could not load the `world_cup_2026` future-refresh policy from the staging runtime config mount. Because the scheduler health contract failed, no future-refresh dispatch was accepted, no task audit was created, and no provider request was started for this validation path.

## Rollback

Rollback was executed immediately after the scheduler health contract failure.

Post-rollback facts:

- `/opt/w2/current` points to `23c89be4d2a32019d8d21bb9b102ae0b7ca15c16`.
- Six containers are healthy.
- API `/health` and `/ready` are healthy.
- Web returns HTTP `200`.
- Public business ports remain closed.
- Alembic remains `0017_create_stage9a_shadow_strategy`.

## Next Action

The next repair must make the future-refresh policy available to the staging scheduler despite the shared config mount, without reading or changing `.env`, without migration, without Stage10E, and without enabling production, CANDIDATE, or RECOMMEND.
