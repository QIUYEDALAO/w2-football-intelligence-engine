# W2 Stage7H Sensitive Value Exposure Incident

incident_id: `W2-STAGE7H-SENSITIVE-EXPOSURE-20260622-001`
detected_at_utc: `2026-06-22T08:23:37.223231+00:00`
trigger: `docker compose config expanded environment`

## Affected Sensitive Value Classes

- `POSTGRES_PASSWORD`
- `W2_DATABASE_URL`
- `API_FOOTBALL_KEY` if present in expanded compose environment

## Exposure Scope

- Terminal/session only.
- Temporary compose config file deleted from server `/tmp`.
- Temporary archive files deleted from server `/tmp`.
- Matching local `/tmp` compose config and archive files deleted.
- Not committed.
- Not pushed.
- Not served publicly.
- No `.env` content is included in this report.
- No sensitive value is included in this report.

## Immediate Actions

- Stopped deployment before switching `/opt/w2/current`.
- Did not run migration.
- Did not restart `w2-staging.service`.
- Deleted temporary compose config artifacts.
- Deleted temporary W2 release tarballs from `/tmp`.
- Confirmed server current remains on `2f85408c2936be6a62b8d6cc7491cc3f4819dd85`.
- Confirmed public business ports were not opened.

## Required Actions

- Rotate PostgreSQL credential.
- Rotate API-Football key.
- Replace compose preflight with a redacted/no-interpolate or structural parser that never writes or prints expanded environment values.

## Current Blocker

`USER_ACTION_REQUIRED_NEW_API_FOOTBALL_KEY`

`NEW_API_FOOTBALL_KEY` is not present in the current Codex process environment. Per policy, the old key must not be reused and no key should be pasted into chat.

## Final Status

`PENDING_ROTATION`


## Rotation and Hardening Update (2026-06-22T09:47:23+00:00)

- PostgreSQL credential rotation: `COMPLETED`.
- API-Football key injection/rotation: `COMPLETED`; value was never written to this report.
- Shared environment file permissions: `600` verified on server metadata only.
- Compose expanded environment preflight replaced by structural port checker: `COMPLETED`.
- Expanded compose output is no longer written or printed by the deployment script.
- Previous provider credential revocation at provider console: `PREVIOUS_PROVIDER_CREDENTIAL_REVOCATION=UNVERIFIED_WARN_ONLY`.

## Final Containment Status

`SENSITIVE_VALUE_INCIDENT=CONTAINED`
`POSTGRES_PASSWORD_ROTATED=YES`
`API_FOOTBALL_KEY_ROTATED=YES`
`COMPOSE_PREFLIGHT_HARDENED=YES`
`NO_SENSITIVE_VALUE_LEAK=PASS`

## Server Validation Closure (2026-06-22T09:59:54+00:00)

- Shared environment file metadata verified as owner/group `ubuntu:ubuntu` and mode `600`; contents were not printed.
- Runtime logs checked by value matching inside the server only; output was limited to category counts.
- Provider credential value matches in recent logs: `0`.
- PostgreSQL credential value matches in recent logs: `0`.
- Database URL value matches in recent logs: `0`.
- Authorization/API key header matches in recent logs: `0`.
- Previous provider credential revocation at provider console remains `PREVIOUS_PROVIDER_CREDENTIAL_REVOCATION=UNVERIFIED_WARN_ONLY`.

`NO_SENSITIVE_VALUE_LEAK=PASS`
