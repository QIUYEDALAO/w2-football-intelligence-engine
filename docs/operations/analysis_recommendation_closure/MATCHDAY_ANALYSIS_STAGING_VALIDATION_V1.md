# Matchday Analysis Staging Validation V1

## Baseline

- Branch: `codex/w2-analysis-recommendation-closure`
- Implementation SHA: `166c573d432a5acc3e0f798f0df674a55ff0dbb4`
- Staging release SHA: `166c573d432a5acc3e0f798f0df674a55ff0dbb4`
- Migration current: `0032_create_matchday_fixture_identities`
- Capability manifest SHA: `59b78f997a8d55c9953c6667a3e35b9ec780aa98e9a2df36f684b3f0e0511422`

## Runtime

- `api`: healthy
- `web`: healthy
- `worker`: healthy
- `postgres`: healthy
- `redis`: healthy
- `scheduler`: stopped

## Provider Safety

- Worker `W2_PROVIDER_CALLS_DISABLED=true`
- Worker `W2_PROVIDER_SCHEDULER_ENABLED=false`
- Provider calls during this validation: `0`

## Materialization

- Matchday evidence manifests for smoke fixtures: `2`
- Recommendations: `0`
- Recommendation locks: `0`

## Final State

`ANALYSIS_CHAIN_MODEL_INPUT_REMEDIATION_REQUIRED`

Always retained:

- `FORMAL_DISABLED`
- `LOCK_DISABLED`
- `PRODUCTION_DISABLED`
- `MANUAL_APPROVAL_REQUIRED`
