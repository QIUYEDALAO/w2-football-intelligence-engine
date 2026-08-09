# W2 Codex Execution Receipt

```text
AUTHORITY = W2_CODEX_EXECUTION_RECEIPT_LATEST
STATUS = COMPLETE_TERMINAL
EXECUTION_TASK = W2_VPS_DEPLOYMENT_AND_POSTDEPLOY_ACCEPTANCE
TERMINAL_GATE = VPS_DEPLOYMENT_ROLLBACK_TERMINAL
TERMINAL_CLASSIFICATION = VPS_DEPLOYMENT_ROLLED_BACK
EXACT_ORIGIN_MAIN_SHA = d61768ecf8457a72df80a5cb0220072de76dfdd4
EXACT_CONTEXT_BASE_SHA = efdc6f62eb6f0776f3c1a8d91cf95eea24011cc3
TARGET_SOURCE_SHA = d61768ecf8457a72df80a5cb0220072de76dfdd4
PREDEPLOY_SOURCE_SHA = 51ebbeabc5497ce48708b3587705e2922c4805da
FINAL_DEPLOYED_SOURCE_SHA = 51ebbeabc5497ce48708b3587705e2922c4805da
RELEASE_CANDIDATE_RUN = 31299328162
RELEASE_REQUIRED = PASS
PREDEPLOY_BACKUP = PASS
ROLLBACK_AVAILABILITY = PASS
ROLLOUT_GATE = FAIL_COLD_PULL_END_TO_END_304S_GT_300S
ROLLBACK = PASS_33S_LT_120S
POSTDEPLOY_ACCEPTANCE = NOT_RUN_ROLLOUT_GATE_FAILED
CONDITIONAL_TRACK_A_REFRESH = NOT_RUN_DEPLOYMENT_DID_NOT_PASS
TRACK_A = WAIT_MORE_NATURAL_EVIDENCE
PROVIDER_CALLS_FOR_EXECUTION = 0
DB_BUSINESS_WRITES_FOR_EXECUTION = 0
PRODUCTION_CODE_CHANGES = 0
SCHEDULER_OR_CADENCE_CHANGED = false
WHITELIST_CHANGED = false
MODEL_OR_THRESHOLD_CHANGED = false
PHASE_0_5_REEXECUTED = false
ROUND_4_STATUS = NOT_STARTED
CANDIDATE_STATUS = OFF
FORMAL_STATUS = OFF
LOCK_STATUS = OFF
PRODUCTION_STATUS = OFF
P6_STATUS = BLUEPRINT_ONLY_NOT_AUTHORIZED
OVERALL_W2_PROJECT_STATUS = NOT_COMPLETE_VPS_DEPLOYMENT_ROLLED_BACK_TRACK_A_WAITING
REPOSITORY_HYGIENE = PASS
NEXT_GATE = OWNER_DIRECTION_REQUIRED
```

## Result

The exact approved main and context refs were fetched immediately before the
switch and had not moved. Exact-main Full CI, image smoke, `RELEASE_REQUIRED`,
immutable-manifest verification, database backup and rollback availability all
passed.

The existing deployment script pulled the approved digest-bound images, ran its
existing migration step and activated the application services. The immutable
cold-pull end-to-end gate then measured 304 seconds against its frozen
300-second target and failed closed. The script automatically restored the
measured predeploy release in 33 seconds and verified health and digests.

The final API and Web source identity is
`51ebbeabc5497ce48708b3587705e2922c4805da`. All six services are healthy and
the API readiness checks for database, Redis, schema, mounts and artifacts pass.
The Provider/request/capture and business-data baselines were unchanged across
the execution window.

The rollout did not pass, so successful-deployment postdeploy Dashboard/API/
visual acceptance and the conditional source-bound Track A refresh were not
run. No retry or threshold relaxation is authorized.

## Evidence artifacts

```text
DEPLOYMENT_RECEIPT = VPS_DEPLOYMENT_POSTDEPLOY_ACCEPTANCE_RECEIPT.md
TRACK_A_REPORT = POST_R3_TRACK_A_NATURAL_EVIDENCE_CLOSURE_REPORT.md
TRACK_A_MATRIX = POST_R3_TRACK_A_NATURAL_EVIDENCE_CLOSURE_MATRIX.json
ROUND4_PACKET = ABSENT_BY_DESIGN
```

## Repository hygiene and frozen controls

Only `CURRENT_STATE.yaml`, `NEXT_ACTION.md`, this receipt and the new sanitized
deployment receipt changed. No production code, schema, migration, Scheduler,
runtime configuration, test, dependency or product asset changed in Git.

```text
REPOSITORY_HYGIENE = PASS
NEW_DEPENDENCIES = 0
BACKEND_SCHEMA_CHANGE = 0
PROVIDER_CALLS = 0
DB_BUSINESS_WRITES = 0
SCHEDULER_OR_CADENCE_CHANGED = false
ACTIVE_WHITELIST = EXACT_EXISTING_13
MODEL_FACTOR_THRESHOLD_CHANGED = false
PHASE_0_5_REEXECUTED = false
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
P6 = BLUEPRINT_ONLY_NOT_AUTHORIZED
ROUND_4 = NOT_STARTED
```
