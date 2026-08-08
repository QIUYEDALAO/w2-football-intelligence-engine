# W2 Zero-Cost Free-Plan Fixture-Centric Bridge

```text
TASK = W2_MI_FREE_PLAN_FIXTURE_CENTRIC_BRIDGE
OWNER_DECISION = DO_NOT_RENEW_API_FOOTBALL_PRO_NOW
OWNER_TIMING = CONSIDER_PRO_WHEN_BIG_FIVE_ACTUAL_MATCH_COLLECTION_WINDOW_BEGINS
ROUND_2 = PASS_WITH_TERMINAL_PROVIDER_PLAN_RESTRICTION
POST_R2_ACCESS_DECISION = PASS_FREE_PLAN_SEASON_RESTRICTION_CONFIRMED
ROUND_3 = NOT_STARTED
```

## Owner intent

Do not purchase or renew API-Football Pro merely to unblock development or run a few validation calls. The previous paid month materially under-used the purchased 7,500/day capacity. W2 must first exhaust a zero-incremental-cost architecture using the existing active Free account and its 100 requests/day.

A future Pro purchase may be reconsidered when the Big Five leagues enter the actual current-season collection window and there is a demonstrated data-volume/season-entitlement need. Purchase is not authorized by this task.

## Current proven facts

```text
API_FOOTBALL_PLAN = FREE
ACCOUNT_ACTIVE = true
DAILY_LIMIT = 100
SEASON_2024 = ACCESSIBLE_CONTROL
SEASON_2025 = PLAN_RESTRICTED_CONTROL
SEASON_2026 = PLAN_RESTRICTED_CONTROL
ROOT_CAUSE = FREE_PLAN_SEASON_ENTITLEMENT_RESTRICTION
INTERNAL_W2_REQUEST_CLIENT_DEFECT = false
```

The season entitlement result does not prove that current fixture-centric endpoints are unusable, because API-Football documents current-data request shapes that do not require a season parameter.

Official API-Football documentation currently supports:

```text
GET /fixtures?date=YYYY-MM-DD
GET /fixtures?live=all
GET /fixtures?id=<fixture_id>
GET /fixtures?ids=<id-id-...>   # up to 20 fixture ids
GET /odds?fixture=<fixture_id>
GET /odds?date=YYYY-MM-DD
GET /odds/live?fixture=<fixture_id>
GET /injuries?fixture=<fixture_id>
GET /injuries?ids=<id-id-...>
GET /fixtures/statistics?fixture=<fixture_id>
```

The Free plan is documented as including Fixtures, Livescore, Lineups, Injuries, Pre-match Odds, In-play Odds and Statistics; Free limitations are season-related.

## Mission

Determine whether W2 can operate a useful current-match bridge on the Free plan without querying restricted `league + season` enumeration paths.

The desired architecture is fixture-centric:

```text
DATE/LIVE DISCOVERY
-> FILTER TO EXISTING TARGET LEAGUES
-> FIXTURE_ID
-> CURRENT FIXTURE DETAIL / ODDS / INJURY / STATISTICS AS NEEDED
-> CACHE / PERSIST THROUGH EXISTING W2 RAW-EVIDENCE CONTRACTS
```

This is not authorization to claim full historical coverage or to bypass Provider terms. It is a bounded compatibility and architecture validation.

## Phase A — minimum live Free-plan proof

Use the existing Free key in the secure environment. No new account or purchase.

Maximum new Provider calls for this validation:

```text
MAX_NEW_PROVIDER_CALLS = 12
TARGET_CALLS = 5_TO_8
DAILY_RESERVE_AFTER_TASK >= 20
AUTOMATIC_RETRY = false
BUSINESS_DB_WRITES = 0 during proof
CHECKPOINT_WRITES = 0 during proof
```

Do not repeat the 17-league season audit.

Required sequence:

1. Re-fetch latest `origin/main` and `origin/context/current`.
2. Read current Free account status from the already-proven Post-R2 evidence; call `/status` again only if needed to establish today's remaining quota.
3. Call `/fixtures?date=<current UTC date>` **without `season`**.
4. Inspect whether the response contains any fixture from existing W2 active target leagues that are actually in season now, such as MLS, Brasileirão Série A, Allsvenskan, Eliteserien, Chinese Super League or Argentina Primera. Do not assume coverage; use real response evidence.
5. If no usable target fixture is returned for that date, use at most one alternative discovery call (`/fixtures?live=all` or an adjacent date) without season.
6. For one real returned target fixture, validate the minimum fixture-centric chain using only necessary calls:
   - fixture detail via `id` if not already sufficient;
   - pre-match odds via `/odds?fixture=<id>` when applicable;
   - in-play odds only if the fixture is actually in play;
   - one of injuries/statistics/lineup evidence only where relevant and available.
7. Record exact HTTP/provider status, result count, league/fixture identity, current season observed in the response, bookmaker count, AH/OU presence, timestamps and call cost.
8. Preserve a sanitized call ledger; no raw secrets or auth headers.

### Proof outcomes

Classify:

