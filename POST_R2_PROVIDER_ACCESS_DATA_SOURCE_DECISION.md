# W2 Post-R2 — Provider Access Root Cause & Data-Source Decision

```text
TASK = W2_MI_POST_R2_PROVIDER_ACCESS_AND_DATA_SOURCE_DECISION
OWNER_DECISION = APPROVED_EXECUTE_NOW
ROUND_1 = PASS
ROUND_2 = PASS_WITH_TERMINAL_PROVIDER_PLAN_RESTRICTION
ROUND_3 = NOT_STARTED
```

## Owner-confirmed account fact — binding

The previous paid API-Football subscription has expired, but the account still has the normal Free-plan quota.

```text
PAID_SUBSCRIPTION = EXPIRED
CURRENT_EXPECTED_PLAN = FREE
CURRENT_EXPECTED_DAILY_QUOTA = 100
API_KEY_EXPECTED_ACTIVE = true
```

Official current API-Football material states that an expired dashboard subscription returns to the Free plan; Free has 100 requests/day and access to all endpoints/competitions, while Free is limited by available seasons.

Therefore:

```text
PLAN_RESTRICTED != API_DISABLED
PLAN_RESTRICTED != DAILY_QUOTA_EXHAUSTED
```

The primary hypothesis to test first is **Free-plan season entitlement / audit-season mismatch**, especially because Round 2 queried `season=2026` for all 17 rows.

Do not begin with Provider replacement research until this hypothesis is resolved.

## Goal

Resolve why all 17 Round-2 rows stopped at `PLAN_RESTRICTED`, then decide whether any data-source change is actually necessary before Round 3.

This is a root-cause and source-decision gate. It is not authorization to purchase a plan, switch Provider, expand Scheduler coverage, enable leagues, or start Round 3.

## Evidence first

Use code, config, tests, sanitized Round-2 Provider evidence, exact runtime/account metadata without exposing secrets, and current official Provider documentation/pricing/licensing sources.

Read first:

```text
CURRENT_STATE.yaml
NEXT_ACTION.md
ROUND_2_FINAL_RECEIPT.md
ROUND_2_FINAL_CAPABILITY_MATRIX.json
ROUND_2_DAY0_RECEIPT.md
src/w2/competitions/league_whitelist_provider_audit.py
scripts/run_w2_league_whitelist_audit.py
config/audit_candidates/round2_first_divisions.v1.json
REPOSITORY_HYGIENE_POLICY.md
```

## Phase A — resolve Free-plan access and season entitlement first

Determine which classification is actually supported:

```text
FREE_PLAN_SEASON_ENTITLEMENT_RESTRICTION
SEASON_PARAMETER_OR_SEASON_MAPPING_DEFECT
ACCOUNT_OR_KEY_ENTITLEMENT_MISMATCH
PROVIDER_COVERAGE_GAP
REQUEST_SHAPE_OR_CLIENT_DEFECT
MULTIPLE_CAUSES
UNRESOLVED
```

Required checks:

1. inspect the exact sanitized Provider error payload classification and how `_provider_payload_error` / plan-restriction handling is triggered;
2. inspect why the Round-2 audit selected `season=2026` for all 17 rows;
3. distinguish calendar-year leagues from cross-year European leagues;
4. verify whether the current account really reports `plan=Free`, active access and `limit_day=100`;
5. verify whether the same Free account can access an adjacent supported season for a known league while `season=2026` is restricted;
6. determine whether W2's season strategy is correct for current fixtures and competitions;
7. do not infer that 100 requests/day implies every season is accessible — quota and season entitlement are separate dimensions.

### Minimal controlled diagnostic calls

Use the minimum calls required. The preferred sequence is:

```text
CALL_1 = GET /status
```

Record only sanitized fields:

```text
subscription.plan
subscription.active
requests.current
requests.limit_day
rate-limit remaining headers
```

Then choose one known cross-year European league from current repository config and test only the minimum season controls required, for example:

```text
CALL_2 = GET /leagues?id=<known_repo_provider_league_id>&season=2026
CALL_3 = GET /leagues?id=<same_id>&season=2025
```

Do not guess the league ID; read it from current repository config.

If needed, use one calendar-year league as a second control. Total new calls remain bounded:

```text
MAX_NEW_DIAGNOSTIC_PROVIDER_CALLS = 8
TARGET_DIAGNOSTIC_CALLS = 3_TO_5
AUTOMATIC_RETRY = false
BUSINESS_DB_WRITES = 0
CHECKPOINT_WRITES = 0
PRODUCTION_SCHEDULER_CHANGES = 0
ACTIVE_WHITELIST_CHANGES = 0
```

Do not rerun the 17-league audit batch.

### Decision logic

If `/status` confirms Free + 100/day and a supported adjacent season succeeds while `season=2026` returns plan restriction:

```text
ROOT_CAUSE = FREE_PLAN_SEASON_ENTITLEMENT_RESTRICTION
INTERNAL_W2_FIX_REQUIRED = false
```

