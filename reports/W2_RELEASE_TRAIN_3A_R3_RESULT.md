# W2 Release Train 3A-R3B Staging Retry Result

## Summary

- Release train package: `W2-RELEASE-TRAIN-3A-R3B`
- Target revision: `5e1179f2502e6fe78c7a0a58c81dcacf9341dc53`
- Previous staging revision: `23c89be4d2a32019d8d21bb9b102ae0b7ca15c16`
- Result: `ROLLED_BACK_CONTRACT_FAILURE`
- Failure: `SHARED_RUNTIME_NOT_WRITABLE_FOR_NON_ROOT_WORKER`
- Rollback revision: `23c89be4d2a32019d8d21bb9b102ae0b7ca15c16`
- Deployment freeze: `ACTIVE`
- Gate3: `PARTIAL`
- Gate5: `OPEN`
- `candidate=false`
- `formal_recommendation=false`

## Preflight

- Local target and both remote refs matched `5e1179f2502e6fe78c7a0a58c81dcacf9341dc53`.
- R3A CI run `28129100759` was `success`.
- Staging started on `23c89be4d2a32019d8d21bb9b102ae0b7ca15c16`.
- `w2-staging.service` was enabled and active.
- Six containers were healthy.
- API `/health` and `/ready` returned healthy responses.
- Web returned HTTP `200`.
- Public business ports were closed; API/Web remained localhost-only.
- `.env` was checked by `stat` only; content was not read.
- `/opt/w2/shared/runtime` resolved to itself and was observed as `drwx------ ubuntu ubuntu`.
- Alembic version table remained `0017_create_stage9a_shadow_strategy`.
- No active Stage7I observer or collector was found.

## Deployment Order

The target release was created and `release/runtime` was linked to `/opt/w2/shared/runtime` before image startup. The target images were built, then `/opt/w2/current` was switched to `5e1179f2502e6fe78c7a0a58c81dcacf9341dc53`.

To avoid premature future-refresh dispatch, only these target services were recreated before the worker runtime contract:

- `api`
- `worker`
- `web`

The target scheduler was not recreated before the failure. PostgreSQL and Redis were not recreated. Migration was not run.

## Worker Pre-Dispatch Contract

The worker was inspected before target scheduler startup:

- runtime mount source: `/opt/w2/releases/5e1179f2502e6fe78c7a0a58c81dcacf9341dc53/runtime`
- runtime mount resolved target: `/opt/w2/shared/runtime`
- container user id: `10001`
- container root user: `false`
- `/app/runtime` is a directory: `true`
- `/app/runtime` writable via `os.access`: `false`
- policy file readable and SHA256 matched release policy
- `w2.future_fixture_refresh` was registered

Because `/app/runtime` was not writable by the non-root worker, target scheduler was not started and no provider call was made.

## Rollback

Rollback was executed immediately.

Post-rollback facts:

- `/opt/w2/current` points to `23c89be4d2a32019d8d21bb9b102ae0b7ca15c16`.
- Six containers are healthy.
- API `/health` and `/ready` are healthy.
- Web returns HTTP `200`.
- Public business ports remain closed.
- Alembic remains `0017_create_stage9a_shadow_strategy`.

## Required Decision

The next retry requires an explicitly approved shared runtime writability strategy for the non-root worker (`uid=10001`). This package did not and must not use `chmod`, `chown`, ACL changes, root worker, `0777`, migration, production settings, data deletion, Stage10E, Stage7I recovery, Baselight, CANDIDATE, or RECOMMEND.
