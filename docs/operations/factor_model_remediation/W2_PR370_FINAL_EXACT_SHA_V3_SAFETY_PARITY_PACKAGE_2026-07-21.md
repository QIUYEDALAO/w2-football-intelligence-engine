# W2 PR370 Final Exact-SHA V3 Safety Parity Package - 2026-07-21

## Final status

```text
ANALYSIS_RECOMMENDATION_CHAIN_VALIDATED
LIVE_STAGING_EXACT_SHA_DEPLOYED
PUBLIC_HTTP_FROZEN_CANARY_VALIDATED
FORMAL_DISABLED
LOCK_DISABLED
PRODUCTION_DISABLED
MANUAL_APPROVAL_REQUIRED
```

## Exact GitHub and staging identity

```text
PR: #370
Branch: codex/w2-factor-model-remediation-master
Exact SHA: 2a2dd3b704e1207a88dcbec5ed626e2ce002de91
GitHub Actions run: 29823989417
verify: PASS
staging-parity: PASS
predeploy-e2e: PASS
```

Staging deployment:

```text
Host: 118.196.30.136
Current release: /opt/w2/releases/2a2dd3b704e1207a88dcbec5ed626e2ce002de91
api W2_GIT_SHA: 2a2dd3b704e1207a88dcbec5ed626e2ce002de91
/ready: READY
schema: PASS
scheduler: STOPPED
```

## Controlled provider window

Report:

```text
/app/runtime/reports/provider_future_refresh_exact_image_2a2dd3b_20260721T105937Z.json
```

Result:

```text
status: COMPLETED
request_count: 10
remaining_quota: 7183
fixture_count: 14
market_snapshot_count: 8
ledger_appended_count: 2938
raw_payload_written_count: 10
blockers: []
```

Post-window:

```text
W2_PROVIDER_CALLS_DISABLED=true
W2_PROVIDER_SCHEDULER_ENABLED=false
W2_RECOMMENDATION_ENABLED=false
W2_PRODUCTION_RELEASE=false
```

## Frozen materialization

Report:

```text
/opt/w2/shared/runtime/reports/materialize_analysis_card_canary_exact_image_2a2dd3b_after_capture_20260721T110250Z.json
```

Result:

```text
status: MATERIALIZED
requested_fixture_count: 8
materialized_fixture_count: 8
unavailable_fixture_count: 0
schema_versions: w2.analysis-card.frozen.v1
```

The first materialization attempt used an evaluation timestamp two seconds before the provider capture and correctly failed freshness with `CAPTURED_AT_AFTER_EVALUATION`. The accepted materialization uses `2026-07-21T11:00:00Z`, after the fresh quote capture timestamp.

## Service 20-read safety probe

Report:

```text
/opt/w2/shared/runtime/reports/service_frozen_v3_safety_exact_image_2a2dd3b_20read_after_capture_20260721T110326Z.json
```

Result:

```text
zero_write_pass: true
canonical_cohort_hash_unchanged: true
official_storage_hash_unchanged: true
required_tables_present: true
```

## Public HTTP 20-read canary

Report:

```text
/opt/w2/shared/runtime/reports/http_v3_frozen_canary_exact_image_2a2dd3b_20read_20260721T110357Z.json
```

Result:

```text
all_http_200: true
all_frozen_verified: true
all_hash_stable: true
```

Fixture outcomes:

| fixture_id | decision | decision_tier | v3_outcome | reason_code | quote identities | frozen |
| --- | --- | --- | --- | --- | ---: | --- |
| 1494224 | WATCH | WATCH | NO_EDGE | EDGE_INSUFFICIENT | 2 | VERIFIED |
| 1494218 | ANALYSIS_PICK | ANALYSIS_PICK | ANALYSIS_PICK | null | 3 | VERIFIED |
| 1494221 | WATCH | WATCH | NO_EDGE | EDGE_INSUFFICIENT | 2 | VERIFIED |
| 1494223 | ANALYSIS_PICK | ANALYSIS_PICK | ANALYSIS_PICK | null | 3 | VERIFIED |
| 1494217 | ANALYSIS_PICK | ANALYSIS_PICK | ANALYSIS_PICK | null | 3 | VERIFIED |
| 1494222 | ANALYSIS_PICK | ANALYSIS_PICK | ANALYSIS_PICK | null | 3 | VERIFIED |
| 1494219 | WATCH | WATCH | NO_EDGE | EDGE_INSUFFICIENT | 2 | VERIFIED |
| 1494220 | ANALYSIS_PICK | ANALYSIS_PICK | ANALYSIS_PICK | null | 3 | VERIFIED |

Summary:

```text
ANALYSIS_PICK: 5
NO_EDGE: 3
HTTP read count: 20
recommendations/locks/OFFICIAL writes: 0
```

## What remains blocked

No analysis-chain factor remains blocked for this exact-SHA staging canary.

Still not approved or enabled:

```text
Formal AH/OU recommendation
Lock
Production release
Public official recommendation
```

Those require separate human approval and formal gates. This package validates the analysis recommendation chain only.

