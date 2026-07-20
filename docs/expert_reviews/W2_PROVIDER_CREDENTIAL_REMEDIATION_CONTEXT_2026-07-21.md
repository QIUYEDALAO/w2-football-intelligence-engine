# W2 Provider Credential Remediation Context - 2026-07-21

This is a GitHub-visible context sync only.

## Question

Why was the provider credential missing, and can Codex resolve it?

## Answer

Codex can resolve the configuration and deployment wiring once the credential value exists in an authorized source. Codex cannot invent, recover, or obtain the API-Football credential if it is absent from the server, local workspace, or connected secret store.

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

## Current Status

```text
MATCHDAY_LIVE_INTAKE_REMEDIATION_REQUIRED
BLOCKER=LIVE_GATE_API_KEY_NOT_VISIBLE
NEEDS_AUTHORIZED_PROVIDER_CREDENTIAL
```

