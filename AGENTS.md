# W2 Repository Agent Instructions

Current task authority is `origin/context/current`.

Read first:

```text
1. CURRENT_STATE.yaml
2. NEXT_ACTION.md
3. FREE_PLAN_FIXTURE_CENTRIC_BRIDGE.md
4. POST_R2_PROVIDER_ACCESS_ROOT_CAUSE.md
5. POST_R2_DATA_SOURCE_DECISION_MATRIX.md
6. ROUND_2_FINAL_RECEIPT.md
7. REPOSITORY_HYGIENE_POLICY.md
```

```text
PRODUCT = W2 Football Intelligence
ROUND_1 = PASS
ROUND_2 = PASS_WITH_TERMINAL_PROVIDER_PLAN_RESTRICTION
POST_R2_ACCESS_DECISION = PASS_FREE_PLAN_SEASON_RESTRICTION_CONFIRMED
ACTIVE_NEXT_ACTION = W2_MI_FREE_PLAN_FIXTURE_CENTRIC_BRIDGE
OWNER_DECISION = DO_NOT_RENEW_API_FOOTBALL_PRO_NOW
ROUND_3 = NOT_STARTED
```

Current job: determine whether the active API-Football Free account can provide current-season W2 data through no-season fixture-centric request shapes (`fixtures?date`, `fixtures?live`, fixture IDs, odds by fixture/date, injuries/statistics by fixture) even though league+season enumeration for 2025/2026 is plan-restricted.

Use the existing Free account only. Target 5-8 new calls, hard max 12, no retries, daily W2 hard cap 80 and reserve at least 20. Do not repeat the 17-league season audit.

If a useful fixture-centric path is proven, one bounded bridge PR is authorized, disabled by default, reusing existing W2 raw/identity/market contracts and adding quota planning/cache/deduplication rather than a parallel data model.

If current fixture-centric access is also blocked, do not ask for Pro renewal merely to keep engineering moving; proceed to the zero-cost/low-cost source bridge decision defined in `FREE_PLAN_FIXTURE_CENTRIC_BRIDGE.md`.

No Provider purchase/renewal, production activation, Scheduler change, persistent collection expansion, league enablement or Round 3 is authorized by this validation alone.

Every task must pass `REPOSITORY_HYGIENE_POLICY.md` before PASS. Permanent guards remain: active whitelist 13 unless separately authorized; intelligence-first; no betting-edge/opportunity claim; Candidate/Formal/Lock/Production OFF; H permanently closed; no real-money execution.