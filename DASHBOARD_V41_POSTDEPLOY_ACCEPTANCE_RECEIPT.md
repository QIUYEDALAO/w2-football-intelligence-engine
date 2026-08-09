# Dashboard V4.1 Postdeploy Acceptance Receipt

```text
AUTHORITY = W2_LAST_48H_RECONCILIATION_AND_DASHBOARD_V41_EXECUTION_V1
RESULT = DASHBOARD_V41_POSTDEPLOY_READY_FOR_OWNER_ACCEPTANCE
PR = 506
SOURCE_HEAD_SHA = 05cdc3c1c6dbadbfe20899e941ca404274ff786f
SOURCE_TREE_SHA = 071187ba78381640028efb27b6a1e46c585176d2
FINAL_MAIN_SHA = c6d8c6c7304d302f31bea5a88967e3bc9e945b37
FULL_CI_RUN = 31332734693
PROMOTION_RUN = 31333287529
RELEASE_REQUIRED = PASS
ROUND_4 = NOT_STARTED
ROUND_4_EXECUTION_AUTHORITY = NOT_GRANTED
```

## Release and deployment evidence

| Evidence | Result |
|---|---|
| PR Fast | PASS on exact source head |
| Full CI / `RELEASE_REQUIRED` | PASS, run `31332734693` |
| Main promotion | PASS, run `31333287529` |
| Python image | `sha256:e51b229d7f87169f144d8f56ca655bebf6ef789cc1ed4abf42b7f8d02aae3237` |
| Web image | `sha256:d6f1b67460b91076630881701cab1086181fa1fdca229b7bf102b24b02bbaab5` |
| Transport | Owner local OCI relay primary; both exact digests inspected on VPS |
| Warm switch | PASS in 38 seconds; target 300 seconds |
| Rollback | not required |

The first parallel relay attempt stopped before merge when one SSH transfer timed
out. The exact imported Python digest was verified, the missing Web digest was
relayed sequentially in 51 seconds with `DIGEST_VERIFIED=true`, and only then was
PR #506 merged and the warm switch started. No SSH, Fail2ban, Provider, Scheduler,
cadence, whitelist, model, factor or threshold setting was changed.

## Postdeploy acceptance

```text
WEB_AND_API_EXACT_SOURCE_MATCH = PASS
HEALTH = PASS
READY = PASS_5_CRITICAL_CHECKS
RELEASE_SYNC = PASS
PUBLIC_SCHEMA = w2.dashboard-intelligence-workspace.v1
PUBLIC_AUTHORITY = NEW_INTELLIGENCE_WORKSPACE_ONLY
CURRENT_REAL_DAY_MODE = NORMAL
CURRENT_DEFAULT_FOCUS_TYPE = MATCH
CURRENT_DEFAULT_FOCUS_FIXTURE_ID = 1492329
CURRENT_MATCH_COUNT = 3
CURRENT_ATTENTION_COUNT = 3
ACTIVE_WHITELIST = EXACT_EXISTING_13
FREE_BRIDGE_MODE = SHADOW_ONLY
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
DATA_PROFILE = real-db
DATA_SOURCE = read_model_checkpoint
NO_STAGING_SEED_OR_SYNTHETIC_FALLBACK = PASS
```

The live payload exposed the exact four risk axes and only approved intelligence
states. External intelligence remained `NOT_CONNECTED`. Scoreline remained
fail-closed because no live match proved the READY invariant.

One immediate live endpoint read left this Provider/capture/business vector
unchanged:

```text
685 | 2026-08-09 00:01:19.347942+00 |
532 | 2026-08-09 00:01:19+00 |
82751 | 0 | 63576 | 674 | 2026-08-08 10:31:34.788657+00
```

The same payload reported:

```text
provider_calls = 0
db_writes = 0
would_write_checkpoint = false
no_call_on_read = true
```

## Visual and device evidence

| Viewport | Screenshot SHA-256 | Result |
|---|---|---|
| 1536 x 1024 | `4c901fac1791c6fc6560238c976b9bd0515a42db92047bba0a1120a20aebad47` | PASS |
| 1366 x 768 | `15f761cd2f308d646b0f8d57345e371468dfa511c14464b6d3af66c0640dcfa9` | PASS |

At 1366 x 768 the rendered document measured exactly 1366 CSS pixels wide,
with no horizontal overflow. The current mode/focus was `NORMAL/MATCH`, and no
legacy Boss presentation was present.

## Terminal boundary

```text
NEXT_GATE = OWNER_DASHBOARD_V41_POSTDEPLOY_ACCEPTANCE
NEXT_AUTOMATIC_ACTION = NONE
ROUND_4 = NOT_STARTED
P6 = NOT_AUTHORIZED
```
