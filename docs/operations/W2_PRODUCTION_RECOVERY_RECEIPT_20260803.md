# W2 Production Recovery Receipt — 2026-08-03

This receipt is intentionally sanitized. It contains no host address, public URL, database name,
credential, API key, fixture identifier, raw payload, container identifier, or unredacted log.

```text
CURRENT_MAIN_SHA = 3b38e283959394459671e441132c1e1cb9d1f019
DEPLOYED_SHA = 3b38e283959394459671e441132c1e1cb9d1f019
MAIN_POST_MERGE_CI_RUN = 30761641987
MAIN_POST_MERGE_CI = PASS

DASHBOARD_REAL_DATA_RECOVERY = PASS
PUBLIC_DASHBOARD_CARDS = 51
PRODUCTION_FUTURE_FIXTURES = 51
PROVIDER_REQUEST_DELTA = 58
ENDPOINT_CAPTURE_DELTA = 58
PROVIDER_ERRORS = 0
PROVIDER_LEDGER_RECONCILED = true
STAGING_SEED_USED = false

COLLECTION_READY_COMPETITIONS =
- brasileirao_serie_a
- chinese_super_league
- allsvenskan
- eliteserien

PERSISTENT_SCHEDULER = ON_CONTROLLED
SCHEDULER_CONCURRENCY = 1
PROVIDER_ATTEMPTS = 1
DAILY_HARD_CAP = 120
TICK_HARD_CAP = 30

DYNAMIC_EVALUATION_V2 = 0
EXPLICIT_NOT_READY_CARDS = 51
DYNAMIC_EVALUATION_PRODUCTION_RECOVERY = PENDING

CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF

ACTIVE_NEXT_ACTION = POST_RECOVERY_OBSERVATION_AND_DYNAMIC_EVALUATION_READINESS
EVAL-03 = NOT STARTED
COLD_PULL_SLO = NOT_PROVEN

REGISTERED_COMPETITIONS_MISSING_FUTURE_REFRESH_AND_MATCHDAY_POLICY =
- argentina_primera
- bundesliga
- eredivisie
- la_liga
- ligue_1
- mls
- premier_league
- primeira_liga
- serie_a

CONTEXT_CLOSURE_PROVIDER_CALL_DELTA = 0
SCHEDULER_RESTARTED_IN_CONTEXT_CLOSURE = false
DEPLOYMENT_EXECUTED_IN_CONTEXT_CLOSURE = false
AUTO_MERGE_EXECUTED = false
```

The 58 successful Provider request-ledger rows reconcile one-for-one with 58 endpoint captures;
no Provider error was recorded in the recovery window. The persistent scheduler remains limited to
the four collection-ready competitions and retains attempts=1, concurrency=1, dedupe, ledger, and
the existing hard caps. The remaining registered competitions stay registered and await both
future-refresh and matchday policy coverage.
