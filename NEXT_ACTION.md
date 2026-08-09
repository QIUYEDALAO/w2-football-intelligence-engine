# NEXT ACTION

```text
ACTIVE_NEXT_ACTION = EXECUTE_VPS_LOCAL_OCI_RELAY_DEPLOYMENT_AND_POSTDEPLOY_ACCEPTANCE
CURRENT_GATE = VPS_LOCAL_RELAY_DEPLOYMENT_AND_POSTDEPLOY_ACCEPTANCE
AUTHORITY = VPS_LOCAL_OCI_RELAY_DEPLOYMENT_RETRY_AUTHORIZATION.md
SUPERSEDES = VPS_DEPLOYMENT_WARM_RETRY_AUTHORIZATION.md
APPROVED_MAIN_SHA = d61768ecf8457a72df80a5cb0220072de76dfdd4
CURRENT_DEPLOYED_SOURCE_SHA = 51ebbeabc5497ce48708b3587705e2922c4805da
PREVIOUS_RESULT = VPS_DEPLOYMENT_ROLLED_BACK
PREVIOUS_FAILURE = COLD_PULL_END_TO_END_304_SECONDS_EXCEEDED_300_SECOND_TARGET
IMAGE_TRANSPORT = LOCAL_OCI_RELAY_PRIMARY
TRACK_A = WAIT_MORE_NATURAL_EVIDENCE
ROUND_4 = NOT_STARTED
P6 = BLUEPRINT_ONLY_NOT_AUTHORIZED
```

## Binding correction

Do **not** use the VPS as the primary GitHub/GHCR image downloader.

The repository already freezes the intended transport model in `docs/operations/W2_DELIVERY_PIPELINE_LEAD_TIME_RECOVERY.md`:

```text
IMAGE_TRANSPORT = LOCAL_OCI_RELAY_PRIMARY / GHCR_ARCHIVE_AND_FALLBACK
```

The current execution path is therefore:

```text
GitHub/GHCR
-> Owner local computer / Codex local execution host
-> scripts/relay_immutable_images_via_local.sh
-> exact OCI archive
-> SCP
-> VPS SHA-256 verification
-> ctr import
-> docker image inspect exact immutable digest
-> existing deploy_stage7h_staging.sh warm activation
-> postdeploy acceptance
```

The previous warm-retry authority is superseded before execution because it did not make the local-computer relay requirement explicit enough.

## Binding read order

```text
1. CODEX_EXECUTION_PROTOCOL.md
2. CURRENT_STATE.yaml
3. NEXT_ACTION.md
4. VPS_LOCAL_OCI_RELAY_DEPLOYMENT_RETRY_AUTHORIZATION.md
5. VPS_DEPLOYMENT_POSTDEPLOY_ACCEPTANCE_RECEIPT.md
6. docs/operations/W2_DELIVERY_PIPELINE_LEAD_TIME_RECOVERY.md from approved main
7. scripts/relay_immutable_images_via_local.sh from approved main
8. scripts/deploy_stage7h_staging.sh from approved main
9. docs/runbooks/W2_RELEASE_SYNC.md from approved main
10. POST_R3_TRACK_A_NATURAL_EVIDENCE_CLOSURE_REPORT.md
11. POST_R3_TRACK_A_NATURAL_EVIDENCE_CLOSURE_MATRIX.json
12. CODEX_EXECUTION_RECEIPT.md
```

## Execute continuously

1. Fresh-sync exact main/context and verify the accepted Release Candidate manifest and exact Python/Web immutable refs.
2. Reconfirm healthy rollback VPS release, DB backup/rollback safety and runtime stop lines.
3. From the Owner local computer, run the existing `scripts/relay_immutable_images_via_local.sh` for the exact Python and Web refs. Parallel relay is allowed.
4. Require `DIGEST_VERIFIED=true`, matching local/remote archive SHA-256 and exact digest presence on VPS.
5. Do not activate until both immutable images are locally imported on VPS.
6. Run `scripts/deploy_stage7h_staging.sh` unchanged. It must enter `WARM_SWITCH`; if it would enter `COLD_PULL_END_TO_END`, treat that as a relay/cache identity problem rather than falling back to VPS-direct bulk image download.
7. Do not change the existing deployment or rollback timing thresholds.
8. After activation run complete real postdeploy acceptance.
9. If any critical rollout/postdeploy gate fails, automatically roll back and stop; no threshold relaxation, hotfix or runtime-policy change.
10. After deployment PASS only, make one bounded Track A refresh if genuinely new source-bound evidence is readable without manual Provider calls or DB business writes.

## Required deployment acceptance

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

## Terminal classifications

```text
VPS_LOCAL_RELAY_DEPLOYMENT_ACCEPTANCE_PASS
VPS_LOCAL_RELAY_DEPLOYMENT_ROLLED_BACK
POSTDEPLOY_DEFECT_FOUND
LOCAL_RELAY_IDENTITY_BLOCKED
```

If deployment passes while Track A still waits, use:

```text
DEPLOYED_WAITING_FOR_NATURAL_EVIDENCE
```

Overall W2 is not complete until VPS deployment acceptance and Track A `CLOSED_PASS` are both satisfied. Round4 remains `NOT_STARTED`.

## Required outputs

Write only sanitized evidence:

- local-relay/preheat timing and digest-verification evidence;
- `VPS_DEPLOYMENT_POSTDEPLOY_ACCEPTANCE_RECEIPT.md` or a new retry receipt;
- `CODEX_EXECUTION_RECEIPT.md`;
- `CURRENT_STATE.yaml`;
- `NEXT_ACTION.md`;
- Track A report/matrix only if legitimate new source-bound evidence is obtained.

Never commit VPS address/public URL, local SSH identity path, credentials, database identifiers, API keys, secrets or unredacted logs.

## Frozen stop lines

```text
VPS_DIRECT_GHCR_BULK_IMAGE_PULL = FORBIDDEN_AS_PRIMARY_TRANSPORT
IMAGE_TRANSPORT = LOCAL_OCI_RELAY_PRIMARY
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
