# W2 Release Train 3A Result

## Summary

- Release train: `W2-RELEASE-TRAIN-3A`
- Scope: future-refresh hardening staging deployment
- Target revision: `fcfba08824f42917d30bc8d0742ea99d2fc18349`
- Previous staging revision: `23c89be4d2a32019d8d21bb9b102ae0b7ca15c16`
- Result: `ROLLED_BACK_CONTRACT_FAILURE`
- Rollback revision: `23c89be4d2a32019d8d21bb9b102ae0b7ca15c16`
- Gate3: `PARTIAL`
- Gate5: `OPEN`
- `candidate=false`
- `formal_recommendation=false`

## Preflight

- GitHub `main` and `chore/stage7i-24h-observation` both pointed to the target revision.
- GitHub Actions run `28122483166` for the target revision completed with `success`.
- Staging started on revision `23c89be4d2a32019d8d21bb9b102ae0b7ca15c16`.
- `w2-staging.service` was enabled and active.
- Six long-running containers were healthy.
- API `/health` and `/ready` returned healthy responses.
- Web returned HTTP `200` on localhost.
- Public business ports were closed; only SSH was public.
- `/opt/w2/shared/.env` was checked by `stat` only and had mode `600`.
- `.env` content was not read.
- Alembic version table was `0017_create_stage9a_shadow_strategy`.

## Deployment Method

The deployment intentionally avoided migration and production actions:

- No production target was used.
- No Stage10E deployment was performed.
- No Stage7I observer or collector was started.
- No migration was executed.
- No permissions or sensitive material were modified.
- No W1 files were modified.
- The full systemd `docker compose up` path was avoided because the compose file contains a `migration` service.
- Only app services were rebuilt and recreated with no dependency recreation: `api`, `worker`, `scheduler`, and `web`.
- PostgreSQL and Redis were not recreated.

## Target Validation Failure

The target revision booted and core health checks passed, but future-refresh did not satisfy the release contract.

Observed target facts:

- `current` pointed to `fcfba08824f42917d30bc8d0742ea99d2fc18349`.
- Six containers were healthy.
- API and Web were healthy.
- Public business ports remained closed.
- Worker registered `w2.future_fixture_refresh`.
- Scheduler `future_fixture_refresh_tick()` returned `DISABLED`.
- Scheduler container did not have `W2_FUTURE_FIXTURE_REFRESH_ENABLED` set.
- No `runtime/future_refresh/future_refresh_audit.json` was created.
- The append-only market ledger and read model could not be verified because dispatch was disabled.

Failure:

`FUTURE_REFRESH_SCHEDULER_DISPATCH_DISABLED`

## Rollback

Rollback was executed immediately after the future-refresh contract failure.

Post-rollback facts:

- `/opt/w2/current` points to `23c89be4d2a32019d8d21bb9b102ae0b7ca15c16`.
- `w2-staging.service` is enabled and active.
- Six containers are healthy.
- API `/health` and `/ready` are healthy.
- Web returns HTTP `200` on localhost.
- Public business ports remain closed.
- Alembic version table remains `0017_create_stage9a_shadow_strategy`.
- `.env` content was not read.

## Decision

Release Train 3A is not accepted for staging. The attempted deployment was rolled back successfully and the staging runtime is back on the previous revision.

Next action:

`Release Train 3A repair for scheduler future-refresh enablement`

The repair must make scheduler enablement explicit in staging without enabling production, DeepSeek, CANDIDATE, or RECOMMEND.
