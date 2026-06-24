# W2 Release Train 3A-R2A Policy Mount Static Repair

## Summary

- Release train package: `W2-RELEASE-TRAIN-3A-R2A`
- Base revision: `18f85ae379ea5ecb57ddda556e130ba3ca2c0337`
- Repair status: `IMPLEMENTED_PENDING_RETRY_DEPLOYMENT`
- Root cause addressed: `VERSIONED_POLICY_NOT_AVAILABLE_IN_STAGING_CONTAINERS`
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

The staging scheduler failed the R1 retry with `FUTURE_REFRESH_POLICY_INVALID` because the shared `/app/config` mount hid the versioned future-refresh policy packaged in the release. R2A keeps the existing `/app/config` mount and adds a read-only versioned policy submount for the worker and scheduler only:

- `infra/compose/compose.staging.yml`
  - `worker`: `../../config/policies:/app/config/policies:ro`
  - `scheduler`: `../../config/policies:/app/config/policies:ro`
- `infra/compose/staging-lite.override.yml`
  - `worker`: `./config/policies:/app/config/policies:ro`
  - `scheduler`: `./config/policies:/app/config/policies:ro`

API and Web were not given scheduler policy mounts or future-refresh enable flags.

## Static Contract

`scripts/check_w2_future_refresh_staging_contract.py` now verifies both staging compose variants for:

- exactly one read-only policy mount on worker and scheduler;
- target path exactly `/app/config/policies`;
- source path matching tracked `config/policies`;
- JSON-valid `config/policies/future_fixture_refresh.v1.json`;
- `world_cup_2026.enabled=true`;
- scheduler future-refresh enablement and competition ID;
- API/Web remaining free of scheduler enablement;
- production, DeepSeek, CANDIDATE, RECOMMEND, and external alerting disabled;
- no public business port exposure;
- scheduler healthcheck remaining non-dispatching.

The scheduler health contract remains fail-closed and now returns `false` for missing or invalid policy instead of raising an unstructured exception.

## Validation

Targeted validation performed during R2A:

- `python3 scripts/check_w2_future_refresh_staging_contract.py`: `PASS`
- `uv run pytest -q tests/contract/test_future_refresh_staging_enablement.py`: `PASS`
- `uv run python scripts/check_compose_staging_ports.py`: `PASS`

Full repository validation is performed before the R2A commit.

## Next Action

Proceed to `W2-RELEASE-TRAIN-3A-R2B` staging retry only after the R2A commit reaches GitHub CI success.
