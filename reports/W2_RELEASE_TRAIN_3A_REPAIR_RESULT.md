# W2 Release Train 3A-R1 Repair Result

## Summary

- Package: `W2 Release Train 3A-R1 scheduler enablement repair`
- Baseline: `4d17a50c70441e5820efa90dee7328d7c54b1bf1`
- Scope: static repair, tests, reports, commit, push, CI
- Deployment: not performed in this package
- Result: `IMPLEMENTED_PENDING_RETRY_DEPLOYMENT`
- Gate3: `PARTIAL`
- Gate5: `OPEN`
- `candidate=false`
- `formal_recommendation=false`

## Root Cause

Release Train 3A reached target staging health, but future-refresh validation failed because the staging scheduler container did not receive `W2_FUTURE_FIXTURE_REFRESH_ENABLED=true`. The scheduler therefore returned `DISABLED` and did not dispatch `w2.future_fixture_refresh`.

Root cause:

`STAGING_SCHEDULER_ENABLE_FLAG_NOT_WIRED`

## Static Repair

Changed paths:

- `infra/compose/compose.staging.yml`
- `infra/compose/staging-lite.override.yml`
- `apps/scheduler/main.py`
- `scripts/check_w2_future_refresh_staging_contract.py`
- `tests/contract/test_future_refresh_staging_enablement.py`

The staging scheduler now explicitly sets:

- `W2_FUTURE_FIXTURE_REFRESH_ENABLED="true"`
- `W2_FUTURE_FIXTURE_REFRESH_COMPETITION_ID="world_cup_2026"`

The default scheduler code remains fail-closed: if the env flag is absent, `future_fixture_refresh_tick()` returns `DISABLED`.

## Health Contract

The scheduler healthcheck now verifies:

- heartbeat is callable;
- future-refresh enablement flag is present;
- `world_cup_2026` policy is enabled.

The health contract does not:

- dispatch a Celery task;
- call provider APIs;
- write runtime files.

## Guardrails Preserved

- API/Web do not enable the scheduler future-refresh flag.
- Worker does not need or receive the scheduler enable flag.
- Production release remains disabled.
- DeepSeek remains disabled.
- Candidate and recommendation paths remain disabled.
- External alerting remains disabled.
- Public port policy remains unchanged.
- No `.env` change was made.
- No migration was introduced.
- No Stage10E deployment was performed.
- No Stage7I runtime action was performed.
- No W1 files were modified.

## Validation

Targeted validation required for this repair:

- `python3 scripts/check_w2_future_refresh_staging_contract.py`
- `uv run pytest -q tests/contract/test_future_refresh_staging_enablement.py`
- `uv run pytest -q -k "future_refresh or future_fixture_refresh"`
- `uv run python scripts/check_compose_staging_ports.py infra/compose/compose.staging.yml`
- `uv run python scripts/check_compose_staging_ports.py infra/compose/staging-lite.override.yml`

The package is ready for the next approved staging retry deployment.
