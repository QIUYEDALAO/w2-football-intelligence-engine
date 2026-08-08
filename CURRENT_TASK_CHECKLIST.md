# W2 Current Task Checklist

```text
PROGRAM = W2_FOOTBALL_MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
PRODUCT = W2 Football Intelligence
ROUND_1 = PASS
ROUND_2 = PASS_WITH_TERMINAL_PROVIDER_PLAN_RESTRICTION
ACTIVE_TASK = W2_MI_POST_R2_PROVIDER_ACCESS_AND_DATA_SOURCE_DECISION
ROUND_3 = NOT_STARTED
```

Detailed authority: `POST_R2_PROVIDER_ACCESS_DATA_SOURCE_DECISION.md`.

## Post-R2 access decision

- [ ] Re-fetch latest `origin/main` and `origin/context/current` and record exact SHAs.
- [ ] Inspect the exact code path that converts Provider errors into `PLAN_RESTRICTED`.
- [ ] Verify Round-2 retained sanitized error evidence and account/plan metadata without exposing secrets.
- [ ] Verify current API-Football season semantics, endpoint entitlement and plan rules from official current sources.
- [ ] Check calendar-year vs cross-year league season mapping; do not assume `season=2026` is valid everywhere.
- [ ] Classify root cause as entitlement, season mapping, coverage, account/key mismatch, request/client defect, multiple causes or unresolved.
- [ ] If required, use no more than 8 new read-only diagnostic Provider calls, all ledgered, with no retries/business writes; do not rerun all 17 leagues.
- [ ] If and only if an internal W2 defect is proven, create one bounded fix PR and validate it.
- [ ] If external, do not make a fake code fix.
- [ ] Build current official-source comparison: current API-Football path, upgrade path, alternate full Provider, dedicated odds Provider, hybrid architecture.
- [ ] Record fixture/AH/OU/history/timestamps/bookmaker/lineup/injury/statistics coverage, quota, licensing, current price, monthly cost, engineering effort and operational risk.
- [ ] Mark each capability as `DOCUMENTED`, `VERIFIED_BY_CALL` or `NOT_VERIFIED`.
- [ ] Produce `POST_R2_PROVIDER_ACCESS_ROOT_CAUSE.md`.
- [ ] Produce `POST_R2_DATA_SOURCE_DECISION_MATRIX.md`.
- [ ] Give one preferred recommendation and one fallback.
- [ ] Run `REPOSITORY_HYGIENE_POLICY.md` and remove provably dead diagnostic scratch assets.
- [ ] Keep active whitelist exact 13, four candidates audit-only and Round 3 NOT_STARTED.

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

Expected completion:

```text
POST_R2_ACCESS_DECISION = PASS
NEXT = AWAIT_OWNER_DATA_SOURCE_OR_PROVIDER_SPEND_DECISION
```

If a bounded internal fix fully removes the blocker with no spend/account/source change:

```text
POST_R2_ACCESS_DECISION = PASS_INTERNAL_FIX_VERIFIED
NEXT = AWAIT_OWNER_ROUND_3_AUTHORIZATION
```
