# W2 Free-Plan Daily Call Budget

```text
PROVIDER_DAILY_LIMIT = 100
W2_DAILY_HARD_CAP = 80
MIN_PROVIDER_RESERVE = 20
BRIDGE_IMPLEMENTATION_CAP = 80
BRIDGE_IMPLEMENTATION_RESERVE = 20
EFFECTIVE_BRIDGE_PLANNER_CEILING = 60
AUTOMATIC_RETRY = false
NO_IDLE_POLLING = true
DEFAULT_RUNTIME_STATE = DISABLED
```

## Budget interpretation

The Provider account exposes 100 requests/day. W2 may never cross its own
80-call hard cap and must leave at least 20 Provider calls unused. The bounded
PR is deliberately more conservative: its planner applies the 20-call reserve
inside the 80-call W2 cap, so it schedules at most 60 total bridge calls when
starting from zero. This leaves 40 calls against the Provider's 100-call limit
and therefore satisfies both owner guards even if some account usage is outside
the bridge ledger.

The planner receives `actual_calls_today` from the controlled call ledger. Its
remaining schedulable capacity is:

```text
max(80 - 20 - actual_calls_today, 0)
```

Once that capacity is zero, it returns
`FREE_DAILY_RESERVE_PROTECTED` and schedules no request.

## Priority policy

| Priority | Purpose | Scheduling rule |
|---|---|---|
| P0 | date discovery and fixture identity/detail | only one UTC-date discovery when its formal request key is not cached; detail only for a real due target fixture |
| P1 | pre-match odds | only for a discovered target fixture supplied as due by the caller |
| P2 | statistics, injuries or lineups | optional; only an explicitly requested allowed endpoint for a due target fixture |
| P3 | live polling | not implemented or enabled by this bridge; requires separate justification and authority |

Priority is not permission to consume the full budget. No target fixture means
no follow-up call even when quota remains.

## Cache and de-duplication

The bridge does not create a second cache or evidence model. It derives cache
keys with the existing formal `request_task_key` contract and accepts the keys
already represented by endpoint captures. A cached date discovery or cached
fixture follow-up is omitted from the plan.

Fixture IDs are de-duplicated twice:

1. the existing fixture discovery contract resolves repeated Provider rows;
2. the bridge de-duplicates caller-supplied due fixture IDs and intersects them
   with fixtures in the existing target-league set.

The real Free-plan proof rejected `/fixtures?ids=...`. Therefore:

```text
FREE_DEFAULT_IDS_BATCHING = false
FREE_DEFAULT_DETAIL_SHAPE = /fixtures?id=<one_fixture_id>
```

The code retains batches of at most 20 only behind an explicit
`provider_ids_batching=true` capability flag for an account/provider where that
request shape has separately been proven. It is not enabled for the current
Free account.

## Call scenarios

These are ceilings, not polling targets.

| Scenario | Maximum planned calls with empty cache | Formula |
|---|---:|---|
| no target fixture on the date | 1 | one date discovery, then zero follow-ups |
| repeated tick after cached no-target discovery | 0 | cached discovery and no idle polling |
| one target, detail + odds | 3 | `1 + 2 × 1` |
| one target, detail + odds + one enrichment | 4 | `1 + 3 × 1` |
| N targets, detail + odds | `1 + 2N` | truncated before the effective ceiling |
| N targets, detail + odds + one enrichment | `1 + 3N` | truncated before the effective ceiling |

With no earlier daily usage, the conservative 60-call effective ceiling permits
at most 29 targets with discovery/detail/odds, or 19 targets when each also has
one enrichment call. Earlier usage, cached calls, and priority determine the
actual number. The planner truncates lower-priority tail calls rather than
breaching the reserve.

## Validation-day accounting

```text
TASK_CALLS_ATTEMPTED = 5
SUCCESSFUL_DATA_CALLS = 4
EXPECTEDLY_RESTRICTED_CAPABILITY_PROBE = 1
RETRIES = 0
FINAL_CONFIRMED_DAILY_REMAINING_HEADER = 96
REQUIRED_RESERVE = 20
RESERVE_RESULT = PASS
```

The unsupported `ids` probe returned no quota header and remains counted among
attempted calls. There is no attempt to spend the remaining allowance.

## Operational stop rules

The disabled bridge must remain fail-closed unless a later owner-authorized
task wires it into a controlled runtime. Any such task must keep these rules:

```text
NO_TARGET_FIXTURE => ZERO_FOLLOW_UP_CALLS
CACHED_REQUEST_KEY => ZERO_DUPLICATE_CALLS
QUOTA_CAPACITY_ZERO => ZERO_CALLS
TRANSPORT_OR_PROVIDER_ERROR => NO_AUTOMATIC_RETRY
LIVE_ODDS => ONLY_FOR_ACTUALLY_LIVE_FIXTURE_AND_SEPARATE_AUTHORITY
LEAGUE_FILTER => EXISTING_ACTIVE_13_ONLY
```

This budget does not authorize PR merge, Provider cutover, Scheduler changes,
persistent collection, league enablement or Round 3.
