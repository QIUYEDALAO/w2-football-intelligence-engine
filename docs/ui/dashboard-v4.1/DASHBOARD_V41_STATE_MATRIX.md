# Dashboard V4.1 State Matrix

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
