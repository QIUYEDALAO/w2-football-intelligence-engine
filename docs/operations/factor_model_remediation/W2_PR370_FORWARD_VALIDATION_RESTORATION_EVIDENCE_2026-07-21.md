# W2 PR370 Forward Validation Restoration Evidence

Generated at `2026-07-21T12:18:00Z`.

## Scope

This follow-up restores real forward validation capture visibility after the analysis recommendation chain had already passed.

This did not change model factors, model weights, thresholds, or quote freshness. It did not enable formal recommendations, locks, production, continuous provider refresh, or the scheduler.

## GitHub and Staging

```text
PR: #370
PR state: Draft
PR head: d2a7980ab5c2a6665b5dee6411a66733aacf0a7f
GitHub Actions run: 29828967011
GitHub Actions: verify=SUCCESS, staging-parity=SUCCESS, predeploy-e2e=SUCCESS
Deployed staging release: /opt/w2/releases/d2a7980ab5c2a6665b5dee6411a66733aacf0a7f
API SHA: d2a7980ab5c2a6665b5dee6411a66733aacf0a7f
/ready: READY
schema: PASS
api/worker/web: healthy
scheduler: stopped
```

Runtime controls remained closed:

```text
W2_PROVIDER_CALLS_DISABLED=true
W2_PROVIDER_SCHEDULER_ENABLED=false
W2_RECOMMENDATION_ENABLED=false
W2_PRODUCTION_RELEASE=false
```

## Ledger Files

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

Performance report:

```text
/opt/w2/shared/runtime/reports/forward_ledger_performance_final_d2a7980.json
sha256=8c924f6d12ad2a8fd1c9417631cbb6b9d86fa71c20ff96a4e6eb784eed9c8004
```

## Forward Validation Counts

```text
validation_fixture_count=5
performance_cohort.validation_count=5
performance_cohort.pending_count=5
performance_cohort.eligible_count=0
validation_settled_fixture_count=0
validation_excluded_count=0
integrity_status=PASS
league=Allsvenskan
```

No HIT/MISS/PUSH/VOID outcome was fabricated. These five fixtures remain pending until real final-time result evidence exists.

## Pending Capture Identities

```text
fixture_id=1494217
capture_identity_hash=9223390bdefc1dce5c07ceeee7651c9c13cb421860d116b002c4ff81d328fd1a
card_hash=f319e0cafaebd09a376a876d6c022381a9fe920a1cac6fe5033c31096534f09a
decision_hash=10ad2a21e36089dc9dc1310e7ebb45c926ff03ddb0e4db5a491621fca99c8778

fixture_id=1494218
capture_identity_hash=8aab83ce0fab976e2e4ce4538dacf78db87b3185bd97ee9ccd53fcf2eb05149f
card_hash=d29334506a354e5def714a9c80098dc187851cbc31998b244bff78dedcbee131
decision_hash=eaa60bffa67ce461972019c335b6070e1acf48624995c7599b8a805e7641efa2

fixture_id=1494220
capture_identity_hash=6184ada7506a594590ccd26177ad3d82ab6dbea7e19570e6daec6da095a3f1f8
card_hash=77be8fd751e2a011ed29e5968e1171f2607da946c3ff8f995ebf08d7f8abda4e
decision_hash=667cc6cf719c4a86b837df5f7cb31685eb7f0cc52d497a0197382b6d64cd5e8b

fixture_id=1494222
capture_identity_hash=3aa4fd315f4cea1783c590b16639861b32fc58a9d0ccf043e4d94e3fb5d5714e
card_hash=4279940fdb3535a7be4524cee354da5534978fe5585aab6ece374dd5a06a139e
decision_hash=f4f8edbfc9231aee1dcaff7d34d70c49c54e8c5e8697e2fa8f651698a5bee1a5

fixture_id=1494223
capture_identity_hash=2c10701d0a3190c47dfaf45a6bb860fd3c48a45113a34ea010325268edd4a85a
card_hash=cd343fccb0af143d6e43e81a8321b7e61307c4252e098a0bec6231e0140d7ddd
decision_hash=c2f681913fd31363bd36e37db92cfd8a5f66bfd127759e31d8f457e4fb09e175
```

## Dashboard Evidence

Live URL:

```text
http://118.196.30.136/
```

Screenshot:

```text
/tmp/w2_forward_validation_d2a7980.png
sha256=888e7a6df192ed3fd8ea8cb042a41cc01b10243d2481e9b55c05abe2a53acd3a
```

Observed UI text:

```text
已出推荐 5
验证推荐 5 场
纳入统计 0 · 待处理 5
验证 ledger 已记录
验证推荐已写入 ledger，当前待结算 5 场
```

## Safety

```text
recommendations_delta=0
locks_delta=0
OFFICIAL_delta=0
formal_settlements_delta=0
```

Final state:

```text
REAL_FORWARD_VALIDATION_CAPTURE_RESTORED
REAL_POST_MATCH_SETTLEMENT_NOT_DUE
FORMAL_DISABLED
LOCK_DISABLED
PRODUCTION_DISABLED
MANUAL_APPROVAL_REQUIRED
```
