# W2 Current Task Checklist

```text
PROGRAM = W2_FOOTBALL_MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
PRODUCT = W2 Football Intelligence
ROUND_1 = PASS
ROUND_2 = PASS_WITH_TERMINAL_PROVIDER_PLAN_RESTRICTION
POST_R2_ACCESS_DECISION = PASS_FREE_PLAN_SEASON_RESTRICTION_CONFIRMED
ACTIVE_TASK = AWAIT_OWNER_API_FOOTBALL_PLAN_OR_DATA_SOURCE_DECISION
ROUND_3 = NOT_STARTED
```

## Completed Post-R2 access decision

- [x] Re-fetched latest `origin/main` and `origin/context/current`; used
  `b04dcc7e521dce413740bcf754b1a45755a3e83e` and
  `e9534b2864849c66f5864a24515cb3ef82c51614` as execution bases.
- [x] Inspected the exact code path that converts Provider `errors.plan` into
  `PLAN_RESTRICTED`.
- [x] Verified Round-2 retained sanitized evidence without exposing secrets.
- [x] Verified official current plan, season, endpoint, odds, price and terms
  semantics.
- [x] Distinguished calendar-year and cross-year season semantics.
- [x] Called `/status` once: Free, active, 100 requests/day.
- [x] Compared repository league ID 39 for seasons 2026 and 2025: both Free-plan
  restricted.
- [x] Verified season 2024 for the same league succeeds.
- [x] Used exactly 4 new read-only Provider calls, no retries, business writes,
  checkpoints or 17-league rebatch.
- [x] Classified root cause as `FREE_PLAN_SEASON_ENTITLEMENT_RESTRICTION` with
  high confidence.
- [x] Rejected a fake internal fix; no code PR was created.
- [x] Produced `POST_R2_PROVIDER_ACCESS_ROOT_CAUSE.md`.
- [x] Produced `POST_R2_DATA_SOURCE_DECISION_MATRIX.md`.
- [x] Compared current API-Football, paid API-Football, Sportmonks, The Odds API
  and a hybrid path using current official sources.
- [x] Recorded 17-league coverage, AH/OU, historical odds, timestamps,
  bookmaker depth, lineups, injuries, statistics/xG, quotas, licensing, prices,
  costs, implementation effort and risks.
- [x] Marked evidence as `VERIFIED_BY_CALL`, `DOCUMENTED` or `NOT_VERIFIED`.
- [x] Selected API-Football Pro as preferred and Sportmonks Growth + Premium
  Odds after trial as fallback.
- [x] Executed repository hygiene; no repository dead assets were introduced or
  found in authorized scope; transient diagnostic scratch was removed.
- [x] Kept active whitelist exact 13, four candidates audit-only and Round 3
  not started.

## Repository hygiene result

```text
REPOSITORY_HYGIENE = PASS
DEAD_ASSETS_FOUND = 1_TRANSIENT_DIAGNOSTIC_SCRIPT
DEAD_ASSETS_DELETED = 1_TRANSIENT_DIAGNOSTIC_SCRIPT
OBSOLETE_CODE_LINES_REMOVED = 0
RETAINED_FOR_EVIDENCE = 2_POST_R2_REPORTS_PLUS_EXISTING_ROUND_2_EVIDENCE
UNRESOLVED_HYGIENE_ITEMS = 0
```

## Not authorized

```text
PURCHASE_OR_PLAN_CHANGE
CREDENTIAL_REPLACEMENT
PROVIDER_CUTOVER
PRODUCTION_SCHEDULER_CHANGE
PERSISTENT_COLLECTION_EXPANSION
LEAGUE_ENABLEMENT
ROUND_3_IMPLEMENTATION
CANDIDATE/FORMAL/LOCK/PRODUCTION_ENABLEMENT
```

## Waiting state

```text
NEXT = AWAIT_OWNER_API_FOOTBALL_PLAN_OR_DATA_SOURCE_DECISION
```

After an owner decision, the next task must define a bounded current-season
capability validation. It must not infer Round-3 or production authority.
