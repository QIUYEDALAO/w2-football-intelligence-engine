# W2 Matchday Live Intake Recovery Context - 2026-07-21

This is a GitHub-visible context sync only.

Task: W2 MATCHDAY-LIVE-INTAKE-RECOVERY.

Start baseline: `037b88cd529e4c19ecf7ddc51f50106a6a996572`.

New branch: `codex/w2-matchday-live-intake-recovery`.

## Current Finding

The real blocker is not "no matches exist" and not a `fetch()` interface misuse.

The live gate diagnosis from the real worker container returned:

```text
reason_code=LIVE_GATE_API_KEY_NOT_VISIBLE
process=worker
function=w2.providers.api_football.ApiFootballClient.request_live
message=provider credential is not visible to the process
provider_calls_disabled=false
allow_live=true
endpoint_allowlist=status,fixtures,odds,lineups
```

The worker and scheduler are configured to allow provider calls, and scheduler competition IDs include `allsvenskan`, but `W2_API_FOOTBALL_API_KEY` is not visible inside the worker or scheduler containers.

## Staging Baseline

- Staging release directory points to `037b88cd529e4c19ecf7ddc51f50106a6a996572`.
- API, web, worker, postgres, and redis were healthy.
- Scheduler was stopped for diagnosis to avoid repeated provider calls.
- Schema revision was `0031_finalize_matchday_execution_identity`.
- Provider request logs: 0.
- Raw payload rows: 0.
- Matchday endpoint captures: 0.
- Matchday market observations: 0.
- Matchday evidence manifests: 0.
- Recommendations: 0.
- Recommendation locks: 0.

## Consequence

No controlled fixtures or odds canary was legally executed because the credential is missing from the actual worker process. Provider HTTP call count consumed in this diagnosis: 0.

Allsvenskan fixture discovery, odds capture, exact quote identity, crosswalk package, F5/F8 binding, and V3 outcome are therefore blocked upstream.

## Final Status

```text
MATCHDAY_LIVE_INTAKE_REMEDIATION_REQUIRED
FORMAL_DISABLED
LOCK_DISABLED
PRODUCTION_DISABLED
MANUAL_APPROVAL_REQUIRED
EXPERT_REVIEW_REQUIRED
```

Next action is to provide the API-Football credential through the staging env file consumed by compose, restart only worker/scheduler as needed, then rerun the bounded `request_live()` canary.

