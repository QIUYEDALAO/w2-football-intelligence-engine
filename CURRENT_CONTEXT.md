# W2 Current Context

Current mutable authority is `origin/context/current`.

## Current decision

```text
PRODUCT = W2 Football Intelligence
ROUND_1 = PASS
ROUND_2 = PASS_WITH_TERMINAL_PROVIDER_PLAN_RESTRICTION
ACTIVE_NEXT_ACTION = AWAIT_OWNER_API_FOOTBALL_PLAN_OR_DATA_SOURCE_DECISION
POST_R2_ACCESS_DECISION = PASS_FREE_PLAN_SEASON_RESTRICTION_CONFIRMED
ROUND_3 = NOT_STARTED
```

Read current execution authority in this order:

```text
1. CURRENT_STATE.yaml
2. NEXT_ACTION.md
3. POST_R2_PROVIDER_ACCESS_ROOT_CAUSE.md
4. POST_R2_DATA_SOURCE_DECISION_MATRIX.md
5. POST_R2_PROVIDER_ACCESS_DATA_SOURCE_DECISION.md
6. ROUND_2_FINAL_RECEIPT.md
7. ROUND_2_FINAL_CAPABILITY_MATRIX.json
8. REPOSITORY_HYGIENE_POLICY.md
```

Round 2 is closed: 17/17 Provider rows are `PLAN_RESTRICTED`, 17/17 temporal evidence is insufficient, zero rows are promotion-authorized, and the runtime whitelist remains exact 13.

The Post-R2 diagnosis is complete. Four controlled read-only calls verified an active API-Football Free account with 100 requests/day, rejected Premier League seasons 2025 and 2026 under `errors.plan`, and successfully returned season 2024. The root cause is `FREE_PLAN_SEASON_ENTITLEMENT_RESTRICTION`, not API disablement, quota exhaustion, key failure, Provider coverage, or a W2 season/request/client defect. No code fix or PR was created.

The preferred data-source path is API-Football Pro renewal at the current official USD 19/month followed by bounded current-season revalidation. The fallback is Sportmonks Growth plus Premium Odds after a coverage trial, currently EUR 228/month before VAT, or an indicative EUR 252/month with its xG bundle. Neither purchase nor trial was executed.

Current authority is waiting for an explicit owner plan/source and spend decision. A future purchase does not itself authorize Provider cutover, persistent collection, Scheduler changes, league enablement, or Round 3.

Permanent guards remain: intelligence-first semantics; active whitelist 13 unless separately authorized; V4 diagnostic-only; no betting-edge/opportunity claim; Candidate/Formal/Lock/Production OFF; H permanently closed; no real-money execution; Round 3 not started.
