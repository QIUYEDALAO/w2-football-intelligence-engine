# NEXT ACTION

```text
ACTIVE_NEXT_ACTION = W2_MI_FREE_PLAN_FIXTURE_CENTRIC_BRIDGE
OWNER_DECISION = DO_NOT_RENEW_API_FOOTBALL_PRO_NOW
ROUND_1 = PASS
ROUND_2 = PASS_WITH_TERMINAL_PROVIDER_PLAN_RESTRICTION
POST_R2_ACCESS_DECISION = PASS_FREE_PLAN_SEASON_RESTRICTION_CONFIRMED
ROUND_3 = NOT_STARTED
NEXT_CODE_ACTION = BOUNDED_VALIDATION_THEN_CONDITIONAL_DISABLED_BRIDGE_PR
```

The owner explicitly does **not** authorize API-Football Pro renewal now. The previous paid month materially under-used the 7,500/day purchased capacity. Paid current-season access may be reconsidered when the Big Five enter the actual match collection window; it is not a prerequisite for present engineering work.

Current task authority:

```text
FREE_PLAN_FIXTURE_CENTRIC_BRIDGE.md
```

## Immediate objective

Test whether API-Football Free can still provide **current-season data without a season parameter** through fixture-centric request shapes.

Official API-Football currently documents Free access to Fixtures, Livescore, Lineups, Injuries, Pre-match Odds, In-play Odds and Statistics, and documents request forms such as:

```text
/fixtures?date=YYYY-MM-DD
/fixtures?live=all
/fixtures?id=<fixture_id>
/fixtures?ids=<up-to-20-ids>
/odds?fixture=<fixture_id>
/odds?date=YYYY-MM-DD
/odds/live?fixture=<fixture_id>
/injuries?fixture=<fixture_id>
/fixtures/statistics?fixture=<fixture_id>
```

These request shapes do not inherently require `season`.

## Required sequence

```text
1. fetch latest origin/main and origin/context/current
2. read FREE_PLAN_FIXTURE_CENTRIC_BRIDGE.md
3. use the existing active Free key; no purchase/new account
4. make one no-season /fixtures?date=<today> discovery call
5. locate a real fixture from an existing in-season W2 target competition
6. if needed use at most one live/adjacent-date discovery call
7. validate one real fixture-id chain: fixture detail + odds + one necessary extended-data endpoint
8. classify whether current fixture-centric data really works under Free
9. total new calls target 5-8, hard max 12, no retry, reserve at least 20
10. if useful path is proven, create one bounded bridge PR, disabled by default, with quota planner/cache/dedupe/tests
11. if current fixture path is also blocked, do not renew Pro automatically; move to zero-cost/low-cost source bridge decision
12. apply REPOSITORY_HYGIENE_POLICY.md
13. stop before Round 3
```

## Hard boundaries

```text
API_FOOTBALL_PRO_RENEWAL = NOT_AUTHORIZED_NOW
MAX_NEW_PROVIDER_CALLS = 12
TARGET_NEW_PROVIDER_CALLS = 5_TO_8
FREE_DAILY_LIMIT = 100
FREE_DAILY_HARD_CAP_FOR_W2 = 80
MIN_DAILY_RESERVE = 20
AUTOMATIC_RETRY = false
BUSINESS_WRITES_DURING_PROOF = 0
PRODUCTION_SCHEDULER_CHANGE = NOT_AUTHORIZED_BY_VALIDATION_ALONE
PERSISTENT_COLLECTION_EXPANSION = NOT_AUTHORIZED_BY_VALIDATION_ALONE
ACTIVE_WHITELIST = 13_UNCHANGED
NET_NEW_LEAGUE_ENABLEMENT = 0
ROUND_3 = NOT_STARTED
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
```

Do not request owner money or another plan change merely because the season-enumeration path is blocked. First exhaust this no-season fixture-centric Free path.