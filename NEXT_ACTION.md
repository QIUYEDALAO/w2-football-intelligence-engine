# NEXT ACTION

```text
ACTIVE_NEXT_ACTION = NATURAL_SHADOW_CANDIDATE_EVIDENCE_ACCUMULATION
CURRENT_GATE = EVIDENCE_ACCUMULATION_BEFORE_FORMAL_RECOMMENDATION_APPROVAL
DIRECT_OWNER_APPROVAL = SHADOW_CANDIDATE_AND_POSTMATCH_VALIDATION_LOOP_APPROVED_2026_08_11
PR_517 = MERGED_DEPLOYED
IMPLEMENTATION_HEAD = 58555d2f6bd1e0a069550c91e7ce543164a4819c
FINAL_MAIN = 001b1bae8e5276597dc506e0cd3cb40dbd180fb5
SHADOW_CANDIDATE = ENABLED_SHADOW_ONLY
FORMAL_RECOMMENDATION = OFF_PENDING_SEPARATE_OWNER_APPROVAL
ROUND_4 = NOT_STARTED
ROUND_4_EXECUTION_AUTHORITY = NOT_GRANTED
P6 = NOT_AUTHORIZED
NEXT_AUTOMATIC_ACTION = EXISTING_SCHEDULED_CAPTURE_SETTLEMENT_AND_VALIDATION_ONLY
```

## Authorized operating state

PR #517 is merged, promoted and deployed from the exact Release Candidate source.
SHADOW/CANDIDATE recommendation and the postmatch validation loop are active. Candidate
output remains validation-only and cannot become a formal, locked, production or real-money
recommendation without a later Owner approval.

The existing scheduler naturally runs capture, forward-ledger and result-settlement work. The
dashboard read remains read-only with `provider_calls=0`, `db_writes=0` and
`no_call_on_read=true`. No new Provider call or schedule/cadence change was introduced.

The selected 2026-08-10 day currently has two matches and zero active shadow candidates.
Both matches are truthfully `NOT_READY`; this does not mean the loop is disabled. It means
neither match passed the unchanged existing readiness and selection thresholds.

## Next gate

Continue only the existing natural SHADOW/CANDIDATE evidence accumulation, outcome
settlement and cumulative validation loop. When the repository-defined formal approval
threshold is met with reviewable evidence, prepare and submit a Formal recommendation
approval packet. Do not turn Formal on while preparing or submitting that packet.

## Evidence identity

```text
FULL_CI_RUN = 31412790278
RELEASE_REQUIRED = PASS_EXACT_HEAD
PROMOTION_RUN = 31413410048
PROMOTION_REQUIRED = PASS
HEALTH = PASS
READY = PASS
RELEASE_SYNC = PASS
LOCAL_OCI_RELAY = PASS_DIGEST_VERIFIED
COLD_PULL_END_TO_END = PASS_132_SECONDS
LIVE_VISUAL_QA_SHADOW_CANDIDATE_ENABLED = PASS
LIVE_CURRENT_ACTIVE_SHADOW_CANDIDATES = 0_TRUTHFUL_NOT_READY
NATURAL_FORWARD_LEDGER_TASK = PASS
FORWARD_LEDGER_WRITTEN = 2
FORWARD_LEDGER_SKIPPED_EXISTING = 33
FORWARD_LEDGER_PROVIDER_CALLS = 0
LEDGER_IMPORT_IDENTITY_CONFLICT = NONE
LIVE_BROWSER_CONSOLE_ERRORS = 0
NO_CALL_NO_WRITE = PASS
REPOSITORY_HYGIENE = PASS
```

## Stop

Do not start Formal, Lock, Production, real-money operation, Round4 or P6. Natural execution
of the existing scheduler/cadence is authorized only for SHADOW/CANDIDATE evidence capture,
outcome settlement and postmatch validation. A separate Owner decision is required before
Formal can be enabled.

```text
ROUND_4_START = NOT_AUTHORIZED
P6_EXECUTION = NOT_AUTHORIZED
NEW_PROVIDER_OR_PLAN = NOT_AUTHORIZED
MANUAL_PROVIDER_PROBE = FORBIDDEN
SCHEDULER_OR_CADENCE_CHANGE = NOT_AUTHORIZED
ACTIVE_WHITELIST_CHANGE = NOT_AUTHORIZED
MODEL_FACTOR_THRESHOLD_CHANGE = NOT_AUTHORIZED
MODEL_RETRAINING = NOT_AUTHORIZED
PHASE_0_5_REEXECUTION = FORBIDDEN
CANDIDATE = SHADOW_ONLY_ENABLED
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
READ_PROVIDER_CALLS = 0_REQUIRED
READ_DB_BUSINESS_WRITES = 0_REQUIRED
IMAGE_TRANSPORT = LOCAL_OCI_RELAY_PRIMARY
```
