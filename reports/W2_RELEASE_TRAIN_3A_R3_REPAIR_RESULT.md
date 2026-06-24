# W2 Release Train 3A-R3A Canonical Runtime Mount Repair

## Summary

- Release train package: `W2-RELEASE-TRAIN-3A-R3A`
- Base revision: `d1175151629298f67facb41a00cff5195c571af9`
- Repair status: `IMPLEMENTED_PENDING_RETRY_DEPLOYMENT`
- Root cause addressed: `STANDALONE_COMPOSE_RUNTIME_SOURCE_RESOLVED_INSIDE_INFRA_COMPOSE`
- Staging revision remains: `23c89be4d2a32019d8d21bb9b102ae0b7ca15c16`
- Migration executed: `false`
- Deployment executed: `false`
- Stage10E deployed: `false`
- Stage7I observer/collector started: `false`
- Gate3: `PARTIAL`
- Gate5: `OPEN`
- `candidate=false`
- `formal_recommendation=false`

## Repair

R2B proved that the future-refresh policy mount was fixed, but the worker failed before writing task audit with `PermissionError(13, 'Permission denied')`. The failed target mounted runtime from the standalone compose directory:

`/opt/w2/releases/371a9cb8618e7f47324e6ea9a2c9be35ca63199e/infra/compose/runtime`

That directory was root-owned and not writable by the non-root worker. R3A fixes the standalone staging compose runtime source so `api`, `worker`, and `scheduler` mount the release-root runtime symlink instead:

- `infra/compose/compose.staging.yml`: `../../runtime:/app/runtime`
- `infra/compose/staging-lite.override.yml`: unchanged as `./runtime:/app/runtime`

The canonical deployment contract remains that release-root `runtime` resolves to `/opt/w2/shared/runtime` before containers start.

## Worker Health Contract

The staging worker healthcheck now keeps the existing Celery ping and adds a no-side-effect runtime contract:

- `/app/runtime` is a directory;
- the current container user has write access via `os.access('/app/runtime', os.W_OK)`;
- the healthcheck does not create, delete, or modify runtime files.

No root-worker workaround, `0777`, permission change, ACL change, migration, or `.env` content access was introduced.

## Static Contract

`scripts/check_w2_future_refresh_staging_contract.py` now verifies:

- standalone `api`, `worker`, and `scheduler` runtime source is `../../runtime`;
- staging-lite runtime source remains `./runtime`;
- runtime mount target is `/app/runtime` and not read-only;
- worker healthcheck contains the no-side-effect writability contract;
- policy mounts remain read-only;
- scheduler future-refresh and policy contracts remain enabled only for scheduler;
- production, DeepSeek, CANDIDATE, RECOMMEND, and external alerting remain disabled;
- public business ports remain closed.

## Validation

Targeted validation performed during R3A:

- `python3 scripts/check_w2_future_refresh_staging_contract.py`: `PASS`
- `uv run pytest -q tests/contract/test_future_refresh_staging_runtime_mount.py tests/contract/test_future_refresh_staging_enablement.py`: `PASS`
- `uv run python scripts/check_compose_staging_ports.py`: `PASS`

Full repository validation is performed before the R3A commit.

## Next Action

Proceed to `W2-RELEASE-TRAIN-3A-R3B` staging retry only after R3A reaches GitHub CI success.
