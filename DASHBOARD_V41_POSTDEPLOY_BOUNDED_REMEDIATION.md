# Dashboard V4.1 Postdeploy Bounded Remediation

```text
AUTHORITY = W2_DASHBOARD_V41_POSTDEPLOY_BOUNDED_REMEDIATION_V1
OWNER_DECISION = CHANGES_REQUIRED_BOUNDED
REVIEWED_MAIN = c6d8c6c7304d302f31bea5a88967e3bc9e945b37
REVIEWED_SOURCE_HEAD = 05cdc3c1c6dbadbfe20899e941ca404274ff786f
PR_506 = MERGED_DEPLOYED
REMEDIATION_SCOPE = V41_CONTRACT_TRUTH_PRIORITY_COPY_LAYOUT_CLOSURE_ONLY
AUTOMATIC_IMPLEMENTATION_FIX_CI_MERGE_REDEPLOY = AUTHORIZED
OWNER_RELAY_BETWEEN_STEPS = NOT_REQUIRED
TERMINAL_GATE = OWNER_DASHBOARD_V41_POSTDEPLOY_REREVIEW
ROUND_4 = NOT_STARTED
ROUND_4_EXECUTION_AUTHORITY = NOT_GRANTED
P6 = NOT_AUTHORIZED
```

## Independent review result

PR #506 is a real merged/deployed V4.1 build and its release, no-call/no-write, deployment and repository gates remain valid. Owner postdeploy inspection nevertheless found a bounded group of public-contract and real-data presentation defects. This is not a V4.1 redesign reset and does not reopen D13/D14/D15 foundations.

One correction to the initial visual diagnosis is binding: the postdeploy receipt proves the live V4.1 payload itself was `day_mode=NORMAL` and `default_focus_type=MATCH`. The visible `BLOCKED DAY` pill comes from `data_operations.system_health`, while the page mode/focus comes from the new V4.1 focus authority. Therefore D16-01 is a **public authority conflict**, not evidence that the serialized pair was literally `BLOCKED + MATCH`. The user-visible contradiction is still invalid and must be closed.

## D16-01 — Page mode and system-health authority conflict — P0

Current behavior can render a raw `BLOCKED_DAY` system-health pill while the V4.1 page is `NORMAL + MATCH`. A reader reasonably interprets this as the frozen `BLOCKED` day mode even though the two values come from different fields.

Required closure:

1. There must be exactly one public day-mode authority on the first screen.
2. If source degradation is a whole-football-day blocker, project `BLOCKED + GLOBAL_INCIDENT + null fixture`.
3. If degradation is not sufficient to make the whole day `BLOCKED`, the header must not display `BLOCKED DAY` as a day-mode badge. It may show a clearly scoped Chinese system-health label such as partial/system data degradation, with the raw code only in technical detail.
4. A `NORMAL + MATCH` screen must never visibly claim `BLOCKED DAY`.
5. Existing schema fail-closed rules for `NORMAL/MATCH`, `BLOCKED/GLOBAL_INCIDENT`, `CALM/DAY_SUMMARY`, `EMPTY/EMPTY_STATE` remain mandatory.

Acceptance: real-shape and API/UI tests prove no contradictory public mode/system label and no impossible serialized pair.

## D16-02 — Priority eligibility and default focus — P0

Current code assigns a primary reason to `DATA_INCOMPLETE`, `LINEUP_PENDING` and `FRESH_MARKET_EVIDENCE`, then treats every non-null primary reason as a priority match. This makes evidence-empty matches occupy the priority shortlist and can make stable evidence-rich matches prevent `CALM`.

Freeze the distinction between **attention reason** and **priority eligibility**:

- `MARKET_MOVEMENT` is priority-eligible only when the relevant current market evidence is usable and the movement is supported by persisted evidence.
- `MODEL_DIAGNOSTIC` is priority-eligible only when the current comparison is source-bound and available.
- `STALE_MARKET_MEMORY` may be priority-eligible for awareness; stale must dominate historical movement as the public primary reason because stale evidence cannot authorize a current movement conclusion.
- `DATA_INCOMPLETE`, `LINEUP_PENDING` and localized collection/data blockers are grouped under `其他关注`; they do not become priority matches merely because they are severe.
- `FRESH_MARKET_EVIDENCE` is an evidence-quality fact, not by itself an Attention/priority reason.

Day/focus behavior:

- If a usable READY or STALE evidence match exists, a zero-evidence `DATA_INCOMPLETE` match must not be the default focus.
- If the entire day has no usable match evidence and is blocked by source-bound data/collection conditions, render `BLOCKED + GLOBAL_INCIDENT`, never an arbitrary empty MATCH.
- `CALM` requires source-bound evidence that the observed day is genuinely calm/complete; it is not merely `no priority reason`.
- A mixed day may remain `NORMAL + MATCH`, but the focus must be the most useful source-bound evidence match.
- Kickoff time and fixture id remain deterministic tie-breaks only after evidence usefulness.

L1 priority counts must count only priority-eligible primary reasons and must not double count secondary reasons.

## D16-03 — Primary reason must be visually auditable — P0

Each shortlist match must visibly distinguish:

```text
主因: <one primary reason>
次因: <zero or more secondary reasons>
```

