# Dashboard V4.1 State Matrix

Public presentation is derived from two dimensions rather than from panel-local
copy. `scope` is `MATCH`, `SELECTED_DAY`, `CROSS_DAY_CUMULATIVE`, or `GLOBAL`;
`cause` is nullable when ready/empty, otherwise one of the exact causes below.

| Scope | Cause | Public meaning | Severity |
|---|---|---|---|
| `SELECTED_DAY` | `NOT_YET_DUE` | 未进入市场采集窗口 / 赛果尚未产生 | neutral |
| `SELECTED_DAY` | `AWAITING_COLLECTION` | 已到采集时点，持久化证据或赛果待采集 | warning |
| any | `INSUFFICIENT` | 已采集但证据量不足 | warning |
| any | `UNAVAILABLE` | 来源不提供或不可用 | critical |
| any | `UNASSESSED` | 尚未完成评估 | neutral |
| `MATCH` | `LABEL_MISSING` | 保留已知原名并标记中文译名待映射 | neutral |
| `MATCH` | `IDENTITY_UNRESOLVED` | 身份未知，可使用占位符 | warning |
| `MATCH` | `AMBIGUOUS` | 身份存在歧义，可使用占位符 | warning |

`CROSS_DAY_CUMULATIVE` metrics and `SELECTED_DAY` records are rendered in
separate statistic groups. Raw `day_mode` and source states remain technical
truth, but they do not choose public copy or color independently.

| Scenario | `day_mode` | `default_focus_type` | Fixture id | L2 | L3 authority | Key fail-closed behavior |
|---|---|---|---|---|---|---|
| Normal, rich evidence | `NORMAL` | `MATCH` | required | prioritized matches/groups | persisted AH/OU facts, W2 diagnostic relation, blockers, optional scoreline | no match focus without a valid id |
| Normal, stale market memory | `NORMAL` | `MATCH` | required | stale reason may be primary | persisted history remains visible; comparison paused | never expose READY and STALE together |
| Whole-day collection incident | `BLOCKED` | `GLOBAL_INCIDENT` | null | incident group | affected scope, factual cause, last source time, recovery condition | never force an arbitrary match |
| Calm day | `CALM` | `DAY_SUMMARY` | null | zero priority plus factual summary | why no item requires review and next evaluation | never force a match detail |
| Empty football day | `EMPTY` | `EMPTY_STATE` | null | zero rows | no matches, no borrowing; adjacent-day evidence only | never fill from another date |
| Responsive presentation | unchanged | unchanged | unchanged | rows stack above L3 | same semantic payload | presentation is not a fifth business mode |

The valid pairs are bidirectional and exact:

```text
NORMAL  <-> MATCH
BLOCKED <-> GLOBAL_INCIDENT
CALM    <-> DAY_SUMMARY
EMPTY   <-> EMPTY_STATE
```

Examples that must fail validation include `BLOCKED + MATCH`, `EMPTY + non-null fixture`, `NORMAL + null fixture`, `CALM + non-null fixture`, and any unknown day or focus state.

## Priority authority

Each match has one `priority_reason_primary` and zero or more `priority_reason_secondary` values. L1 grouping counts primary reasons only. Sorting is deterministic: day-level incident, visible fresh movement, fresh two-plus snapshots with model comparison, stale market memory, remaining review severity, kickoff, fixture id. This is information usefulness, never betting value.

## Time authority

`generated_at`, `kickoff_utc`, `latest_snapshot_at`, `freshness_max_age_seconds`, and `next_eval_at` are raw source fields. Relative age, countdown and next-evaluation labels are derived by the client. A timestamp not later than `generated_at` is labelled expired, never "next".
