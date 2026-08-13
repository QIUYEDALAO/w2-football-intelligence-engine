# Dashboard V4.1 State Matrix

Public presentation is derived from two dimensions rather than from panel-local
copy. `scope` is `MATCH`, `SELECTED_DAY`, `CROSS_DAY_CUMULATIVE`, or `GLOBAL`;
`cause` is nullable when ready/empty, otherwise one of the exact causes below.

| Scope | Cause | Public meaning | Severity |
|---|---|---|---|
| `SELECTED_DAY` | `NOT_YET_DUE` | W2 计划采集尚未开始 / 赛果尚未产生 | neutral |
| `SELECTED_DAY` | `AWAITING_COLLECTION` | 已到采集时点，持久化证据或赛果待采集 | warning |
| any | `INSUFFICIENT` | 已采集但证据量不足 | warning |
| any | `UNAVAILABLE` | 来源不提供或不可用 | critical |
| any | `UNASSESSED` | 尚未完成评估 | neutral |
| `MATCH` | `LABEL_MISSING` | 保留已知原名并标记中文译名待映射 | neutral |
| `MATCH` | `IDENTITY_UNRESOLVED` | 身份未知，可使用占位符 | warning |
| `MATCH` | `AMBIGUOUS` | 身份存在歧义，可使用占位符 | warning |

`CROSS_DAY_CUMULATIVE` metrics and `SELECTED_DAY` records are rendered in
separate statistic groups. Raw operations health remains technical truth, but
it cannot choose public copy, color, focus, or layout.

| Facts and semantics | Selected fixture | L2 | L3 authority | Key fail-closed behavior |
|---|---|---|---|---|
| usable evidence, attention item | required | prioritized matches/groups | persisted AH/OU facts, W2 diagnostic relation, blockers, optional scoreline | no match focus without a valid id |
| usable stale market memory | required | stale reason is secondary attention only | persisted history remains visible; comparison paused | never expose READY and STALE together |
| selected-day cause present | null | affected factual rows | scope, cause, counts, last source time, recovery condition | no incident styling for `NOT_YET_DUE`; never force an arbitrary match |
| matches exist, no priority | null | zero priority plus factual summary | why no item requires review and next evaluation | never force a match detail |
| zero persisted fixtures | null | zero rows | no matches, no borrowing; adjacent-day evidence only | never fill from another date |

The only focus invariant is exact: a non-null `selected_fixture_id` must identify
a response match and excludes `global_focus`; a null selection requires a factual
`global_focus`. Unknown scope/cause values fail validation.

## Priority authority

Each match has one `priority_reason_primary` and zero or more `priority_reason_secondary` values. L1 grouping counts primary reasons only. Sorting is deterministic: day-level incident, visible fresh movement, fresh two-plus snapshots with model comparison, remaining review severity, kickoff, fixture id. Stale market memory remains visible as secondary attention but cannot occupy a primary priority slot. This is information usefulness, never betting value.

## Time authority

`generated_at`, `kickoff_utc`, `latest_snapshot_at`, `freshness_max_age_seconds`, and `next_eval_at` are raw source fields. Relative age, countdown and next-evaluation labels are derived by the client. A timestamp not later than `generated_at` is labelled expired, never "next".

Outcome timing uses the existing result-settlement boundary of kickoff plus
three hours. Before that boundary, an unfinished match is `NOT_YET_DUE`; after
it, an unchanged unfinished status is `AWAITING_COLLECTION`, never the false
claim that the result is still not due. Missing time or an unknown, postponed,
or cancelled status is `UNASSESSED`.
