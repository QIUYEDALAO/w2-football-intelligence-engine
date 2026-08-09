# W2 VPS Deployment and Postdeploy Acceptance Authorization

```text
AUTHORITY = W2_VPS_DEPLOYMENT_POSTDEPLOY_ACCEPTANCE_V1
OWNER_DATE = 2026-08-09
REPOSITORY = QIUYEDALAO/w2-football-intelligence-engine
APPROVED_MAIN_SHA = d61768ecf8457a72df80a5cb0220072de76dfdd4
CURRENT_DEPLOYED_SOURCE_SHA = 51ebbeabc5497ce48708b3587705e2922c4805da
TRACK_A_STATUS = WAIT_MORE_NATURAL_EVIDENCE
DASHBOARD_WORKSTREAM = REPOSITORY_FULLY_CLOSED
ROUND_4 = NOT_STARTED
P6 = NOT_AUTHORIZED
```

## Decision

The Dashboard code line is complete, but overall W2 delivery is not complete because the VPS still runs an older source SHA. This authority starts the remaining mandatory delivery gate now instead of idling while Track A waits for naturally persisted evidence.

Execute one continuous operational task:

```text
CONTROLLED_VPS_DEPLOYMENT
-> POSTDEPLOY_REAL_ACCEPTANCE
-> CONDITIONAL_SOURCE_BOUND_TRACK_A_REFRESH
-> STOP
```

No intermediate Owner relay is required for ordinary in-scope deployment issues. Deployment does not authorize new product semantics or runtime-policy changes.

## Existing deployment path only

Reuse the repository's existing approved VPS/release mechanisms and operator configuration. Do not invent a second deployment architecture. Existing runbooks/receipts are evidence for backup, immutable-image/release identity, rollback, health, release-sync, and sanitized receipts.

Do not commit resolved VPS addresses, public URLs, credentials, API keys, database names, secrets, or unredacted production logs.

## Predeploy gate

Before switching the running release, prove and record:

- exact `origin/main` is still `d61768ecf8457a72df80a5cb0220072de76dfdd4`;
- approved code tree/CI evidence is unchanged;
- current deployed source is measured rather than assumed;
- database backup/snapshot succeeds under the existing deployment procedure;
- current service inventory and health are recorded;
- current runtime switches are recorded;
- current Provider request-ledger/call baseline is recorded without making a Provider call;
- rollback target is the measured currently healthy release;
- deployment artifacts/images are immutable and correspond to the approved source/tree.

If main moved, the approved artifact cannot be resolved safely, backup fails, or rollback cannot be guaranteed: stop before switching.

## Deployment invariants

The deployment must preserve all existing runtime policy:

```text
FREE_BRIDGE_MODE = SHADOW_ONLY
ACTIVE_WHITELIST = EXACT_EXISTING_13
PROVIDER_POLICY = UNCHANGED
SCHEDULER_CADENCE = UNCHANGED
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
REAL_MONEY = NOT_AUTHORIZED
```

No manual Provider probe is allowed. Do not enable/disable Scheduler merely to make acceptance easier. Existing naturally scheduled runtime activity may continue under existing policy and must be distinguished from deployment-smoke activity using persisted evidence where available.

No tracked production-code change is authorized by this task. If a code defect is discovered, stop with evidence; do not hotfix main from the VPS deployment task.

## Required postdeploy acceptance

After the switch, independently verify all of the following from the running VPS/public release:

```text
VPS_SOURCE_SHA_MATCHES_APPROVED_MAIN
API_HEALTH_PASS
API_READY_PASS
WEB_HEALTH_PASS
WEB_AND_API_RELEASE_IDENTITY_MATCH
GET_/v1/dashboard/intelligence-workspace_PASS
PUBLIC_SCHEMA = w2.dashboard-intelligence-workspace.v1
PUBLIC_AUTHORITY = NEW_INTELLIGENCE_WORKSPACE_ONLY
READ_CONTRACT_PROVIDER_CALLS = 0
READ_CONTRACT_DB_WRITES = 0
NO_CALL_ON_READ = true
RUNTIME_ACTIVE_WHITELIST_COUNT = 13
RUNTIME_FREE_BRIDGE_MODE = SHADOW_ONLY
CANDIDATE_FORMAL_LOCK_PRODUCTION = OFF
DASHBOARD_REAL_DATA_OR_EXPLICIT_REAL_EMPTY_STATE = PASS
NO_STAGING_SEED_OR_SYNTHETIC_FALLBACK = PASS
NO_LEGACY_BOSS_OR_PERFORMANCE_PUBLIC_ROUTE = PASS
POSTDEPLOY_VISUAL_SMOKE = PASS
SCHEDULER_PROVIDER_RUNTIME_STATUS = VERIFIED_UNCHANGED
REPOSITORY_HYGIENE = PASS
```