Do not create a code PR merely to suppress the Provider restriction.

If `season=2026` succeeds with the same account/key in a direct controlled call but W2 still classifies it as plan-restricted:

```text
ROOT_CAUSE = REQUEST_SHAPE_OR_CLIENT_DEFECT or SEASON_PARAMETER_OR_SEASON_MAPPING_DEFECT
INTERNAL_W2_FIX_REQUIRED = true
```

Then a bounded internal fix PR is authorized.

If both adjacent/current seasons are restricted, use `/status`, official current plan docs and the exact sanitized Provider response to classify account/season entitlement before considering a Provider change.

## Phase B — conditional bounded internal fix

If and only if evidence proves an internal W2 season/request/configuration defect, Codex may:

1. create one bounded fix PR from latest `origin/main`;
2. make the smallest correction to season/request/audit logic;
3. keep active whitelist exact 13 and four new leagues audit-only;
4. run focused/full required tests, PR Fast and required release-quality checks;
5. use only the remaining diagnostic-call budget for exact post-fix validation;
6. apply `REPOSITORY_HYGIENE_POLICY.md` before declaring the fix complete.

Do not change Provider plan, production Provider allowlist, production Scheduler cadence, league enablement, Candidate/Formal/Lock/Production or Round-3 logic.

## Phase C — data-source decision only if still necessary

Do **not** automatically research replacement Providers just because the paid plan expired.

First determine whether the current Free path is technically usable for the current-season data W2 needs.

If current-season access is unavailable under Free and W2 requires it, compare:

```text
OPTION_A = renew/upgrade API-Football
OPTION_B = alternate full football-data Provider
OPTION_C = dedicated odds/market Provider plus API-Football Free/paid football data
OPTION_D = hybrid multi-source architecture
```

For each viable option record, from current official primary sources:

```text
fixture coverage for target 17
AH coverage
OU coverage
historical odds availability
pre-match odds timestamps / snapshots
bookmaker depth
lineups
injuries
statistics / xG-capable inputs
rate limits / quota model
required tier and current price
commercial/licensing restrictions
expected monthly recurring cost
implementation effort
identity/mapping migration cost
schema/normalization work
operational reliability risk
vendor-lock-in risk
Market Radar support
Model Diagnostics support
```

Separate `DOCUMENTED`, `VERIFIED_BY_CALL`, and `NOT_VERIFIED`.

## Decision output

Create/update:

```text
POST_R2_PROVIDER_ACCESS_ROOT_CAUSE.md
POST_R2_DATA_SOURCE_DECISION_MATRIX.md
```

Final result must contain:

```text
CURRENT_PLAN_VERIFIED
CURRENT_DAILY_QUOTA_VERIFIED
FREE_PLAN_CURRENT_SEASON_ACCESS
ROOT_CAUSE_CLASSIFICATION
ROOT_CAUSE_CONFIDENCE
NEW_DIAGNOSTIC_PROVIDER_CALLS
INTERNAL_FIX_REQUIRED
INTERNAL_FIX_PR if any
CURRENT_API_FOOTBALL_PATH_VIABLE
RECOMMENDED_PRIMARY_DATA_SOURCE_PATH
RECOMMENDED_FALLBACK_PATH
ESTIMATED_MONTHLY_DATA_COST
BLOCKERS_REQUIRING_OWNER_SPEND_OR_ACCOUNT_CHANGE
ROUND_3_DATA_PREREQUISITES
```

## Stop line

No purchase/subscription change, credential replacement, Provider cutover, production deployment, Scheduler expansion, league promotion, persistent collection expansion, or Round 3 implementation is authorized.

Permanent guards:

```text
ACTIVE_WHITELIST = 13_UNCHANGED
AUDIT_ONLY_CANDIDATES = 4_NOT_ENABLED
MODEL_MARKET_DIVERGENCE != MARKET_OPPORTUNITY
BETTING_EDGE_CLAIM = FORBIDDEN
H_RESULT_ACCESS = PERMANENTLY_CLOSED
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
ROUND_3 = NOT_STARTED
REAL_MONEY = NOT_AUTHORIZED
```

## Completion and hygiene

Before PASS, execute `REPOSITORY_HYGIENE_POLICY.md`. Remove provably dead diagnostic scratch code/files/assets and stale references; retain reusable validated audit tooling and required receipts/evidence.

Expected completion if Free-plan season entitlement explains the blocker:

```text
POST_R2_ACCESS_DECISION = PASS_FREE_PLAN_SEASON_RESTRICTION_CONFIRMED
ROUND_3 = NOT_STARTED
NEXT = AWAIT_OWNER_API_FOOTBALL_PLAN_OR_DATA_SOURCE_DECISION
```

If a bounded internal W2 fix fully removes the blocker:

```text
POST_R2_ACCESS_DECISION = PASS_INTERNAL_FIX_VERIFIED
ROUND_3 = NOT_STARTED
NEXT = AWAIT_OWNER_ROUND_3_AUTHORIZATION
```
