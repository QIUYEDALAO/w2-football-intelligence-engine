# NEXT ACTION

```text
ACTIVE_NEXT_ACTION = W2_MI_POST_R2_PROVIDER_ACCESS_AND_DATA_SOURCE_DECISION
ROUND_1 = PASS
ROUND_2 = PASS_WITH_TERMINAL_PROVIDER_PLAN_RESTRICTION
POST_R2_ACCESS_DECISION = AUTHORIZED_IN_PROGRESS
ROUND_3 = NOT_STARTED
NEXT_CODE_ACTION = CONDITIONAL_ONLY_IF_INTERNAL_W2_DEFECT_IS_PROVEN
```

Current authority:

```text
POST_R2_PROVIDER_ACCESS_DATA_SOURCE_DECISION.md
```

## Owner-confirmed account fact

```text
PAID_SUBSCRIPTION = EXPIRED
CURRENT_EXPECTED_PLAN = FREE
CURRENT_EXPECTED_DAILY_QUOTA = 100
API_KEY_EXPECTED_ACTIVE = true
```

Do not interpret Round-2 `PLAN_RESTRICTED` as API-disabled or quota-exhausted.
API-Football Free remains callable; the first diagnosis is whether Free-plan
season entitlement rejects the Round-2 `season=2026` requests.

## Immediate sequence

```text
1. re-fetch latest origin/main and origin/context/current
2. read POST_R2_PROVIDER_ACCESS_DATA_SOURCE_DECISION.md
3. inspect why all Round-2 rows used season=2026
4. call /status once and verify sanitized plan/active/limit_day
5. select one known cross-year league ID from repo config
6. compare /leagues for season=2026 vs an adjacent supported season such as 2025
7. use a calendar-year control only if necessary
8. stay within 8 total new diagnostic calls; target 3-5; no retries
9. if direct 2026 access works but W2 fails, fix the internal W2 defect in one bounded PR
10. if Free rejects 2026 but an adjacent season works, classify Free-plan season entitlement restriction; do not fake a code fix
11. only then evaluate plan renewal/alternate/hybrid data-source options if current-season data is unavailable
12. run repository hygiene and stop before Round 3
```

## Hard boundaries

```text
ACTIVE_WHITELIST = 13_UNCHANGED
AUDIT_ONLY_CANDIDATES = 4_NOT_ENABLED
MAX_NEW_DIAGNOSTIC_PROVIDER_CALLS = 8
TARGET_NEW_DIAGNOSTIC_PROVIDER_CALLS = 3_TO_5
AUTOMATIC_RETRY = false
BUSINESS_DB_WRITES = 0
CHECKPOINT_WRITES = 0
PRODUCTION_PROVIDER_CUTOVER = NOT_AUTHORIZED
PROVIDER_PURCHASE_OR_PLAN_CHANGE = NOT_AUTHORIZED
PRODUCTION_SCHEDULER_CHANGE = false
PERSISTENT_COLLECTION_EXPANSION = false
ROUND_3 = NOT_STARTED
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
```

No new owner authorization is needed for this bounded diagnosis or a proven
internal-defect fix. Spending, subscription/account changes, Provider cutover,
production collection changes, league enablement and Round 3 still require a
new explicit owner decision.