Use the unified Intelligence Workspace endpoint, not the retired legacy Dashboard contract, as the product acceptance authority.

The visual smoke should check the real deployed page at the approved desktop authority viewport and at least one responsive viewport. Store only sanitized evidence/hash/summary in GitHub context; do not commit private deployment coordinates.

## Failure and rollback

If health, readiness, release identity, migration/DB compatibility, Web/API routing, or critical unified-workspace smoke fails and cannot be corrected by an ordinary existing operational action, automatically roll back to the measured predeploy healthy release and stop.

Allowed ordinary operational actions include the repository's existing image pull/cache/warm-switch/service-restart/retry/rollback mechanics. They do not include tracked code changes, new runtime flags, Scheduler/cadence changes, Provider policy changes, whitelist changes, model changes, or production-authority enablement.

Terminal deployment classifications:

```text
VPS_DEPLOYMENT_ACCEPTANCE_PASS
VPS_DEPLOYMENT_ROLLED_BACK
POSTDEPLOY_DEFECT_FOUND
```

## Conditional Track A refresh

Track A currently remains `WAIT_MORE_NATURAL_EVIDENCE`. Do not rerun the same public-API-only audit merely because time elapsed.

Because this deployment task has an operational VPS vantage point, after successful deployment it may perform one bounded read-only source-bound refresh **only if** the previously missing evidence can now be read without causing Provider calls or DB business writes. The relevant missing fields are:

- checkpoint terminal status/reason per legal window;
- scheduler task identity or explicit terminal non-execution reason;
- request-ledger identity and quota state;
- raw-payload and endpoint-capture identity;
- post-baseline persisted Round-3 reprojection/current timeline and Model Lab/readiness evidence.

If those source-bound fields are available, update the Track A report/matrix once and classify exactly one of:

```text
TRACK_A_CLOSED_PASS
WAIT_MORE_NATURAL_EVIDENCE
RECURRING_INTERNAL_DEFECT_PROVEN
```

If the fields are still unavailable, do not manufacture a second timestamp-only audit; preserve `WAIT_MORE_NATURAL_EVIDENCE` and record the exact missing evidence.

Even if Track A closes, this task must not start Round4. It may create/update a Round4 readiness decision packet only when Track A evidence actually supports it.

## Overall completion rule

A successful deployment closes the VPS delivery gate but does not by itself convert the current Track A WAIT into PASS.

```text
OVERALL_W2_COMPLETE =
  VPS_DEPLOYMENT_ACCEPTANCE_PASS
  AND TRACK_A_CLOSED_PASS
  AND ALL_EXISTING_FROZEN_STOP_LINES_PRESERVED
```

If deployment passes while Track A still waits, the correct overall state is `DEPLOYED_WAITING_FOR_NATURAL_EVIDENCE`, not project complete.

## Required outputs

Write sanitized evidence back to `context/current`:

- `VPS_DEPLOYMENT_POSTDEPLOY_ACCEPTANCE_RECEIPT.md`;
- update `CODEX_EXECUTION_RECEIPT.md`;
- update `CURRENT_STATE.yaml`;
- update `NEXT_ACTION.md`;
- update Track A closure report/matrix only if a legitimate source-bound refresh was performed;
- create/update `ROUND4_READINESS_DECISION_PACKET.md` only if Track A becomes decision-ready.

## Permanent stop lines

```text
NEW_PROVIDER_OR_PLAN = NOT_AUTHORIZED
MANUAL_PROVIDER_PROBE = FORBIDDEN
SCHEDULER_OR_CADENCE_CHANGE = NOT_AUTHORIZED
ACTIVE_WHITELIST_CHANGE = NOT_AUTHORIZED
MODEL_FACTOR_THRESHOLD_RETRAINING = NOT_AUTHORIZED
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
TRACKED_CODE_HOTFIX_FROM_DEPLOYMENT_TASK = NOT_AUTHORIZED
```
