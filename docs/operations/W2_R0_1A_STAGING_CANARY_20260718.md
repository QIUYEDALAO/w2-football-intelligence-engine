# W2 R0.1a Staging Canary — 2026-07-18

Result: `BLOCKED_AND_ROLLED_BACK`

## Release under test

- PR: #349.
- Merge SHA: `5849374e61bc7b7fe91b6da41c637b5c65a4b9fb`.
- GitHub run: `29628009629`.
- `verify`, `staging-parity` and `predeploy-e2e`: pass.

## Passing evidence before the hard failure

- `/health`, `/ready`, `/v1/version` and DayView returned 200.
- DayView retained 14 cards, all WATCH/PARTIAL, with ANALYSIS_PICK, RECOMMEND and
  lock eligibility at zero.
- The selected product projection hash was unchanged from the pre-deploy capture:
  `70621303a66cd24908d3d946edc3fc2706f7c0be18e8be6066691af432dab00a`.
- Scheduler was stopped and the Celery queue was empty.
- Provider request count remained 673 throughout acceptance: active acceptance
  provider delta was zero.

## Hard failure

The first public analysis-card identity probe did not return. Docker recorded:

- `oom`;
- `die` with exit code 137;
- two API container restarts.

This confirms the already documented public read-time rebuild boundary. R0.1a did
not change model, feature or fallback behavior, but the approved runtime gate treats
any OOM, exit 137 or restart as a hard failure regardless of attribution.

## Automatic rollback

Staging was rebuilt and restored from the frozen release
`b5cfd6575ba7274692714c9fc814916a00c13e36`.

Post-rollback state:

- API, Web, Worker and Scheduler: same frozen SHA, healthy, restart 0, OOM false.
- Health, weak readiness, version and Web metadata probes: pass.
- Redis Celery queue: 0.
- Provider request count: 673.
- Recommendation, Gate 5, shadow and forward lock rows: 0.
- OFFICIAL and RECOMMEND were not enabled; production was not deployed.

R0.1b must not start until the R0.1a staging exit gate has an approved resolution.
