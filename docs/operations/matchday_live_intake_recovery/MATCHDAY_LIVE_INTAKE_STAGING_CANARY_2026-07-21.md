# W2 Matchday Live Intake Staging Canary - 2026-07-21

## GitHub Context

- Repository: `QIUYEDALAO/w2-football-intelligence-engine`
- Branch: `codex/w2-matchday-live-intake-recovery`
- Pull request: `#369`
- Commit SHA: `50a03f8fd00749134fd800ab631a3c36d126caa3`

## Deployment

Staging was deployed from commit `50a03f8fd00749134fd800ab631a3c36d126caa3`.

Verified runtime facts:

- API `/v1/version` reports `api_git_sha=50a03f8fd00749134fd800ab631a3c36d126caa3`.
- Alembic current revision is `0032_create_matchday_fixture_identities`.
- New table `matchday_fixture_identities` exists.
- `api`, `web`, `worker`, `postgres`, and `redis` are healthy.
- `scheduler` is stopped after the controlled canary.

## Controlled Provider Canary

The canary used Allsvenskan only, with a small budget:

- Provider league: `113`
- Season: `2026`
- Request budget: `6`
- Max odds requests: `2`

Result:

- Status: `COMPLETED`
- Fixture count: `14`
- Market snapshot count: `2`
- Ledger appended count: `640`
- Request count: `4`
- Selected market fixture IDs: `1494224`, `1494218`
- Blockers: none

## Database Evidence

After the canary:

- Allsvenskan fixture identities: `14`
- Fixture identities linked to endpoint capture: `14`
- Team identity status: `REVIEW_REQUIRED=14`
- Endpoint captures: `fixtures=2`, `odds=10`, `status=2`
- Market observations: `1X2=288`, `ASIAN_HANDICAP=1331`, `TOTALS=1720`
- Recommendations: `0`
- Recommendation locks: `0`

## Readiness Truth

The service is healthy, but matchday intake remains `NOT_READY` for continuous operation. This is expected because the current runtime config keeps provider calls, future refresh, and scheduler operation disabled unless explicitly opened.

Remaining blockers:

- `PROVIDER_SCHEDULER_DISABLED`
- `FUTURE_FIXTURE_REFRESH_DISABLED`
- `PROVIDER_CALLS_DISABLED`
- `ALLSVENSKAN_NOT_CONFIGURED`
- `TEAM_IDENTITY_REVIEW_REQUIRED`
- `F5_CANONICAL_TEAM_HISTORY_NOT_READY`
- `F8_REVIEWED_ASOF_TEAM_VALUE_NOT_READY`
- `MODEL_EVIDENCE_NOT_VALIDATED`

This proves that provider credential and fixture visibility are no longer the blocker. Recommendation remains blocked because evidence authority and readiness gates are still incomplete.

Final state: `MANUAL_APPROVAL_REQUIRED`
