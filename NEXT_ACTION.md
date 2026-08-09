# NEXT ACTION

```text
ACTIVE_NEXT_ACTION = EXECUTE_DASHBOARD_OWNER_CANONICAL_TRUTH_REMEDIATION
CURRENT_GATE = DASHBOARD_OWNER_CANONICAL_TRUTH_REMEDIATION_ACTIVE
AUTHORITY = DASHBOARD_OWNER_CANONICAL_IDENTITY_COLLECTION_SEMANTICS_REMEDIATION.md
BASE_MAIN = 5f8066187acc323d23ac4d73da7115100a58aa48
PR_502_503 = MERGED_DEPLOYED_BUT_OWNER_ACCEPTANCE_REVOKED
TRACK_A = TRACK_A_CLOSED_PASS
ROUND_4 = NOT_STARTED
P6 = NOT_AUTHORIZED
TERMINAL_TARGET = DASHBOARD_OWNER_CANONICAL_TRUTH_ACCEPTANCE_PASS
```

## Binding read order

```text
1. CODEX_EXECUTION_PROTOCOL.md
2. CURRENT_STATE.yaml
3. NEXT_ACTION.md
4. DASHBOARD_OWNER_CANONICAL_IDENTITY_COLLECTION_SEMANTICS_REMEDIATION.md
5. DASHBOARD_DATA_CONTRACT.md
6. current origin/main unified workspace/read-model implementation
7. current performance cohort + fixture checkpoint projection code
8. current CompetitionRegistry and competition seed/config authority
9. PR #502/#503 only as historical implementation evidence
10. CODEX_EXECUTION_RECEIPT.md
```

## Execute continuously

Close D14-01 through D14-08 as one bounded task. Do not stop for ordinary
in-scope implementation, test, schema-additive, identity, responsive, CI,
merge, local-relay or postdeploy defects. Fix and revalidate until the terminal
target or a frozen stop-line conflict.

Highest-priority requirements:

```text
D14-01 one source-bound canonical row per national league; no alias duplicate or fixture double-count
D14-02 collection risk cannot be green OK without persisted assessment evidence
```

Then close:

```text
D14-03 canonical Chinese competition names; no mixed-language or raw slug primary copy
D14-04 tournament/cup samples separated from 联赛表现
D14-05 BASELINE_PRIOR -> 仅先验 / PRIOR_ONLY, not 模型就绪
D14-06 homogeneous blocked-day Attention collapses to an expandable aggregate
D14-07 project and display the existing football-day boundary
D14-08 every 仅记录 state exposes its exact reason and benchmark status separately
```

## Critical implementation constraints

- Canonicalize performance identity before the public response; do not dedupe by
  translated display text.
- Do not blindly add aggregate checkpoint rows that may overlap. Use existing
  fixture-level performance checkpoints to prove/dedupe canonical samples, or
  fail closed with an explicit aggregation conflict.
- Recompute rates from counts; never average percentages.
- Use registry `scope_group`/canonical identity to separate national leagues and
  tournaments. Do not change the whitelist or delete World Cup evidence.
- `provider_calls=0` is a read invariant, not collection-health evidence.
- Collection `OK` requires source-bound assessed terminal/capture evidence and
  source time. Missing evidence must display `未评估`, without inventing an
  incident.
- Preserve source simulation status in technical details, but public model
  readiness must downgrade `BASELINE_PRIOR` to `PRIOR_ONLY`.
- Project the already-existing DayView football-day start/end/cutoff authority;
  do not duplicate the cutoff rule in frontend-only code.
- No Provider call, no DB business write, no migration, no Scheduler/cadence,
  whitelist, model/factor/threshold or runtime-authority change.

## Required deterministic evidence

```text
allsvenskan + provider alias -> one 瑞典超 row
chinese_super_league + provider alias -> one 中超 row
same fixture across aliases -> counted once
ambiguous overlap -> fail closed, not summed
world_cup_2026 -> 世界杯 outside 联赛表现
no collection evidence -> 未评估, not green 正常
fresh persisted collection terminal/capture -> 正常 with source_as_of
READY + BASELINE_PRIOR -> 仅先验
9/9 same DATA_INCOMPLETE -> one aggregate Attention + expandable 9 rows
next-calendar-day kickoff -> football-day boundary visible
仅记录（概率质量未就绪） != 仅记录（样本不足）
市场方向基准未定义 shown separately
```

Maintain real-device readability and no-overlap acceptance at least for:

```text
1280x720
1366x768
1512x982
1920x1080
```

## Delivery sequence

```text
implementation
-> focused + full tests
-> exact-head Full CI / RELEASE_REQUIRED
-> Repository Hygiene
-> merge accepted PR(s)
-> immutable image promotion
-> LOCAL_OCI_RELAY_PRIMARY
-> VPS warm switch
-> real-data postdeploy acceptance
-> STOP
```

Multiple PRs are allowed only as one continuous task when real postdeploy data
exposes an in-scope defect. Do not wait for an intermediate Owner message.

## Terminal classifications

```text
DASHBOARD_OWNER_CANONICAL_TRUTH_ACCEPTANCE_PASS
DASHBOARD_OWNER_CANONICAL_TRUTH_ROLLED_BACK
BLOCKED_OWNER_DECISION_REQUIRED
```

After PASS, Round4 remains `NOT_STARTED`; stop at Owner Round4 decision.

## Frozen stop lines

```text
ROUND_4_START = NOT_AUTHORIZED
P6_EXECUTION = NOT_AUTHORIZED
NEW_PROVIDER_OR_PLAN = NOT_AUTHORIZED
MANUAL_PROVIDER_PROBE = FORBIDDEN
SCHEDULER_OR_CADENCE_CHANGE = NOT_AUTHORIZED
ACTIVE_WHITELIST_CHANGE = NOT_AUTHORIZED
MODEL_FACTOR_THRESHOLD_RETRAINING = NOT_AUTHORIZED
EXTERNAL_INTELLIGENCE_ACTIVATION = NOT_AUTHORIZED
PHASE_0_5_REEXECUTION = FORBIDDEN
H_RESULT_ACCESS = PERMANENTLY_CLOSED
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
REAL_MONEY = NOT_AUTHORIZED
VPS_DIRECT_GHCR_BULK_IMAGE_PULL = FORBIDDEN_AS_PRIMARY_TRANSPORT
IMAGE_TRANSPORT = LOCAL_OCI_RELAY_PRIMARY
```
