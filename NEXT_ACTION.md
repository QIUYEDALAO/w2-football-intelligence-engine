# NEXT ACTION

```text
ACTIVE_NEXT_ACTION = EXECUTE_DASHBOARD_V41_CONTINUOUS_IMPLEMENTATION_TO_POSTDEPLOY_OWNER_GATE
CURRENT_GATE = DASHBOARD_V41_CONTINUOUS_EXECUTION_ACTIVE
AUTHORITY = W2_LAST_48H_RECONCILIATION_AND_DASHBOARD_V41_EXECUTION_PLAN.md
BASE_MAIN = d2740a573c748cfaef38c66e951618e8782e09d0
CURRENT_DEPLOYED_SOURCE = 4370393be9b2593ec008d150daa9bf39ddbf265f
V41_DESIGN_FREEZE = PASS_OWNER_APPROVED
TRACK_A = TRACK_A_CLOSED_PASS
ROUND_4 = NOT_STARTED
P6 = NOT_AUTHORIZED
TERMINAL_GATE = OWNER_DASHBOARD_V41_POSTDEPLOY_ACCEPTANCE
```

## Reconciled meaning

The last two days of Provider/data foundation, Round 3, unified read model, validation/replay, canonical identity, collection truth, stale Market Memory, movement evidence, quote-count semantics and repository cleanup are complete and retained.

The old first-screen information architecture is superseded. Do not redo the backend foundations or reopen D13/D14/D15 as separate patch rounds. Implement the Owner-approved V4.1 first screen while preserving those truths.

## Binding read order

```text
1. CODEX_EXECUTION_PROTOCOL.md
2. CURRENT_STATE.yaml
3. NEXT_ACTION.md
4. W2_LAST_48H_RECONCILIATION_AND_DASHBOARD_V41_EXECUTION_PLAN.md
5. DASHBOARD_OWNER_INFORMATION_ARCHITECTURE_RESET.md as historical design rationale
6. current origin/main unified read-model and Dashboard code
7. Owner-local W2设计_v4/ latest V4.1 HTML/PNG artifacts
8. D13/D14/D15 tests and accepted truth contracts
9. ROUND4_READINESS_DECISION_PACKET.md only for later packet refresh, not execution
```

## Execute continuously

### V41-0 — Reference authority

- Verify the latest Owner V4.1 artifact set.
- Copy sanitized editable HTML/PNG references into `docs/ui/dashboard-v4.1/reference/`.
- Record hashes.
- Generate repo-bound visual targets at 1280x720, 1180 responsive, 1366x768, 1512x982 and 1536x1024.
- Create the design spec, state matrix, review packet and realistic fixture JSON.

### V41-1 — Read-model contract

Add source-bound additive fields on the existing endpoint:

```text
day_mode = NORMAL | BLOCKED | CALM | EMPTY
default_focus_type = MATCH | GLOBAL_INCIDENT | DAY_SUMMARY | EMPTY_STATE
default_focus_fixture_id
priority_reason_primary
priority_reason_secondary[]
```

Lock the only valid mappings:

```text
NORMAL  <-> MATCH
BLOCKED <-> GLOBAL_INCIDENT
CALM    <-> DAY_SUMMARY
EMPTY   <-> EMPTY_STATE
```

E stale evidence remains `NORMAL + MATCH + STALE`; D 1180 is responsive only.

Add global incident/day summary/empty navigation, trend versus cross-sectional evidence, raw timestamps/freshness threshold, and valid global-validation checkpoint status. Fail closed on impossible combinations and stale/unknown evidence.

### V41-2 — Production UI

- Replace the current first-screen composition with one clean V4.1 component system.
- Never select `matches[0]` as product policy.
- Use the read-model focus authority.
- Render NORMAL/BLOCKED/CALM/EMPTY and stale Market Memory exactly as frozen.
- Keep Scoreline compact and conditional.
- Keep full validation, performance, replay, external intelligence and Data/Ops secondary.
- Refactor/rewrite CSS; do not append another override block.
- Do not restore Boss/recommendation surfaces.

### V41-3 — Acceptance

Require contract, truth, time arithmetic, default-focus parity, no-call/no-write, five business-state fixtures plus 1180 responsive, stored-target image diff, 200% zoom, keyboard, contrast and no-overflow acceptance.

### V41-4 — Full gate

Run focused and full Python tests, Ruff, MyPy, Web typecheck/build/E2E, all V4.1 visual baselines, staging parity, secret/tracked/protected-evidence checks, Repository Hygiene, exact-head Full CI and `RELEASE_REQUIRED`.

### V41-5 — Merge and deploy

After exact-head PASS, merge automatically and deploy through the existing local OCI relay path. Do not use VPS-direct GHCR bulk pulling as the primary transport.

### V41-6 — Postdeploy

Verify exact Web/API identity, health, ready, release sync, unified endpoint, V4.1 focus fields, real current day-mode rendering, exact 13 competitions, SHADOW_ONLY and zero read calls/writes.

### V41-7 — Round4 packet refresh only

Refresh the Round4 decision packet to the final V4.1 exact release identity, then stop. Do not start Round4.

## Do not stop between phases

Ordinary implementation, CSS, test, screenshot, CI or deployment-preparation failures are in scope:

```text
fix -> revalidate -> continue
```

Do not ask the Owner to relay a new instruction after V41-0, V41-1, V41-2, V41-3, V41-4, merge or deployment.

Stop early only for a proven migration requirement, missing/unverifiable Owner reference, out-of-scope product semantics, runtime-policy change, security/data-integrity conflict, or critical deployment failure after automatic rollback.

## Terminal classifications

```text
DASHBOARD_V41_POSTDEPLOY_READY_FOR_OWNER_ACCEPTANCE
DASHBOARD_V41_DEPLOYMENT_ROLLED_BACK
DASHBOARD_V41_SCOPE_BLOCKED_OWNER_DECISION_REQUIRED
```

## Frozen stop lines

```text
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
ROUND_4_START = NOT_AUTHORIZED
P6_EXECUTION = NOT_AUTHORIZED
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