# VPS Local OCI Relay Deployment Retry Receipt

```text
AUTHORITY = W2_VPS_LOCAL_OCI_RELAY_DEPLOYMENT_RETRY_V1
RESULT = VPS_LOCAL_RELAY_DEPLOYMENT_ACCEPTANCE_PASS
APPROVED_MAIN_SHA = d61768ecf8457a72df80a5cb0220072de76dfdd4
CONTEXT_BASE_SHA = 1ae340d99f14e841d9f6a61b1a0d8b97a2b2c374
PREDEPLOY_SOURCE_SHA = 51ebbeabc5497ce48708b3587705e2922c4805da
FINAL_DEPLOYED_SOURCE_SHA = d61768ecf8457a72df80a5cb0220072de76dfdd4
IMAGE_TRANSPORT = LOCAL_OCI_RELAY_PRIMARY
WARM_SWITCH = PASS_39_SECONDS_LT_300_SECONDS
ROLLBACK = NOT_REQUIRED
POSTDEPLOY_ACCEPTANCE = PASS
```

## Release Candidate identity

| Evidence | Value |
|---|---|
| GitHub run | `31299328162` |
| Full CI / image smoke / `RELEASE_REQUIRED` | `PASS` |
| Immutable manifest SHA-256 | `e56bdef5c3bdcae04ae80f601a3fd845bb5ae407da9fdea56d8f474c6c5ae1e7` |
| Python image digest | `sha256:bafd1c0400e19cb3afd2f2baefc7993b180ff7a482d8ec34b8f89c07f9152143` |
| Web image digest | `sha256:9aecbdbecccf686f6be13c8c255dbcc706d8320a0d915899a4a0b898748e3d96` |

The manifest source tree matches exact `origin/main`. No floating tag or local
rebuild was used.

## Predeploy safety

The measured rollback release was healthy before activation. A new custom-format
database backup was created and `pg_restore --list` passed. The sanitized backup
evidence is 36,093,373 bytes with SHA-256
`3263072e0bb4e3e9138a2a90bf83e6a5db9b049e436c8c4fd97b4bfa4aabf929`.
Rollback images remained present.

Runtime stop lines were unchanged before deployment: API Provider calls and
Scheduler disabled; worker/scheduler use `SHADOW_ONLY`, Scheduler enabled,
daily hard cap 80 and tick hard cap 30; Candidate, Formal and Production off.

## Local OCI relay

The unchanged `scripts/relay_immutable_images_via_local.sh` ran on the Owner
local computer for both exact images.

| Image | GHCR→local | local→VPS | VPS import | Total | Archive bytes | Digest |
|---|---:|---:|---:|---:|---:|---|
| Web | 54s | 21s | 3s | 78s | 21,084,672 | verified |
| Python | 122s | 87s | 4s | 213s | 99,786,240 | verified |

For both images the local and remote archive SHA-256 matched, `ctr import`
succeeded, exact Docker digest inspection passed and the relay emitted
`DIGEST_VERIFIED=true`. The VPS did not perform primary bulk GHCR image transfer.

## Warm activation

The unchanged `scripts/deploy_stage7h_staging.sh` used the already imported
exact images and entered `WARM_SWITCH`. It completed in 39 seconds against the
unchanged 300-second target. No timing threshold, code or runtime policy was
changed.

## Postdeploy acceptance

```text
VPS_SOURCE_SHA_MATCHES_APPROVED_MAIN = PASS
API_HEALTH = PASS
API_READY = PASS_5_CRITICAL_CHECKS
WEB_HEALTH = PASS
WEB_AND_API_RELEASE_IDENTITY_MATCH = PASS
UNIFIED_INTELLIGENCE_WORKSPACE_ENDPOINT = PASS
PUBLIC_SCHEMA = w2.dashboard-intelligence-workspace.v1
PUBLIC_AUTHORITY = NEW_INTELLIGENCE_WORKSPACE_ONLY
ACTIVE_WHITELIST = EXACT_EXISTING_13
FREE_BRIDGE_MODE = SHADOW_ONLY
CANDIDATE_FORMAL_LOCK_PRODUCTION = OFF
DATA_PROFILE = real-db
DATA_SOURCE = read_model_checkpoint
NO_STAGING_SEED_OR_SYNTHETIC_FALLBACK = PASS
NO_LEGACY_PUBLIC_DASHBOARD = PASS
POSTDEPLOY_VISUAL_SMOKE = PASS
```

The live unified read model returned 16 matches and 16 attention rows. Every
match and attention row used one of the exact seven intelligence states and
the exact `EVENT_RISK / DATA_RISK / MODEL_RISK / COLLECTION_RISK` axes. The
Scoreline READY invariant remained fail-closed; there were no READY scorelines
in this live cohort. External intelligence stayed `NOT_CONNECTED` and did not
affect match readiness.

One immediate endpoint read left the complete Provider/capture/business metric
vector unchanged:

```text
685 | 2026-08-09 00:01:19.347942+00 |
532 | 2026-08-09 00:01:19+00 |
138 | 82751 | 674
```

This proves the acceptance read made no Provider call and no business-data
write. The payload itself also reports:

```text
provider_calls = 0
db_writes = 0
would_write_checkpoint = false
no_call_on_read = true
```

All six services were running and healthy at final verification. The exact
runtime controls were independently re-read:

```text
API:       SHADOW_ONLY / provider_calls_disabled=true / scheduler=false /
           daily_cap=120 / tick_cap=30 / candidate=false / formal=false /
           production=false
SCHEDULER: SHADOW_ONLY / provider_calls_disabled=false / scheduler=true /
           future_refresh=false / daily_cap=80 / tick_cap=30 /
           candidate=false / formal=false / production=false
```

## Visual evidence

The new unified workspace passed at the approved desktop and responsive widths.

| Viewport | SHA-256 | Result |
|---|---|---|
| 1536×1024 | `554a56ee5797838e508cc59033f4e72d1f65968e07bd37963f2f8d1c5dc69f7b` | PASS |
| 1366×768 | `10f2204c9eb38140958a7bebbc1acb6156fdeb9c411adfeb7b15112706827163` | PASS |

At 1366 pixels the document and top-bar status areas had no horizontal
overflow. `NEW_INTELLIGENCE_WORKSPACE_ONLY` was present and the old Boss
Decision Console / Recommendation Board were absent.

## Frozen controls

```text
PROVIDER_CALLS_CAUSED_BY_EXECUTION = 0
DB_BUSINESS_WRITES_CAUSED_BY_EXECUTION = 0
PRODUCTION_CODE_CHANGES = 0
SCHEDULER_OR_CADENCE_CHANGED = false
WHITELIST_CHANGED = false
MODEL_OR_THRESHOLD_CHANGED = false
PHASE_0_5_REEXECUTED = false
ROUND_4 = NOT_STARTED
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
P6 = BLUEPRINT_ONLY_NOT_AUTHORIZED
```