The primary reason must have a dedicated tag/chip or equivalent dominant styling. Secondary reasons must be visually subordinate or folded. The reader must be able to reconcile every L1 primary-reason count with the rows without guessing.

## D16-04 — Four-risk public copy must be Chinese-first — P1

The first screen must not use raw strings such as `DATA IDENTITY NOT READY`, `MODEL SIMULATION NOT READY` or `COLLECTION ASSESSMENT NOT AVAILABLE` as the main explanation.

Required:

- render dimension-specific Chinese public explanations from source reason codes/status;
- keep raw canonical codes only in technical detail;
- when several codes exist, summarize the main Chinese reasons and expose the code count/details secondarily;
- do not fabricate an explanation when source evidence is absent;
- `UNASSESSED` remains `未评估`, never `正常`.

## D16-05 — Match summary must be causal, not status concatenation — P1

`数据不完整；正式推荐未启用` is not a sufficient match summary.

The summary must be source-bound and answer, in one compact statement:

1. what evidence is present/missing or stale;
2. what conclusion is therefore allowed/blocked;
3. what existing process can change the state.

For zero-market-evidence cases, state that AH/OU persisted evidence is absent, trend/current model-market comparison cannot be produced, and recovery waits for existing scheduled evidence. Do not imply a read-side Provider call.

Use one summary authority so the same object does not receive conflicting explanations across panels.

## D16-06 — Remove first-screen nested vertical scrolling — P1

The deployed 1366-class view can show both a page scrollbar and an independent focus-body scrollbar. The approved V4.1 first screen must not require nested vertical scrolling to read the primary match.

Required:

- no independent vertical scrollbar inside `v41-focus-body` at 1280/1366/1512/1536 desktop acceptance viewports;
- a single natural page scroll is acceptable when real content exceeds the viewport;
- keep the 1180 natural-flow contract;
- compact/fold full four-risk technical detail if needed; the first screen should keep only the concise risk/diagnostic summary and move detailed codes to technical/secondary detail;
- no horizontal overflow.

## D16-07 — Global validation checkpoint states must be internally coherent — P1

Current UI can say `历史验证暂不可用` while also showing a checkpoint timestamp. Close the state model explicitly:

```text
AVAILABLE   = checkpoint exists, is current, required metrics complete
STALE       = checkpoint timestamp exists and exceeds freshness boundary
INCOMPLETE  = current checkpoint identity/timestamp exists but required probability metrics are incomplete
NOT_AVAILABLE = no usable checkpoint identity/timestamp exists
```

Equivalent source-bound naming is acceptable, but these meanings must remain distinct.

Rules:

- `STALE` says `已过期（截至 ...）`; metrics remain fail-closed unless explicitly authorized by the validation contract.
- `INCOMPLETE` says checkpoint/metrics incomplete and may show its source timestamp.
- `NOT_AVAILABLE` must not show a misleading `截至 ...` timestamp.
- no validation number may fall back to a design fixture or stale constant.

## Required regression matrix

Add a real-shape fixture reproducing the postdeploy class of state: several matches, stale/data-incomplete reasons, zero-snapshot matches, raw degradation `BLOCKED_DAY`, unavailable/incomplete checkpoint metadata.

Must cover at minimum:

```text
NORMAL + MATCH with useful evidence
NORMAL + MATCH + STALE
mixed useful + data-incomplete day
all-unusable blocked day -> GLOBAL_INCIDENT
CALM + DAY_SUMMARY
EMPTY + EMPTY_STATE
primary vs secondary reason counting
raw system health vs public day-mode label
0/1/2+ market timeline
Chinese risk public copy
causal match summary
AVAILABLE/STALE/INCOMPLETE/NOT_AVAILABLE checkpoint states
1280x720
1366x768
1512x982
1536x1024
1180 responsive
200% zoom
keyboard focus
single vertical scroll path / no nested focus scrollbar
```

Production and deterministic E2E must use the same focus/priority logic.

## Continuous execution authorization

Execute in one remediation PR from current `main`:

```text
fix D16-01..D16-07
-> focused contracts and real-shape E2E
-> stored-target visual comparison / truthful revised targets if source-bound real-state copy changes
-> full Python/Web tests
-> Ruff/MyPy/typecheck/build
-> Repository Hygiene / secret / tracked / protected evidence
-> exact-head Full CI + RELEASE_REQUIRED
-> automatic merge
-> local OCI relay deployment
-> Web/API exact-source + health/ready/release-sync
-> real current payload and real 1366/1512 device/browser acceptance
-> provider_calls delta 0 / business writes delta 0
-> refresh Round4 packet exact release identity only
-> stop at OWNER_DASHBOARD_V41_POSTDEPLOY_REREVIEW
```

Ordinary implementation, test, CSS, screenshot, CI and deployment-preparation failures are in scope: fix, revalidate and continue. Do not stop for intermediate Owner relay.

If deployment acceptance fails critically, automatically roll back to `c6d8c6c7304d302f31bea5a88967e3bc9e945b37` and stop with a rollback receipt.

## Stop lines

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
IMAGE_TRANSPORT = LOCAL_OCI_RELAY_PRIMARY
VPS_DIRECT_GHCR_BULK_IMAGE_PULL = FORBIDDEN_AS_PRIMARY_TRANSPORT
DELETE_PROTECTED_HISTORICAL_EVIDENCE = FORBIDDEN
```