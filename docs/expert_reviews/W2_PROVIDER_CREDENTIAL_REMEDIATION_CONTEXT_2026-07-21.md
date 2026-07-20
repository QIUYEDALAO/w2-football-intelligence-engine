# W2 Provider Credential Remediation Context - 2026-07-21

This is a GitHub-visible context sync only.

## Question

Why was the provider credential missing, and can Codex resolve it?

## Answer

Codex can resolve the configuration and deployment wiring once the provider auth value exists in an authorized source. Codex cannot invent or retrieve that value when it is absent from the server, local workspace, and connected storage.

The diagnosed blocker remains:

```text
reason_code=LIVE_GATE_API_KEY_NOT_VISIBLE
process=worker
function=w2.providers.api_football.ApiFootballClient.request_live
provider_calls_disabled=false
endpoint_allowlist=status,fixtures,odds,lineups
```

The staging compose file already references `W2_API_FOOTBALL_API_KEY`, but `/opt/w2/shared/.env` has the variable present with an empty value. The worker and scheduler therefore start correctly but cannot authenticate provider calls.

## What Can Be Fixed Without Code

If an authorized API-Football credential is provided, the remediation is staging environment configuration, not a code feature:

1. Put the credential into the staging env file consumed by compose.
2. Restart only the worker and scheduler containers.
3. Re-run the bounded `ApiFootballClient.request_live()` status/fixtures canary.
4. Resume scheduler only after the canary proves `credential_visible=true`.

No formal recommendation, lock, production release, OFFICIAL capture, or calibration should be enabled by this remediation.

## Remediation Update

The local Codex process had `W2_API_FOOTBALL_API_KEY` available. The staging server env file had the same variable present but empty.

Remediation performed:

1. The local credential was transferred to the staging env file through stdin without logging the value.
2. A backup of the previous staging env file was created.
3. Only worker and scheduler containers were recreated.
4. API, web, postgres, and redis were not restarted.

Post-remediation verification:

```text
worker credential_visible=true
scheduler credential_visible=true
worker W2_PROVIDER_CALLS_DISABLED=false
scheduler W2_PROVIDER_CALLS_DISABLED=false
endpoint_allowlist=status,fixtures,odds,lineups
```

Controlled provider canary:

```text
status endpoint: HTTP 200
fixtures endpoint: HTTP 200
league=113
season=2026
from=2026-07-20
to=2026-08-03
response_count=16
payload_sha256=05793353bc8a7a7ec976e0c53c88dde0e35863dae988ccdc91cafd49c950b3bf
```

No raw provider payload or credential was logged.

## Current Status

```text
PROVIDER_CREDENTIAL_VISIBLE_TO_WORKER
PROVIDER_STATUS_CANARY_OK
ALLSVENSKAN_FIXTURES_CANARY_OK
NEXT_STEP=CANONICAL_FIXTURE_AND_ODDS_PERSISTENCE
```
