# W2 VPS Deployment Warm-Switch Retry Authorization

```text
AUTHORITY = W2_VPS_DEPLOYMENT_WARM_RETRY_V1
OWNER_DECISION = AUTO_APPROVED_BOUNDED_OPERATIONAL_RETRY
TARGET_MAIN_SHA = d61768ecf8457a72df80a5cb0220072de76dfdd4
PREVIOUS_DEPLOYMENT_RESULT = VPS_DEPLOYMENT_ROLLED_BACK
PREVIOUS_ROLLBACK_SOURCE_SHA = 51ebbeabc5497ce48708b3587705e2922c4805da
PREVIOUS_FAILURE = COLD_PULL_END_TO_END_304_SECONDS_EXCEEDED_300_SECOND_TARGET
TRACK_A = WAIT_MORE_NATURAL_EVIDENCE
ROUND_4 = NOT_STARTED
```

## Decision

The previous deployment did not fail application health, release identity, migration, API/Web compatibility, Provider safety, or rollback safety. It failed only the existing cold-pull end-to-end timing gate by 4 seconds after the exact immutable target images had been pulled and verified. Rollback completed successfully and restored the prior healthy release.

Authorize one bounded retry using the repository's existing deployment architecture without changing any timing threshold or tracked production code.

## Required retry sequence

1. Fresh-sync exact `origin/main` and `origin/context/current`.
2. Reconfirm Release Candidate / immutable manifest for target main remains accepted.
3. Measure the current healthy rollback release and preserve the existing DB backup/rollback safety procedure.
4. Verify whether both exact target Python and Web immutable image digests are already present locally on the VPS.
5. If either target digest is absent, pre-cache only the exact approved immutable digest without activating any service or changing release/env/runtime policy.
6. Prove both target digests are locally present before activation.
7. Run the existing deployment script unchanged. The script must classify the activation as `WARM_SWITCH` (or equivalent existing warm mode), not a new custom rollout path.
8. Do not relax the existing 300-second all-service target, 120-second rollback target, or any health/readiness gate.
9. On successful activation, execute full postdeploy acceptance from the prior authorization, including exact source/release identity, API/Web health, unified intelligence-workspace endpoint, real-data/explicit-empty semantics, no-call-on-read, exact 13 leagues, SHADOW_ONLY and OFF switches, and visual smoke.
10. Run one bounded Track A source-bound refresh only if the missing persisted terminal evidence is actually available from the VPS vantage point with zero manual Provider calls and zero DB business writes. Otherwise retain `WAIT_MORE_NATURAL_EVIDENCE`.

## Failure handling

If the warm retry fails a critical deployment or postdeploy gate, automatically roll back to the measured healthy predeploy release and stop with evidence. Do not retry again automatically, do not alter timing thresholds, do not hotfix tracked code, and do not change runtime policy.

## Terminal classifications

```text
VPS_WARM_RETRY_ACCEPTANCE_PASS
VPS_WARM_RETRY_ROLLED_BACK
POSTDEPLOY_DEFECT_FOUND
```

If deployment passes while Track A still waits, overall state is `DEPLOYED_WAITING_FOR_NATURAL_EVIDENCE`; do not falsely declare overall W2 complete.

## Frozen stop lines

```text
NEW_PROVIDER_OR_PLAN = NOT_AUTHORIZED
MANUAL_PROVIDER_PROBE = FORBIDDEN
SCHEDULER_OR_CADENCE_CHANGE = NOT_AUTHORIZED
ACTIVE_WHITELIST_CHANGE = NOT_AUTHORIZED
MODEL_FACTOR_THRESHOLD_CHANGE = NOT_AUTHORIZED
EXTERNAL_INTELLIGENCE_CONNECTION = NOT_AUTHORIZED
PHASE_0_5_REEXECUTION = FORBIDDEN
H_RESULT_ACCESS = PERMANENTLY_CLOSED
ROUND_4_START = NOT_AUTHORIZED
P6_EXECUTION = NOT_AUTHORIZED
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
REAL_MONEY = NOT_AUTHORIZED
TRACKED_CODE_HOTFIX = NOT_AUTHORIZED
DEPLOYMENT_TIMING_THRESHOLD_CHANGE = NOT_AUTHORIZED
```
