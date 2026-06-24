# W2 Release Train 3A-R2B Staging Retry Result

## Summary

- Release train package: `W2-RELEASE-TRAIN-3A-R2B`
- Target revision: `371a9cb8618e7f47324e6ea9a2c9be35ca63199e`
- Previous staging revision: `23c89be4d2a32019d8d21bb9b102ae0b7ca15c16`
- Result: `ROLLED_BACK_CONTRACT_FAILURE`
- Rollback revision: `23c89be4d2a32019d8d21bb9b102ae0b7ca15c16`
- Deployment freeze: `ACTIVE`
- Gate3: `PARTIAL`
- Gate5: `OPEN`
- `candidate=false`
- `formal_recommendation=false`

## Preflight

- Local target and both remote refs matched `371a9cb8618e7f47324e6ea9a2c9be35ca63199e`.
- R2A CI run `28127791079` was `success`.
- Staging started on `23c89be4d2a32019d8d21bb9b102ae0b7ca15c16`.
- `w2-staging.service` was enabled and active.
- Six containers were healthy.
- API `/health` and `/ready` returned healthy responses.
- Web returned HTTP `200`.
- Public business ports were closed; API/Web remained localhost-only.
- `.env` was checked by `stat` only; content was not read.
- Alembic version table remained `0017_create_stage9a_shadow_strategy`.
- No active Stage7I observer or collector was found.

## Deployment

The target revision was deployed without migration:

- `/opt/w2/current` was switched to `371a9cb8618e7f47324e6ea9a2c9be35ca63199e`.
- Only `api`, `worker`, `scheduler`, and `web` were built/recreated with `--no-deps`.
- PostgreSQL and Redis were not recreated.
- Stage10E, production, Stage7I observer/collector, permission changes, sensitive material changes, and W1 changes were not performed.

## Policy Contract

The R2A policy mount repair succeeded in staging:

- Scheduler and worker both exposed `/app/config/policies/future_fixture_refresh.v1.json`.
- Both container policy SHA256 values matched the release tracked policy SHA256: `700389aefeb2c5f77e9fb0c35a3695775512fad16c74cf2bf0090f0eddedaf27`.
- Scheduler future-refresh contract returned `contract_ready=true`.
- `world_cup_2026` policy was enabled.
- DeepSeek, CANDIDATE, RECOMMEND, production release, and external alerting remained disabled.

## Contract Failure

Scheduler auto-dispatched one future-refresh task and no manual tick was called:

- task key: `future-refresh:world_cup_2026:2026:20260624T203000Z`
- task id: `future-refresh:world_cup_2026:2026:20260624T203000Z:003173bb-644a-4ea0-9074-05d4e0e92d84`

The worker registered `w2.future_fixture_refresh` and received the task, but failed before writing the task audit:

- failure: `PermissionError(13, 'Permission denied')`
- task audit created: `false`
- future_refresh_audit created: `false`
- runtime mount source: `/opt/w2/releases/371a9cb8618e7f47324e6ea9a2c9be35ca63199e/infra/compose/runtime`
- runtime mount permissions observed after failure: `drwxr-xr-x root root`

This is a contract failure because the worker task failed and audit/schema evidence was not created.

## Rollback

Rollback was executed immediately.

Post-rollback facts:

- `/opt/w2/current` points to `23c89be4d2a32019d8d21bb9b102ae0b7ca15c16`.
- Six containers are healthy.
- API `/health` and `/ready` are healthy.
- Web returns HTTP `200`.
- Public business ports remain closed.
- Alembic remains `0017_create_stage9a_shadow_strategy`.

## Next Action

Repair staging runtime mount writability for the non-root worker before the next retry. The policy mount issue is fixed, but future-refresh cannot be accepted until runtime/audit writes are possible without changing sensitive material, permissions, migrations, or production settings.
