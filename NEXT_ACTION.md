# NEXT ACTION

```text
ACTIVE_NEXT_ACTION = EXECUTE_DASHBOARD_V41_POSTDEPLOY_BOUNDED_REMEDIATION
CURRENT_GATE = DASHBOARD_V41_POSTDEPLOY_REMEDIATION_ACTIVE
AUTHORITY = DASHBOARD_V41_POSTDEPLOY_BOUNDED_REMEDIATION.md
BASE_MAIN = c6d8c6c7304d302f31bea5a88967e3bc9e945b37
REVIEWED_SOURCE_HEAD = 05cdc3c1c6dbadbfe20899e941ca404274ff786f
PR_506 = MERGED_DEPLOYED_TECHNICAL_PASS_OWNER_CHANGES_REQUIRED_BOUNDED
D16_01_THROUGH_D16_07 = OPEN
ROUND_4 = NOT_STARTED
ROUND_4_EXECUTION_AUTHORITY = NOT_GRANTED
P6 = NOT_AUTHORIZED
TERMINAL_GATE = OWNER_DASHBOARD_V41_POSTDEPLOY_REREVIEW
```

## Binding correction

Do not accept PR #506 as final product completion. Its release/deployment/read-isolation evidence remains valid, but Owner postdeploy inspection exposed seven bounded V4.1 contract/real-data defects.

The first reported issue is now precisely classified: the live serialized pair was `NORMAL + MATCH`; the visible `BLOCKED DAY` label came from `data_operations.system_health`. Fix the public authority conflict rather than claiming an unproven literal `BLOCKED + MATCH` payload.

## Binding read order

```text
1. CODEX_EXECUTION_PROTOCOL.md
2. CURRENT_STATE.yaml
3. NEXT_ACTION.md
4. DASHBOARD_V41_POSTDEPLOY_BOUNDED_REMEDIATION.md
5. W2_LAST_48H_RECONCILIATION_AND_DASHBOARD_V41_EXECUTION_PLAN.md
6. repo-bound V4.1 reference/state matrix/real-shape fixtures
7. current main at c6d8c6c7304d302f31bea5a88967e3bc9e945b37
8. D13/D14/D15 retained truth contracts/tests
9. PR #506 postdeploy receipt as baseline evidence, not final acceptance
```

## Execute continuously

In one remediation PR from current `main`:

1. Close D16-01 mode/system-health public authority conflict.
2. Close D16-02 priority eligibility/default-focus logic; data-incomplete/lineup-only rows must not become priority merely from severity; stale dominates historical movement; evidence usefulness governs focus.
3. Close D16-03 explicit primary-vs-secondary reason rendering and count auditability.
4. Close D16-04 Chinese-first four-risk explanations; canonical codes become technical detail.
5. Close D16-05 causal source-bound match summary.
6. Close D16-06 first-screen nested vertical scrolling; preserve 1180 natural flow and all desktop no-overflow targets.
7. Close D16-07 checkpoint AVAILABLE/STALE/INCOMPLETE/NOT_AVAILABLE truth.
8. Add real-shape regressions reproducing the deployed failure class and all frozen V4.1 day/focus states.
9. Run focused/full Python/Web, visual/accessibility, Ruff/MyPy/typecheck/build, repository/secret/tracked/protected gates.
10. Require exact-head Full CI and `RELEASE_REQUIRED` PASS.
11. Merge automatically after exact-head PASS.
12. Redeploy only through the existing Owner-local OCI relay path.
13. Revalidate exact Web/API identity, health/ready/release-sync, real day/focus/priority state, single-scroll layout, Chinese public copy, checkpoint semantics, provider-call delta 0 and business-write delta 0.
14. Refresh Round4 packet to the remediated exact release identity only, then stop.

Ordinary implementation, CSS, fixture, test, screenshot, CI and deployment-preparation failures are in scope:

```text
fix -> revalidate -> continue
```

No Owner relay is required between these steps.

## Terminal classifications

```text
OWNER_DASHBOARD_V41_POSTDEPLOY_REREVIEW
DASHBOARD_V41_REMEDIATION_DEPLOYMENT_ROLLED_BACK
DASHBOARD_V41_REMEDIATION_SCOPE_BLOCKED_OWNER_DECISION_REQUIRED
```

If critical postdeploy acceptance fails after merge, automatically roll back to `c6d8c6c7304d302f31bea5a88967e3bc9e945b37` and stop with evidence.

## Frozen stop lines

```text
ROUND_4_START = NOT_AUTHORIZED
P6_EXECUTION = NOT_AUTHORIZED
NEW_PROVIDER_OR_PLAN = NOT_AUTHORIZED
MANUAL_PROVIDER_PROBE = FORBIDDEN
SCHEDULER_OR_CADENCE_CHANGE = NOT_AUTHORIZED
ACTIVE_WHITELIST_CHANGE = NOT_AUTHORIZED
MODEL_FACTOR_THRESHOLD_CHANGE = NOT_AUTHORIZED
MODEL_RETRAINING = NOT_AUTHORIZED
MARKET_DIRECTION_BENCHMARK_DEFINITION = NOT_AUTHORIZED
EXTERNAL_INTELLIGENCE_ACTIVATION = NOT_AUTHORIZED
PHASE_0_5_REEXECUTION = FORBIDDEN
H_RESULT_ACCESS = PERMANENTLY_CLOSED
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
REAL_MONEY = NOT_AUTHORIZED
READ_PROVIDER_CALLS = 0_REQUIRED
READ_DB_BUSINESS_WRITES = 0_REQUIRED
VPS_DIRECT_GHCR_BULK_IMAGE_PULL = FORBIDDEN_AS_PRIMARY_TRANSPORT
IMAGE_TRANSPORT = LOCAL_OCI_RELAY_PRIMARY
DELETE_PROTECTED_HISTORICAL_EVIDENCE = FORBIDDEN
```