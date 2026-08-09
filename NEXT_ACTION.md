# NEXT ACTION

```text
ACTIVE_NEXT_ACTION = EXECUTE_CONTROLLED_VPS_DEPLOYMENT_AND_POSTDEPLOY_ACCEPTANCE
CURRENT_GATE = VPS_DEPLOYMENT_AND_POSTDEPLOY_ACCEPTANCE
AUTHORITY = VPS_DEPLOYMENT_AND_POSTDEPLOY_ACCEPTANCE_AUTHORIZATION.md
APPROVED_MAIN_SHA = d61768ecf8457a72df80a5cb0220072de76dfdd4
MEASURED_PREDEPLOY_SOURCE_SHA = 51ebbeabc5497ce48708b3587705e2922c4805da
DASHBOARD_WORKSTREAM = REPOSITORY_FULLY_CLOSED
TRACK_A = WAIT_MORE_NATURAL_EVIDENCE
ROUND_4 = NOT_STARTED
P6 = BLUEPRINT_ONLY_NOT_AUTHORIZED
```

## Binding read order

```text
1. CODEX_EXECUTION_PROTOCOL.md
2. CURRENT_STATE.yaml
3. NEXT_ACTION.md
4. VPS_DEPLOYMENT_AND_POSTDEPLOY_ACCEPTANCE_AUTHORIZATION.md
5. POST_R3_TRACK_A_NATURAL_EVIDENCE_CLOSURE_REPORT.md
6. POST_R3_TRACK_A_NATURAL_EVIDENCE_CLOSURE_MATRIX.json
7. CODEX_EXECUTION_RECEIPT.md
8. docs/runbooks/W2_RELEASE_SYNC.md from approved main
9. current approved VPS deployment/runbook assets from approved main
```

## Execute continuously

Deploy the exact approved main to the existing VPS using the existing deployment architecture, then perform real postdeploy acceptance. Do not stop for ordinary in-scope deployment mechanics; use existing backup, immutable artifact, warm-switch/restart, health-check and rollback procedures.

Before switching, measure and record the real current deployment, backup the DB according to the existing procedure, record runtime switches/service health and Provider ledger baseline, and prove rollback is available.

After switching, require:

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

No manual Provider probe is allowed. Existing naturally scheduled activity may continue under the frozen runtime policy and must not be confused with acceptance-generated calls.

If a critical postdeploy check fails and cannot be resolved through the existing operational rollout mechanics, automatically roll back to the measured healthy predeploy release and stop. Do not hotfix tracked code or alter runtime policy from this task.

## Conditional Track A refresh

After a successful deploy, use the VPS vantage point for one bounded read-only Track A refresh **only if** the previously missing source-bound fields can now be read with zero manual Provider calls and zero DB business writes:

- checkpoint terminal status/reason;
- scheduler task identity/non-execution reason;
- request-ledger identity and quota state;
- raw payload / endpoint capture identity;
- post-baseline persisted Round-3 reprojection/current timeline and Model Lab/readiness.

If they remain unavailable, keep `WAIT_MORE_NATURAL_EVIDENCE`; do not repeat the same timestamp-only audit. If legitimate evidence is sufficient, update Track A once. Round4 still must remain `NOT_STARTED`.

## Terminal classifications

Deployment terminal:

```text
VPS_DEPLOYMENT_ACCEPTANCE_PASS
VPS_DEPLOYMENT_ROLLED_BACK
POSTDEPLOY_DEFECT_FOUND
```

If deployment passes, overall state is one of:

```text
DEPLOYED_WAITING_FOR_NATURAL_EVIDENCE
DEPLOYED_TRACK_A_CLOSED_PASS
DEPLOYED_RECURRING_INTERNAL_DEFECT_PROVEN
```

Only `VPS_DEPLOYMENT_ACCEPTANCE_PASS + TRACK_A_CLOSED_PASS` can satisfy the remaining overall completion gates. Even then, do not start Round4 automatically.

## Required outputs

Write sanitized evidence to GitHub:

- `VPS_DEPLOYMENT_POSTDEPLOY_ACCEPTANCE_RECEIPT.md`;
- update `CODEX_EXECUTION_RECEIPT.md`;
- update `CURRENT_STATE.yaml`;
- update `NEXT_ACTION.md`;
- update Track A report/matrix only if a legitimate source-bound refresh occurred;
- create/update `ROUND4_READINESS_DECISION_PACKET.md` only if Track A becomes decision-ready.

Never commit VPS address/public URL, secrets, database identifiers, credentials, API keys, or unredacted production logs.

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
