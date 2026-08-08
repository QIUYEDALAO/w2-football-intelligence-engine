# NEXT ACTION

```text
ACTIVE_NEXT_ACTION = EXECUTE_OWNER_REVIEW_B_BOUNDED_REMEDIATION
CURRENT_GATE = OWNER_REVIEW_B_REMEDIATION
OWNER_REVIEW_B = CHANGES_REQUIRED
REMEDIATION_AUTHORITY = OWNER_REVIEW_B_REMEDIATION.md
CODEX_PROTOCOL = CODEX_EXECUTION_PROTOCOL.md
STANDARD_RECEIPT = CODEX_EXECUTION_RECEIPT.md
PR = 498
REVIEWED_HEAD = a067adbd1d2796cc69ea10bd8cff9aeadf7abee9
P3 = NOT_STARTED_NOT_AUTHORIZED
AFTER_REMEDIATION = STOP_FOR_OWNER_REVIEW_B_REREVIEW
ROUND_4 = NOT_STARTED
```

## Binding read order

```text
1. CODEX_EXECUTION_PROTOCOL.md
2. CURRENT_STATE.yaml
3. NEXT_ACTION.md
4. OWNER_REVIEW_B_REMEDIATION.md
5. OWNER_REVIEW_B_PACKET.md
6. OWNER_REVIEW_A_APPROVAL.md
7. DASHBOARD_INTELLIGENCE_WORKSPACE_PRODUCT_SPEC.md
8. DASHBOARD_DATA_CONTRACT.md on PR #498
9. PERFECT_INTELLIGENCE_CAPABILITY_MATRIX.md on PR #498
10. FRESHNESS_CONTRACT.md on PR #498
11. W2_FINAL_EXECUTION_MASTER_PLAN.md
12. DASHBOARD_INTELLIGENCE_WORKSPACE_MASTER_PLAN.md
13. REPOSITORY_HYGIENE_POLICY.md
```

## Required bounded remediation on existing PR #498

Do not redesign P1/P2. Preserve the one unified read model and close only the Owner Review B contract findings.

### 1. Complete the P0 → P1 → P2 field binding

P1/P2 must add/bind the P0-required Attention fields currently missing from the Attention contract:

```text
affected domain
factual summary
readiness context/status
next_eval_at when available
```

Use existing state/reason/readiness evidence only. No Provider call or new signal.

The existing replay front door already emits `decision_summary`; add it to the final P2 history/replay schema, adapter, sample and tests so the final contract can answer what W2 judged and why.

### 2. Freeze the exact seven states and four risks in schema/tests

The final P2 schema must fail closed to the exact approved seven intelligence states and exact four risk dimensions:

```text
EVENT_RISK
DATA_RISK
MODEL_RISK
COLLECTION_RISK
```

Correct the P2 fixture that currently uses lower-case keys and `market_risk`. Add negative tests for unknown state, missing/extra risk dimension, and `MARKET_RISK`.

### 3. Freeze Scoreline Top 3 semantics

For `scoreline_reference.status = READY`:

```text
simulations_completed = 10000
probability exposed to P3 = explicit unconditional_probability
sample_count preserved
label = MODEL_SCORELINE_REFERENCE
proof_status = NOT_PROVEN
```

Reuse the existing scoreline engine output. No simulation/recalculation on API read. Add negative/positive contract tests.

## Keep all accepted P2 behavior unchanged

Keep:

- one `w2.dashboard-intelligence-workspace.v1` read model;
- current endpoint and checkpoint-only/pure projection boundary;
- no-call/no-write fail-closed behavior;
- 0/1/2+ snapshot semantics;
- NOT_CONNECTED / NOT_DEFINED / NOT_PROVEN;
- API-Football Prediction explicit NOT_AVAILABLE;
- public ROI/CLV and legacy-authority exclusion;
- probability/directional/league/forward validation foundation;
- domain freshness and lineup 1/13 limitation;
- Formal/Candidate/Lock/Production OFF.

## Forbidden

- P3 UI work
- new PR architecture or second read model
- Provider calls
- Scheduler/cadence changes
- whitelist changes
- model/factor/threshold changes
- external-source connection
- Phase 0.5 rerun
- Round 4
- Candidate/Formal/Lock/Production enablement
- legacy deletion

## Required terminal evidence

After fixes on PR #498:

```text
NEW_EXACT_HEAD_SHA
UPDATED_P1_CONTRACTS
UPDATED_SCHEMA_AND_ADAPTER
UPDATED_DETERMINISTIC_SAMPLE
ATTENTION_FIELD_BINDING_TESTS = PASS
EXACT_SEVEN_STATE_FOUR_RISK_TESTS = PASS
SCORELINE_10000_UNCONDITIONAL_TESTS = PASS
REPLAY_DECISION_SUMMARY_TEST = PASS
EXISTING_ZERO_ONE_MULTI_TESTS = PASS
EXISTING_FORBIDDEN_FIELD_TESTS = PASS
EXISTING_NO_CALL_ON_READ_TESTS = PASS
FULL_EXACT_HEAD_CI_RELEASE_REQUIRED = PASS
REPOSITORY_HYGIENE = PASS
WORKTREE = CLEAN
```

Before declaring completion, Codex must also update `CODEX_EXECUTION_RECEIPT.md`, `CURRENT_STATE.yaml`, and `NEXT_ACTION.md` according to `CODEX_EXECUTION_PROTOCOL.md`.

Then stop:

```text
NEXT = OWNER_REVIEW_B_REREVIEW
P3 = NOT_AUTHORIZED
ROUND_4 = NOT_STARTED
```

Do not merge or start P3 automatically.
