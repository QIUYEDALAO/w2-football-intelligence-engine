# Free-plan fixture bridge shadow operations

The bridge is collection infrastructure only. It reuses the existing scheduler,
Celery worker, API-Football transport, persistent request ledger, raw payloads,
endpoint captures, fixture identities, and matchday market observations. It
does not create recommendations or change the competition registry.

## Safety contract

```text
PROVIDER_DAILY_LIMIT = 100
W2_DAILY_CALL_CEILING = 80
MIN_PROVIDER_DAILY_REMAINING = 20
AUTOMATIC_RETRY = 0
PROVIDER_IDS_BATCHING = false
DEFAULT_MODE = OFF
ACTIVE_MODE = SHADOW_ONLY
```

The runtime reads all API-Football traffic for the UTC day from the shared
persistent ledger and reconciles it with Provider quota observations. The
stricter value wins. Unknown quota blocks every call except one `/status`
reconciliation call. A response error, HTTP 429, plan restriction, unsafe
schema, invalid target identity, or reserve boundary stops all later calls in
that task.

Date discovery is cached for the UTC day. Fixture-scoped evidence uses existing
request task keys and persisted endpoint captures. A fresh cache hit or a run
with no due fixture performs no follow-up Provider call. Free-plan
`fixtures?ids=...` is never used.

## Target and cadence

The target set is loaded from the existing DB-backed 13-league whitelist. Rows
from other Provider leagues may exist in the date response but are rejected
before follow-up calls or target-fixture persistence. The four Round-2 audit
candidates are not registry members and are not imported by the runtime.

Collection states are deterministic:

- `DISCOVERY`: one no-season `fixtures?date=YYYY-MM-DD` capture per UTC day.
- `PREMATCH_MARKET`: existing matchday odds checkpoints when present.
- `LINEUP_WINDOW`: existing lineup checkpoints when present.
- `POSTMATCH_STATISTICS`: explicit state only; statistics are not automatically
  called under the current policy.

Whitelist entries without an existing matchday policy use conservative
collection-only T12, T6, T3, T60, and T30 windows. These are operational
cadences, not betting, alert, recommendation, Candidate, Formal, Lock, or
Production thresholds. On heavy days, all current-market calls are ordered
before optional lineup calls.

## Activation and rollback

Both the immutable compose file and the controlled override default to `OFF`.
After deploying an accepted immutable release, set this ordinary runtime flag
in the deployment environment and recreate only worker and scheduler:

```text
W2_FREE_BRIDGE_MODE=SHADOW_ONLY
```

Rollback is the same one-step flag change:

```text
W2_FREE_BRIDGE_MODE=OFF
```

Recreating worker and scheduler with `OFF` prevents new bridge calls. It does
not alter the 13-league registry and does not delete valid raw payloads,
captures, identities, market observations, quota records, or run audits.

The existing season-based future-refresh owner remains disabled while this
Free-plan bridge is active, preventing duplicate collection ownership.
