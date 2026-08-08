# W2 Current Task Checklist

```text
PROGRAM = W2_FOOTBALL_MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
PRODUCT = W2 Football Intelligence
ROUND_1 = PASS
ROUND_2 = PASS_WITH_TERMINAL_PROVIDER_PLAN_RESTRICTION
POST_R2_ACCESS_DECISION = PASS_FREE_PLAN_SEASON_RESTRICTION_CONFIRMED
ACTIVE_TASK = AWAIT_OWNER_FREE_BRIDGE_PR_REVIEW_AND_CONTROLLED_ACTIVATION_DECISION
FREE_PLAN_FIXTURE_CENTRIC_VALIDATION = FREE_FIXTURE_CENTRIC_CURRENT_DATA_WORKS
FREE_PLAN_IDS_PARAMETER = PLAN_RESTRICTED
BRIDGE_PR = 495_OPEN_CI_PASS_DISABLED_BY_DEFAULT
ROUND_3 = NOT_STARTED
```

## Completed Free-plan fixture-centric bridge

- [x] Re-fetched latest `origin/main` and `origin/context/current`; used
  `b04dcc7e521dce413740bcf754b1a45755a3e83e` and
  `8cbbba09199b7178808b4b9f3a85a9a5b240b771` as execution bases.
- [x] Read the task authorities in the required order.
- [x] Used the existing active Free account; no purchase, renewal or account
  change occurred.
- [x] Called `/fixtures?date=2026-08-08` without `season`; obtained 1,153
  fixtures and 25 current target-league matches.
- [x] Selected real fixture 1493055 in Argentina Primera, league 128,
  response season 2026.
- [x] Verified fixture detail by `id`.
- [x] Verified `/odds?fixture=1493055`: 14 bookmakers with AH and OU present.
- [x] Verified fixture-scoped statistics, including xG fields in this control.
- [x] Did not test live odds because the fixture was full-time.
- [x] Proved Free rejects the `ids` parameter and retained single-`id` as the
  default bridge behavior.
- [x] Attempted exactly five Provider calls, no retries or writes; final
  confirmed daily remaining header was 96.
- [x] Classified `FREE_FIXTURE_CENTRIC_CURRENT_DATA_WORKS` with caveat
  `FREE_PLAN_IDS_PARAMETER_RESTRICTED`.
- [x] Created bounded PR
  [#495](https://github.com/QIUYEDALAO/w2-football-intelligence-engine/pull/495)
  at head `d73882dcee3c37819f248f6048bc2308c146feb1`, disabled by default.
- [x] Reused formal raw payload, endpoint capture, fixture identity and AH/OU
  normalization; added no duplicate data model.
- [x] Added request-key cache reuse, fixture-ID de-duplication,
  capability-gated 20-ID batching, quota planning and no-idle-polling.
- [x] Passed 43 focused/contract tests, full Ruff, strict mypy on 278 source
  files and all required PR Fast CI checks.
- [x] Generated `FREE_PLAN_FIXTURE_CENTRIC_VALIDATION.md` and
  `FREE_PLAN_DAILY_CALL_BUDGET.md`.
- [x] Executed repository hygiene and removed both transient one-shot
  diagnostic scripts after retaining their sanitized evidence.
- [x] Kept active whitelist exact 13, PR unmerged, runtime disabled and Round 3
  not started.

## Previously completed Post-R2 access decision

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
DEAD_ASSETS_FOUND = 2_TRANSIENT_DIAGNOSTIC_SCRIPTS
DEAD_ASSETS_DELETED = 2_TRANSIENT_DIAGNOSTIC_SCRIPTS
OBSOLETE_CODE_LINES_REMOVED = 0
RETAINED_FOR_EVIDENCE = 2_FREE_BRIDGE_REPORTS_PLUS_SANITIZED_LEDGER_SUMMARY
UNRESOLVED_HYGIENE_ITEMS = 0
```

## Not authorized

```text
PURCHASE_OR_PLAN_CHANGE
CREDENTIAL_REPLACEMENT
PROVIDER_CUTOVER
ADDITIONAL_PROVIDER_VALIDATION_CALLS
PR_495_MERGE_OR_RUNTIME_ACTIVATION
PRODUCTION_SCHEDULER_CHANGE
PERSISTENT_COLLECTION_EXPANSION
LEAGUE_ENABLEMENT
ROUND_3_IMPLEMENTATION
CANDIDATE/FORMAL/LOCK/PRODUCTION_ENABLEMENT
```

## Waiting state

```text
NEXT = AWAIT_OWNER_FREE_BRIDGE_PR_REVIEW_AND_CONTROLLED_ACTIVATION_DECISION
```

After an owner decision, a later task may define bounded PR merge and controlled
activation acceptance. It must not infer Scheduler, persistent-collection,
league-expansion, production or Round-3 authority.
