# W2 Free-Plan Daily Call Budget

```text
PROVIDER_DAILY_LIMIT = 100
W2_DAILY_CALL_CEILING = 80
MIN_PROVIDER_DAILY_REMAINING = 20
EFFECTIVE_W2_CEILING = 80_NOT_60
AUTOMATIC_RETRY = false
NO_IDLE_POLLING = true
CODE_DEFAULT = OFF
DEPLOYED_RUNTIME_MODE = SHADOW_ONLY
```

## Correct budget interpretation

W2 may record at most 80 calls in one UTC Provider day and must also preserve
at least 20 calls in the Provider's 100-call allowance. These are two views of
the same reserve and must not be subtracted twice.

For each planned call, the runtime requires both:

```text
shared_actual_calls_today + planned_calls <= 80
provider_remaining_after_call >= 20
```

The runtime passes `reserve_bucket=0` to the W2 80-call ceiling check, while
the Provider remaining check separately enforces the 20-call reserve. It
therefore permits call 80 when Provider capacity supports it, and blocks call
81. The superseded `80 - 20 - actual` interpretation is invalid.

## Shared quota truth

The bridge does not trust a process-local counter. It reads the persistent
`provider_request_logs` and `quota_usage` records shared by API-Football
traffic on the same account. Provider limit/remaining evidence and the local
ledger are reconciled; the stricter available capacity wins.

Process restart does not reset the daily count. Unknown Provider remaining
blocks nonessential calls. A known daily limit other than 100 blocks the Free
bridge before business calls.

## Priority and cadence

| Priority | State | Allowed behavior |
|---|---|---|
| P0 | DISCOVERY | at most one no-season UTC-date discovery when the formal request key is not cached |
| P1 | PREMATCH_MARKET | single-fixture odds only for an existing-whitelist fixture in a due checkpoint window |
| P2 | LINEUP_WINDOW | single-fixture lineup only when due and after all selected P1 calls |
| none | POSTMATCH_STATISTICS | state is recorded, but automatic statistics calls are disabled |

The existing scheduler runs the bridge every 300 seconds, but freshness keys
and checkpoint state prevent fixed-frequency Provider polling. No due target
means zero fixture follow-ups. Fresh discovery/odds/lineup evidence means zero
duplicate Provider calls.

## Request shapes

```text
DATE_DISCOVERY = /fixtures?date=<UTC date>
ODDS = /odds?fixture=<single fixture id>
LINEUPS = /lineups?fixture=<single fixture id>
FIXTURE_DETAIL = NOT_REQUIRED_WHEN_DISCOVERY_HAS_CANONICAL_IDENTITY
IDS_BATCHING = false
AUTOMATIC_STATISTICS = false
LIVE_ODDS = false
```

The Free account rejected `fixtures?ids=...`; the deployed runtime never uses
that shape.

## Controlled acceptance accounting

```text
ACCEPTANCE_UTC_DATE = 2026-08-08
SHARED_LOCAL_LEDGER_BEFORE = 26
SHARED_LOCAL_LEDGER_AFTER = 28
TASK_NEW_REAL_CALLS = 2
TASK_CALL_HARD_CAP = 20
TASK_CALL_RESULT = PASS
PROVIDER_DAILY_LIMIT = 100
FINAL_PROVIDER_REMAINING = 93
REQUIRED_REMAINING = 20
AUTOMATIC_RETRIES = 0
```

The two calls were one date discovery and one odds request for fixture
`1575448`. A direct fresh-cache rerun used zero calls. After worker/scheduler
restart, the first scheduled rerun also used zero calls, proving restart-safe
ledger and cache behavior.

Provider remaining is a point-in-time acceptance value. Later authorized
`SHADOW_ONLY` scheduler cycles may consume calls for newly due fixtures, but
the persistent 80-call W2 ceiling and 20-call Provider reserve remain binding.

## Operational stop rules

```text
MODE != SHADOW_ONLY => ZERO_BRIDGE_CALLS
NO_TARGET_FIXTURE => ZERO_FOLLOW_UP_CALLS
CACHED_REQUEST_KEY => ZERO_DUPLICATE_CALLS
W2_DAILY_COUNT >= 80 => ZERO_CALLS
PROVIDER_REMAINING <= 20 => ZERO_CALLS
PROVIDER_REMAINING_UNKNOWN => ZERO_NONESSENTIAL_CALLS
TRANSPORT_OR_PROVIDER_ERROR => NO_AUTOMATIC_RETRY
LEAGUE_FILTER => EXACT_EXISTING_13
AUDIT_ONLY_LEAGUES => RUNTIME_UNREACHABLE
```

This budget authorizes shadow evidence collection only. It does not authorize
paid renewal, Provider cutover, league enablement, recommendations, production
release semantics, real-money actions or Round 3.
