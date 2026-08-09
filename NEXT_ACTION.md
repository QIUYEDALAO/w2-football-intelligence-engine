# NEXT ACTION

```text
ACTIVE_NEXT_ACTION = STOP_VPS_DEPLOYMENT_ROLLED_BACK_AWAIT_OWNER_DIRECTION
CURRENT_GATE = VPS_DEPLOYMENT_ROLLBACK_TERMINAL
AUTHORITY = VPS_DEPLOYMENT_AND_POSTDEPLOY_ACCEPTANCE_AUTHORIZATION.md
TERMINAL_CLASSIFICATION = VPS_DEPLOYMENT_ROLLED_BACK
APPROVED_MAIN_SHA = d61768ecf8457a72df80a5cb0220072de76dfdd4
FINAL_DEPLOYED_SOURCE_SHA = 51ebbeabc5497ce48708b3587705e2922c4805da
DEPLOYMENT_RECEIPT = VPS_DEPLOYMENT_POSTDEPLOY_ACCEPTANCE_RECEIPT.md
TRACK_A = WAIT_MORE_NATURAL_EVIDENCE
ROUND_4 = NOT_STARTED
P6 = BLUEPRINT_ONLY_NOT_AUTHORIZED
```

## Terminal result

The unique authorized task reached `VPS_DEPLOYMENT_ROLLED_BACK`.

The exact-main Release Candidate and immutable artifacts passed, the predeploy
database backup and rollback checks passed, and the existing deployment path was
used. After activation, the frozen cold-pull end-to-end gate measured 304
seconds against its 300-second target. The deployment failed closed and restored
the measured predeploy release in 33 seconds. Rollback health, readiness,
release identity and digest checks passed.

Provider request/capture and business-data evidence was unchanged across the
window. No manual Provider probe, tracked-code hotfix, runtime policy edit or
automatic retry occurred.

## Stop here

Do not retry deployment under the completed authorization. Do not relax the
300-second gate and do not enter postdeploy acceptance from this rolled-back
state. A new Owner decision is required before another deployment attempt or any
change to rollout mechanics/targets.

The conditional Track A refresh was not run because deployment did not pass.
Track A therefore remains `WAIT_MORE_NATURAL_EVIDENCE`; do not repeat the same
timestamp-only audit.

## Binding read order for any future continuation

```text
1. CODEX_EXECUTION_PROTOCOL.md
2. CURRENT_STATE.yaml
3. NEXT_ACTION.md
4. VPS_DEPLOYMENT_POSTDEPLOY_ACCEPTANCE_RECEIPT.md
5. VPS_DEPLOYMENT_AND_POSTDEPLOY_ACCEPTANCE_AUTHORIZATION.md
6. POST_R3_TRACK_A_NATURAL_EVIDENCE_CLOSURE_REPORT.md
7. POST_R3_TRACK_A_NATURAL_EVIDENCE_CLOSURE_MATRIX.json
8. CODEX_EXECUTION_RECEIPT.md
```

## Frozen stop lines

```text
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
```
