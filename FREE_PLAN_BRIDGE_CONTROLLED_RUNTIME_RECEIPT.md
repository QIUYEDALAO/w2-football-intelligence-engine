# W2 Free-Plan Bridge Controlled Runtime Receipt

```text
TASK = W2_MI_FREE_PLAN_BRIDGE_CONTROLLED_RUNTIME_CLOSURE
RESULT = PASS
COMPLETED_AT = 2026-08-08T15:48:04+08:00
FINAL_RUNTIME_MODE = SHADOW_ONLY
NEXT = AWAIT_OWNER_ROUND_3_OR_BIG_FIVE_COLLECTION_DECISION
```

## Source, PR and release identity

```text
PR_495_FINAL_HEAD_SHA = 5d1761106d1bc1b9c55e1ef923b5603ef490c027
PR_495_MERGE_SHA = eccab2542fa68bb0ae557e6f073dfdd927297f07
PR_495_FAST_RUN = 31243587294_PASS
PR_495_RC_RUN = 31243634507_PASS

RUNTIME_INTEGRATION_PR = 496
RUNTIME_INTEGRATION_FINAL_HEAD_SHA = a55111b4955f70c84539ac44d07858a8d80e7f81
RUNTIME_INTEGRATION_MERGE_SHA = c241b877a4168659f465163108f7a53fb8fd82a5
RUNTIME_INTEGRATION_FAST_RUN = 31245930860_PASS
RUNTIME_INTEGRATION_RC_RUN = 31245956775_PASS

FINAL_MAIN_SHA = c241b877a4168659f465163108f7a53fb8fd82a5
MAIN_PROMOTION_RUN = 31246227027_PASS
MAIN_RELEASE_CANDIDATE_RUN = 31246238966_PASS
IMMUTABLE_MANIFEST_SHA256 = 80dba9cb96f8cc0cea7ff71400821813ef3b15def9090f66a315db6c0b258235
DEPLOYED_SOURCE_SHA = c241b877a4168659f465163108f7a53fb8fd82a5
DEPLOYED_PYTHON_DIGEST = sha256:8c71abd5ccc3d946fdc3365e9ce863789b3081ecc8e73fa90d61b088d972abaf
DEPLOYED_WEB_DIGEST = sha256:ceea1489dee6a43aff648f27dc36a6c7d572819569c95f9057580c24385d87d1
DEPLOYMENT = PASS_COLD_PULL_185_SECONDS
SERVICE_HEALTH = PASS_API_POSTGRES_REDIS_SCHEDULER_WEB_WORKER
```

PR #495 fixed the double-reserve defect before merge. The accepted semantics
are Provider limit 100, W2 daily ceiling 80 and minimum Provider remaining 20;
the effective W2 ceiling is 80, not 60.

PR #496 is the only runtime-integration PR. It wires the bridge into the
existing worker/scheduler and existing persistence contracts. No second daemon,
duplicate fixture/market/raw/quota model or new dependency was introduced.

## Verification gates

```text
LOCAL_FULL_SUITE = 2464_PASSED_13_SKIPPED
RUFF = PASS
MYPY_STRICT = PASS_279_SOURCE_FILES
SECRET_SCAN = PASS
DIFF_CHECK = PASS
DEVELOPER_CHECK = PASS
PR_FAST = PASS
RELEASE_CANDIDATE = PASS
FULL_IMAGE_SMOKE = PASS
PROVIDER_CALLS_DURING_CI = 0
```

One earlier PR #496 RC attempt exposed two compose baseline assertions and was
cancelled. The assertions were updated to recognize the explicitly accepted
`W2_FREE_BRIDGE_MODE=OFF` default and 300-second interval; all completed jobs
in that attempt had passed. The final exact implementation was re-run through
Fast and Release Candidate gates and passed.

## Real Free-plan shadow acceptance

```text
PROVIDER_PLAN = FREE
PROVIDER_DAILY_LIMIT = 100
W2_DAILY_CALL_CEILING = 80
MIN_PROVIDER_DAILY_REMAINING = 20
SHARED_LEDGER_STATUS = PASS_PERSISTENT_AND_RESTART_SAFE
SHARED_LEDGER_BEFORE = 26
SHARED_LEDGER_AFTER = 28
REAL_VALIDATION_CALLS = 2
TASK_CALL_HARD_CAP = 20
AUTOMATIC_RETRIES = 0
FINAL_PROVIDER_REMAINING = 93
```

The controlled run kept scheduler mode `OFF` and enabled only the worker,
preventing concurrent acceptance traffic. It performed:

1. `fixtures?date=2026-08-08`, with no `season`;
2. `odds?fixture=1575448`, with one fixture ID and no batching.

The result was `SHADOW_COMPLETE` with no blockers.

```text
TARGET_FIXTURE_ID = 1575448
TARGET_COMPETITION = primeira_liga
TARGET_PROVIDER_LEAGUE_ID = 94
TARGET_RESPONSE_SEASON = 2026
TARGET_FIXTURE_STATUS = NS
CANONICAL_FIXTURE_IDENTITY = PASS
TARGET_BOOKMAKERS = 14
NORMALIZED_1X2_ROWS = 42
NORMALIZED_AH_ROWS = 182
NORMALIZED_OU_ROWS = 240
RAW_CAPTURE_QUOTE_LINEAGE_ROWS = 464
```

