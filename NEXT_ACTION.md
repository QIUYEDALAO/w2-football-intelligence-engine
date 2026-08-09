# NEXT ACTION

```text
ACTIVE_NEXT_ACTION = EXECUTE_VPS_WARM_SWITCH_RETRY_AND_POSTDEPLOY_ACCEPTANCE
CURRENT_GATE = VPS_WARM_RETRY_AND_POSTDEPLOY_ACCEPTANCE
AUTHORITY = VPS_DEPLOYMENT_WARM_RETRY_AUTHORIZATION.md
APPROVED_MAIN_SHA = d61768ecf8457a72df80a5cb0220072de76dfdd4
CURRENT_DEPLOYED_SOURCE_SHA = 51ebbeabc5497ce48708b3587705e2922c4805da
PREVIOUS_RESULT = VPS_DEPLOYMENT_ROLLED_BACK
PREVIOUS_FAILURE = COLD_PULL_END_TO_END_304_SECONDS_EXCEEDED_300_SECOND_TARGET
TRACK_A = WAIT_MORE_NATURAL_EVIDENCE
ROUND_4 = NOT_STARTED
P6 = BLUEPRINT_ONLY_NOT_AUTHORIZED
```

## Why retry is authorized

The first deployment attempt did not expose an application-health, release-identity, migration, schema, Provider, Scheduler, or Dashboard defect. The exact approved immutable images were pulled and verified, but the cold-pull end-to-end path completed in 304 seconds against the unchanged 300-second target, so the existing fail-closed mechanism rolled back safely in 33 seconds.

The existing deployment script already has a warm-switch path when both exact target image digests are present locally. This retry therefore does not change deployment code or relax any threshold.

## Binding read order

```text
1. CODEX_EXECUTION_PROTOCOL.md
2. CURRENT_STATE.yaml
3. NEXT_ACTION.md
4. VPS_DEPLOYMENT_WARM_RETRY_AUTHORIZATION.md
5. VPS_DEPLOYMENT_POSTDEPLOY_ACCEPTANCE_RECEIPT.md
6. VPS_DEPLOYMENT_AND_POSTDEPLOY_ACCEPTANCE_AUTHORIZATION.md
7. POST_R3_TRACK_A_NATURAL_EVIDENCE_CLOSURE_REPORT.md
8. POST_R3_TRACK_A_NATURAL_EVIDENCE_CLOSURE_MATRIX.json
9. CODEX_EXECUTION_RECEIPT.md
10. docs/runbooks/W2_RELEASE_SYNC.md from approved main
11. existing VPS deployment/runbook assets from approved main
```

## Execute continuously

Reconfirm the healthy rollback release, immutable target identities, DB backup/rollback safety and target image cache. If a target image is not locally present, pre-cache only that exact approved immutable digest without activating services or changing runtime policy. Prove both target images are local, then execute the repository's existing deployment script unchanged.

The activation must enter the script's existing `WARM_SWITCH` timing scope. Do not relax the all-service 300-second target or rollback 120-second target.

After activation require the complete real postdeploy acceptance:

```text
VPS_SOURCE_SHA_MATCHES_APPROVED_MAIN
API_HEALTH_PASS
API_READY_PASS
WEB_HEALTH_PASS
WEB_AND_API_RELEASE_IDENTITY_MATCH
GET_/v1/dashboard/intelligence-workspace_PASS
PUBLIC_SCHEMA_W2_DASHBOARD_INTELLIGENCE_WORKSPACE_V1
PUBLIC_AUTHORITY_NEW_INTELLIGENCE_WORKSPACE_ONLY
READ_PROVIDER_CALLS_0
READ_DB_WRITES_0
NO_CALL_ON_READ_TRUE
13_LEAGUES
SHADOW_ONLY
CANDIDATE_FORMAL_LOCK_PRODUCTION_OFF
REAL_DATA_OR_EXPLICIT_REAL_EMPTY_STATE
NO_STAGING_SEED_OR_SYNTHETIC_FALLBACK
NO_LEGACY_PUBLIC_DASHBOARD
SCHEDULER_PROVIDER_POLICY_UNCHANGED
POSTDEPLOY_VISUAL_SMOKE_PASS
```

No manual Provider probe is allowed. Existing naturally scheduled activity may continue under the frozen runtime policy and must be separated from acceptance-generated activity.

## Conditional Track A refresh

Only after successful deployment, perform one bounded read-only Track A refresh if the VPS vantage point exposes the previously missing source-bound terminal fields with zero manual Provider calls and zero DB business writes. If they remain unavailable, retain `WAIT_MORE_NATURAL_EVIDENCE` and do not repeat a timestamp-only audit.

Round4 remains `NOT_STARTED` regardless of this retry.

## Failure handling

If the warm retry fails any critical rollout or postdeploy gate, automatically roll back to the measured healthy predeploy release and stop. Do not retry a third time automatically, do not change timing thresholds, do not hotfix tracked code, and do not change Provider/Scheduler/model/runtime policy.

## Terminal classifications

```text
VPS_WARM_RETRY_ACCEPTANCE_PASS
VPS_WARM_RETRY_ROLLED_BACK
POSTDEPLOY_DEFECT_FOUND
```

If deployment passes while Track A still waits, use `DEPLOYED_WAITING_FOR_NATURAL_EVIDENCE`. Do not declare overall W2 complete until both VPS deployment acceptance and Track A closed-pass requirements are satisfied.

## Required outputs

Update sanitized GitHub evidence:

- `VPS_DEPLOYMENT_POSTDEPLOY_ACCEPTANCE_RECEIPT.md` or a new warm-retry receipt;
- `CODEX_EXECUTION_RECEIPT.md`;
- `CURRENT_STATE.yaml`;
- `NEXT_ACTION.md`;
- Track A report/matrix only if legitimate new source-bound evidence is obtained.

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
