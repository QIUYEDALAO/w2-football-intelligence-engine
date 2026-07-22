# W2 Historical Settled Validation Visibility Audit

Generated at `2026-07-21T12:31:00Z`.

## Question

The user reports that more than ten historical recommendations had already completed post-match validation and asks whether those records disappeared again.

## Current New Staging Server

```text
host=118.196.30.136
current_release=/opt/w2/releases/d2a7980ab5c2a6665b5dee6411a66733aacf0a7f
api_sha=d2a7980ab5c2a6665b5dee6411a66733aacf0a7f
/ready=READY
schema=PASS
```

Current shared forward ledger files:

```text
/opt/w2/shared/runtime/forward_outcome_ledger/2026-07-21_staging.jsonl
lines=40
sha256=5f11c038a4e83f404797525e0f4a5545dee4f6ba76a1dd761980731ca2087ef2

/opt/w2/shared/runtime/forward_outcome_ledger/2026-07-21-validation-correction_staging.jsonl
lines=8
sha256=0edf97d609445fb81eacd7b198a0b815531f88660baa06d4321aec578b6e576b

/opt/w2/shared/runtime/forward_outcome_ledger/2026-07-21-validation-correction-v2_staging.jsonl
lines=8
sha256=b397156f0cd2b33fbce0911495ab2f683812556bb3aaeddbc76b44c0d61d5afd
```

Current API performance view:

```text
analysis_pick_count=5
forward_ledger.validation_fixture_count=5
forward_ledger.performance_cohort.validation_count=5
forward_ledger.performance_cohort.pending_count=5
forward_ledger.performance_cohort.eligible_count=0
forward_ledger.validation_settled_fixture_count=0
dashboard_card_validation_rows=0
```

Current PostgreSQL table counts:

```text
recommendations=0
recommendation_locks=0
settlements=0
forward_prediction_lock=0
gate5_recommendation_lock_event=0
shadow_strategy_lock=0
shadow_strategy_settlement=0
```

## Old Runtime File Found on New Server Releases

A previous release directory contains:

```text
/opt/w2/releases/037b88cd529e4c19ecf7ddc51f50106a6a996572/runtime/forward_outcome_ledger/2026-07-20_staging.jsonl
bytes=181592
lines=80
sha256=aa07c79aafe67a088765e43b5b64685b2f83fd238b197a08fea308428dd1bd46
```

This file is not a settled-validation ledger:

```text
record_type.CAPTURE=80
recommendation_scope.NONE=80
settlements={}
leagues: Serie A=34, Eliteserien=16, Allsvenskan=14, Super League=16
```

It therefore does not account for the reported more-than-ten completed post-match validation records.

## Old Server Access

Repository documentation identifies a prior staging/single-machine production host:

```text
43.155.208.138
```

Read-only SSH attempts failed with the available keys:

```text
ssh ubuntu@43.155.208.138 -i /Users/liudehua/Downloads/huoshanyun.pem
Permission denied (publickey)

ssh root@43.155.208.138 -i /Users/liudehua/Downloads/huoshanyun.pem
Permission denied (publickey)

ssh ubuntu@43.155.208.138 -i /Users/liudehua/.ssh/id_ed25519_btc_eth_quant_vps
Permission denied (publickey)
```

## Interim Finding

The historical completed validation records are not visible in the current new server's shared runtime, public dashboard payload, or PostgreSQL tables.

This audit does not prove those records were deleted. The stronger current conclusion is:

```text
HISTORICAL_SETTLED_VALIDATION_NOT_PRESENT_ON_NEW_STAGING
OLD_SETTLED_VALIDATION_SOURCE_NOT_YET_LOCATED
LIKELY_NOT_MIGRATED_OR_STORED_ON_OLD_HOST_OR_BACKUP
```

The latest forward validation repair did not delete the reported historical rows because the new server's before/after evidence already showed no settled validation rows in the shared forward ledger or DB.

## Required Recovery Step

To recover the reported historical settled validation, locate one of:

```text
1. SSH access to old host 43.155.208.138 with the correct key/user.
2. A filesystem backup of /opt/w2/shared/runtime from the old host.
3. A PostgreSQL dump from the old host.
4. A prior dashboard/export artifact containing card.validation rows with HIT/MISS/PUSH/VOID.
```

After locating the source, recover append-only into a separate legacy import artifact or reviewed migration path. Do not fabricate settled outcomes and do not merge incompatible cohorts into the new five pending validation samples.
