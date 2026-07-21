# W2 PR370 Final Exact-SHA V3 Safety Parity Package

Generated: 2026-07-21

## Scope

This package records the final machine-readable evidence for PR #370 after the
fixture identity stable-field upsert remediation.

It is evidence-only. It does not enable formal recommendations, locks,
production, scheduler, or continuous provider calls.

## Source

```text
machine_json=docs/operations/factor_model_remediation/W2_PR370_FINAL_EXACT_SHA_V3_SAFETY_PARITY_PACKAGE_2026-07-21.json
deployed_implementation_sha=876072e585125644181044ac9789af3f5358458b
deployed_sha_ci_run=29820386907
deployed_sha_ci_conclusion=success
runtime_report=/app/runtime/reports/final_exact_sha_public_read_canary_876072e_AUTO_REFRESH_20260721T100113Z.json
provider_refresh_report=/app/runtime/reports/provider_future_refresh_exact_image_876072e_20260721T100035Z.json
```

## Deployment Evidence

```text
/opt/w2/current=876072e585125644181044ac9789af3f5358458b
api_git_sha=876072e585125644181044ac9789af3f5358458b
web_git_sha=876072e585125644181044ac9789af3f5358458b
/ready=READY
api=healthy
worker=healthy
web=healthy
scheduler=exited
```

## Automatic Refresh

```text
status=COMPLETED
request_count=10
remaining_quota=7212
fixture_count=14
market_snapshot_count=8
ledger_appended_count=2938
blockers=[]
```

This closes the prior `AUTOMATED_FUTURE_REFRESH_DEGRADED` blocker for the
bounded Allsvenskan canary path.

## Public Read Canary

```text
fixtures=8
public_read_iterations=20
ANALYSIS_PICK=5
WATCH=3
zero_write_pass=true
recommendation_lock_official_delta_zero=true
```

Per-fixture result:

```text
1494224 WATCH
1494218 ANALYSIS_PICK
1494221 WATCH
1494223 ANALYSIS_PICK
1494217 ANALYSIS_PICK
1494222 ANALYSIS_PICK
1494219 WATCH
1494220 ANALYSIS_PICK
```

All 8 fixtures include AH and OU model probability, market probability,
probability delta, EV and uncertainty fields in the JSON package.

## Safety

```text
recommendations count_delta=0
recommendation_locks count_delta=0
forward_prediction_lock count_delta=0
gate5_recommendation_lock_event count_delta=0
shadow_strategy_event count_delta=0
shadow_strategy_lock count_delta=0
shadow_strategy_settlement count_delta=0
settlements count_delta=0
```

Provider calls were explicitly reopened only for the bounded refresh execution
and the deployed runtime flags remain:

```text
W2_PROVIDER_CALLS_DISABLED=true
W2_PROVIDER_SCHEDULER_ENABLED=false
W2_RECOMMENDATION_ENABLED=false
W2_PRODUCTION_RELEASE=false
```

## Status

```text
ANALYSIS_RECOMMENDATION_CHAIN_VALIDATED
LIVE_STAGING_CANARY_PASSED
ANALYSIS_RECOMMENDATION_FACTORS_READY
AS_OF_REPLAY_GUARD_PASS
AUTOMATED_FUTURE_REFRESH_COMPLETED_FOR_CANARY
FINAL_MACHINE_READABLE_V3_SAFETY_PARITY_PACKAGE_SUBMITTED
FORMAL_DISABLED
LOCK_DISABLED
PRODUCTION_DISABLED
MANUAL_APPROVAL_REQUIRED
```