```text
A = FREE_FIXTURE_CENTRIC_CURRENT_DATA_WORKS
B = FIXTURE_DISCOVERY_WORKS_BUT_ODDS_OR_EXTENDED_DATA_BLOCKED
C = CURRENT_FIXTURE_DATA_ALSO_SEASON_ENTITLEMENT_BLOCKED
D = NO_TARGET_FIXTURE_AVAILABLE_FOR_VALID_CONTROL
E = PROVIDER_SCHEMA_OR_OTHER_BLOCKER
```

Do not infer A from docs alone. A requires real current-season Provider evidence through a no-season request shape.

## Phase B — conditional bounded implementation

If and only if Phase A proves `A` or a useful `B`, Codex is authorized to create one bounded runtime PR implementing a **fixture-centric Free-plan bridge**, but it must remain disabled by default until post-merge acceptance.

Design requirements:

```text
NO league+season enumeration dependency for bridge discovery
EXISTING_ACTIVE_WHITELIST remains exact 13
NET_NEW_AUDIT_ONLY remains not enabled
DATE/LIVE discovery is filtered locally to canonical target competition identity
fixture IDs become the unit of follow-up calls
cache and de-duplicate fixture calls
use ids batching where supported
no automatic retry
quota-aware hard stop
Free-plan daily hard cap <= 80
reserve >= 20
request only when a target fixture exists or is within a justified match window
no idle polling when no target match exists
```

The bridge must use existing raw payload / endpoint capture / fixture identity / canonical market contracts where possible. Do not create a parallel duplicate data model merely for Free mode.

### Quota design target

A 100/day Free account must be treated as a scarce budget, not a continuous-polling feed.

The implementation must produce an explicit daily call planner. It should prioritize:

```text
P0: fixture discovery / identity
P1: pre-match odds close to configured collection checkpoints
P2: lineup/injury/statistics only when they can change a visible diagnostic state
P3: live polling only if separately justified and within remaining budget
```

Do not spend calls simply because quota remains.

## Phase C — fallback if API-Football current fixture path is blocked

If Phase A proves `C`, do not recommend immediate Pro purchase merely to finish engineering.

Instead create a zero-cost/low-cost bridge decision using current official-source evidence:

1. fixtures/results/competition calendar from existing W2 persisted sources and/or official league sources;
2. current odds as an optional separate source;
3. The Odds API Starter may be evaluated as a zero-dollar odds-only fallback (official current plan: 500 credits/month), but soccer `spreads/totals` coverage must be verified per target league/bookmaker and must not be assumed complete;
4. no historical-odds dependency may be claimed from a free plan;
5. any new Provider integration requires a separate bounded code path and must not silently become production authority.

Output a decision rather than buying capacity prematurely.

## Big Five timing

As of the current 2026/27 calendars, actual league play begins later in August for major competitions; for example LaLiga begins 15 August, Premier League 21 August, Serie A weekend of 23 August and Bundesliga 28 August. This supports deferring paid high-capacity access until there is an actual current-season collection need.

The exact renewal date is an owner commercial decision and is not automated.

## Completion outputs

Create/update:

```text
FREE_PLAN_FIXTURE_CENTRIC_VALIDATION.md
FREE_PLAN_DAILY_CALL_BUDGET.md
```

If a bounded implementation PR is warranted, final evidence must include exact base/head/PR/CI, call planner tests, quota guards and zero runtime whitelist expansion.

Expected next state if validation succeeds but runtime activation is still pending:

```text
FREE_PLAN_FIXTURE_CENTRIC_BRIDGE = VALIDATED
ROUND_3 = NOT_STARTED
NEXT = AWAIT_OWNER_BRIDGE_ACTIVATION_OR_CONTINUE_BOUNDED_IMPLEMENTATION_DECISION
```

If the bridge can be implemented and fully validated without production activation:

```text
FREE_PLAN_FIXTURE_CENTRIC_BRIDGE = IMPLEMENTED_DISABLED_BY_DEFAULT
ROUND_3 = NOT_STARTED
NEXT = AWAIT_OWNER_CONTROLLED_ACTIVATION_DECISION
```

If current fixture-centric access is also blocked:

```text
FREE_PLAN_FIXTURE_CENTRIC_BRIDGE = NOT_VIABLE
ROUND_3 = NOT_STARTED
NEXT = ZERO_COST_ODDS_OR_SOURCE_BRIDGE_DECISION
```

## Permanent boundaries

```text
PROVIDER_PURCHASE_OR_RENEWAL = NOT_AUTHORIZED_NOW
PROVIDER_CUTOVER = NOT_AUTHORIZED
PRODUCTION_SCHEDULER_CHANGE = NOT_AUTHORIZED_BY_VALIDATION_ALONE
PERSISTENT_COLLECTION_EXPANSION = NOT_AUTHORIZED_BY_VALIDATION_ALONE
ACTIVE_WHITELIST = 13_UNCHANGED
NET_NEW_LEAGUE_ENABLEMENT = 0
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
ROUND_3 = NOT_STARTED
H_RESULT_ACCESS = PERMANENTLY_CLOSED
BETTING_EDGE_CLAIM = FORBIDDEN
REAL_MONEY = NOT_AUTHORIZED
```

Before task PASS, apply `REPOSITORY_HYGIENE_POLICY.md` and delete provably dead diagnostic scratch assets.