The acceptance added two raw payloads and two endpoint captures. Existing
identity reconciliation changed the total fixture-identity count from 111 to
124, while all 25 current target rows were processed. Market observations
changed from 65,173 to 65,637, exactly the 464 normalized rows above.

Every target market row joined to its endpoint capture and raw payload, retained
bookmaker identity, Provider quote update time and capture time, and used source
revision `c241b877…`.

Lineups were not due for the selected fixture, so the runtime used zero lineup
calls. Automatic statistics collection is disabled; postmatch state is
recorded without manufacturing a statistics call.

## Cache, cadence and idle-polling proof

```text
CACHE_DEDUPE_STATUS = PASS
DIRECT_CACHE_RERUN_PROVIDER_CALLS = 0
DIRECT_CACHE_RERUN_IDENTITY_WRITES = 0
DIRECT_CACHE_RERUN_MARKET_WRITES = 0
POST_RESTART_SCHEDULER_PROVIDER_CALLS = 0
DISCOVERY_CACHE_REASON = DISCOVERY_CACHED_NO_CALL
ODDS_CACHE_REASON = FRESH_CAPTURE_CACHE_HIT
IDLE_POLLING_STATUS = PASS
IDS_BATCHING = false
```

The first live run selected one genuinely due market checkpoint and made odds
higher priority than optional enrichment. The immediate rerun reused discovery
and odds captures. After worker/scheduler restart, the next persisted audit
also recorded zero calls. Tests additionally cover the no-due-target path and
prove zero fixture follow-up calls.

Persisted bridge audits were:

```text
2026-08-08T07:46:03Z calls=2 fixtures=25 market_rows=464 remaining=93 blockers=0
2026-08-08T07:46:44Z calls=0 fixtures=25 market_rows=0 remaining=93 blockers=0
2026-08-08T07:48:04Z calls=0 fixtures=25 market_rows=0 remaining=93 blockers=0
```

## Whitelist, product and rollback proof

```text
ACTIVE_WHITELIST_BEFORE_AFTER = 13_TO_13
AUDIT_ONLY_RUNTIME_REACHABILITY = 0
SHADOW_MODE = SHADOW_ONLY
ROLLBACK_MECHANISM = ONE_STEP_FEATURE_FLAG
ROLLBACK_STATUS = PASS
DISABLE_BRIDGE_STOPS_NEW_BRIDGE_CALLS = true
ROLLBACK_DOES_NOT_CHANGE_13_WHITELIST = true
ROLLBACK_DOES_NOT_DELETE_VALID_EXISTING_EVIDENCE = true
```

The rollback run switched `W2_FREE_BRIDGE_MODE` to `OFF`, recreated the
worker, and returned `DISABLED` with zero Provider-call delta. Raw payload,
capture, fixture-identity and market-observation counts stayed exactly
`544|475|124|65637` before and after. The bridge was then restored to
`SHADOW_ONLY` and both worker and scheduler were recreated successfully.

The final active whitelist is:

```text
premier_league
la_liga
bundesliga
serie_a
ligue_1
brasileirao_serie_a
argentina_primera
mls
chinese_super_league
allsvenskan
eliteserien
eredivisie
primeira_liga
```

Its intersection with `belgian_pro_league`, `turkish_super_lig`,
`greek_super_league` and `scottish_premiership` is empty.

```text
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
RECOMMENDATION_ROWS = 0
RECOMMENDATION_LOCK_ROWS = 0
ROUND_3 = NOT_STARTED
```

## Repository hygiene

The changed assets were classified as follows:

- `KEEP`: bridge planner/quota fix, runtime integration, existing scheduler
  and worker wiring, persistence methods, compose feature flags, tests and
  runbook. Each remains referenced by runtime, deployment, verification or
  rollback.
- `RETAIN_FOR_EVIDENCE`: authorization, acceptance, validation, budget,
  immutable manifests/CI records and this final receipt.
- `DELETE`: none. No one-off diagnostic script, duplicate model, superseded
  fixture/config, tracked scratch output or obsolete helper was introduced by
  the accepted PRs.

```text
REPOSITORY_HYGIENE = PASS
DEAD_ASSETS_FOUND = 0
DEAD_ASSETS_DELETED = 0
OBSOLETE_CODE_LINES_REMOVED = 0
RETAINED_FOR_EVIDENCE = BRIDGE_IMPLEMENTATION_TESTS_RUNBOOK_AND_FINAL_RECEIPT
UNRESOLVED_HYGIENE_ITEMS = 0
```

Ignored local virtual environments and tool caches were not tracked or included
in the immutable release.

## Final state

```text
FREE_PLAN_BRIDGE_CONTROLLED_RUNTIME = PASS
FREE_BRIDGE_MODE = SHADOW_ONLY
API_FOOTBALL_PRO_RENEWAL = NOT_REQUIRED_NOW
ACTIVE_WHITELIST = 13_UNCHANGED
REPOSITORY_HYGIENE = PASS
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
ROUND_3 = NOT_STARTED
NEXT = AWAIT_OWNER_ROUND_3_OR_BIG_FIVE_COLLECTION_DECISION
```

This bridge is shadow data infrastructure only. It does not establish betting
edge, authorize real-money behavior, enable a recommendation tier or start
Round 3.
