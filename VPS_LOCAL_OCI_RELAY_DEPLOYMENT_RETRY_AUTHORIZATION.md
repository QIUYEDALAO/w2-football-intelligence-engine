# VPS Local OCI Relay Deployment Retry Authorization

```text
AUTHORITY = W2_VPS_LOCAL_OCI_RELAY_DEPLOYMENT_RETRY_V1
OWNER_DATE = 2026-08-09
OWNER_DECISION = AUTHORIZED
SUPERSEDES = VPS_DEPLOYMENT_WARM_RETRY_AUTHORIZATION.md
APPROVED_MAIN_SHA = d61768ecf8457a72df80a5cb0220072de76dfdd4
CURRENT_DEPLOYED_SOURCE_SHA = 51ebbeabc5497ce48708b3587705e2922c4805da
PREVIOUS_DEPLOYMENT_RESULT = VPS_DEPLOYMENT_ROLLED_BACK
PREVIOUS_FAILURE = COLD_PULL_END_TO_END_304_SECONDS_EXCEEDED_300_SECOND_TARGET
IMAGE_TRANSPORT = LOCAL_OCI_RELAY_PRIMARY
ROUND_4 = NOT_STARTED
P6 = BLUEPRINT_ONLY_NOT_AUTHORIZED
```

## Correction and binding transport decision

The previous warm-retry authorization was ambiguous about where immutable image preheat occurs. It is superseded by this authority.

The repository already freezes the intended delivery model in `docs/operations/W2_DELIVERY_PIPELINE_LEAD_TIME_RECOVERY.md`:

```text
IMAGE_TRANSPORT = LOCAL_OCI_RELAY_PRIMARY / GHCR_ARCHIVE_AND_FALLBACK
```

For this deployment, bulk immutable image transport MUST be:

```text
GitHub/GHCR
-> Owner local computer / Codex local execution host
-> exact OCI archive
-> SCP over the existing SSH path
-> VPS
-> SHA-256 verify
-> ctr import
-> docker image inspect exact immutable digest
-> existing deployment script warm activation
```

Do not use the VPS as the primary GHCR image downloader. In particular, do not intentionally perform another VPS cold image-layer pull from GHCR.

Registry metadata checks that the unchanged deployment script may perform after the exact digest is already imported are not a new transport path, but the activation must not require cold layer transfer from GHCR.

## Required existing implementation

Use the repository's existing script unchanged:

```text
scripts/relay_immutable_images_via_local.sh
```

It must run from the Owner local computer / Codex local execution host and use the exact immutable Python and Web image refs from the accepted Release Candidate manifest for approved main.

For each image the existing script must provide evidence of:

```text
LOCAL_GHCR_PULL
OCI_ARCHIVE_CREATED
LOCAL_ARCHIVE_SHA256
LOCAL_TO_VPS_SCP
REMOTE_ARCHIVE_SHA256_MATCH
VPS_CTR_IMPORT
VPS_DOCKER_IMAGE_INSPECT_EXACT_DIGEST
DIGEST_VERIFIED=true
```

Python and Web relays may run in parallel, matching the existing delivery pipeline behavior.

Never use floating tags or rebuild images locally. The local computer is a transport relay only; source and image identity remain the accepted GitHub Release Candidate immutable digests.

## Why this is the correct existing path

The accepted delivery-pipeline evidence records that a cold VPS GHCR pull previously took 1,920 seconds, while the local OCI relay reduced immutable-image preheat to 295 seconds and the warm service switch to 9 seconds. The previous 304-second rollback therefore must not be addressed by relaxing the rollout SLO or by repeating VPS-direct cold transfer.

## Continuous execution sequence

1. Fresh-sync `origin/main` and `origin/context/current` and confirm this authority is current.
2. Confirm approved main is exactly `d61768ecf8457a72df80a5cb0220072de76dfdd4`.
3. Read/verify the accepted immutable Release Candidate manifest and exact Python/Web image refs. Do not infer refs from tags.
4. Reconfirm current healthy rollback release on VPS and its exact source SHA.
5. Reconfirm DB backup/rollback safety and record sanitized predeploy runtime state.
6. From the Owner local computer, run `scripts/relay_immutable_images_via_local.sh` for the exact Python and Web immutable refs.
7. Require digest verification and exact-image presence on VPS before activation. If relay/import identity fails, do not activate.
8. Run the repository's existing `scripts/deploy_stage7h_staging.sh` unchanged with the exact refs.
9. Require the deploy script to enter `WARM_SWITCH`, not `COLD_PULL_END_TO_END`. If it would enter cold-pull mode, stop before accepting activation and diagnose missing relay/cache identity; do not fall back to VPS-direct bulk pull.
10. Preserve the existing deployment and rollback timing thresholds unchanged.
11. After activation, execute full postdeploy acceptance.
12. If a critical rollout/postdeploy gate fails, automatically roll back to the measured healthy release and stop. No threshold relaxation, no tracked-code hotfix, no runtime-policy change.
13. Only after deployment PASS, perform one bounded Track A refresh if the VPS vantage point exposes genuinely new source-bound evidence with zero manual Provider calls and zero DB business writes.

Do not stop for ordinary local relay mechanics; resolve in-scope transfer/import issues and continue. Stop only on a terminal classification or a frozen stop-line conflict.

## Mandatory postdeploy acceptance

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

Naturally scheduled activity may continue under the frozen runtime policy and must be separated from acceptance-generated activity. No manual Provider probe is allowed.

## Conditional Track A refresh

Track A currently remains `WAIT_MORE_NATURAL_EVIDENCE`.

After successful deployment only, make one bounded read-only refresh if the VPS can expose the previously missing source-bound terminal fields without Provider calls or business writes. If those fields remain unavailable, keep `WAIT_MORE_NATURAL_EVIDENCE` and do not repeat the timestamp-only audit.

Round4 remains `NOT_STARTED` regardless of deployment result.

## Terminal classifications

```text
VPS_LOCAL_RELAY_DEPLOYMENT_ACCEPTANCE_PASS
VPS_LOCAL_RELAY_DEPLOYMENT_ROLLED_BACK
POSTDEPLOY_DEFECT_FOUND
LOCAL_RELAY_IDENTITY_BLOCKED
```

If deployment passes while Track A still waits, overall status is:

```text
DEPLOYED_WAITING_FOR_NATURAL_EVIDENCE
```

Do not declare overall W2 complete until both VPS deployment acceptance and Track A `CLOSED_PASS` requirements are satisfied.

## Required sanitized outputs

- update `VPS_DEPLOYMENT_POSTDEPLOY_ACCEPTANCE_RECEIPT.md` or create a local-relay retry receipt;
- update `CODEX_EXECUTION_RECEIPT.md`;
- update `CURRENT_STATE.yaml`;
- update `NEXT_ACTION.md`;
- update Track A report/matrix only if genuinely new source-bound evidence is obtained.

Do not commit VPS address/public URL, SSH identity path, credentials, database identifiers, API keys, secrets, or unredacted production logs.

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
