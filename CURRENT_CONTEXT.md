# W2 Current Context

Current mutable authority is `origin/context/current`.

## Current decision

```text
PRODUCT = W2 Football Intelligence
ROUND_1 = PASS
ROUND_2 = PASS_WITH_TERMINAL_PROVIDER_PLAN_RESTRICTION
FREE_PLAN_BRIDGE_CONTROLLED_RUNTIME = PASS
ROUND_3 = PASS_MARKET_RADAR_MODEL_LAB
ACTIVE_NEXT_ACTION = AWAIT_OWNER_POST_R3_PRODUCT_DECISION
FREE_BRIDGE_MODE = SHADOW_ONLY
ACTIVE_WHITELIST = 13_UNCHANGED
```

Read current authority in this order:

```text
1. CURRENT_STATE.yaml
2. NEXT_ACTION.md
3. ROUND_3_FINAL_RECEIPT.md
4. ROUND_3_DASHBOARD_REALITY_AND_VISUAL_SEMANTICS_ADDENDUM.md
5. REPOSITORY_HYGIENE_POLICY.md
```

## Closed Round 3

Round 3 started from exact main `c241b877a4168659f465163108f7a53fb8fd82a5`.
PR #497 ended at head `51ebbeabc5497ce48708b3587705e2922c4805da`
and merged as main SHA `f0fe9d332d05a84f1ef04be86fd9fb44b69d69e3`.
PR Fast, full Release Candidate, Main Promotion, immutable deployment, real
persisted-evidence acceptance and non-destructive rollback all passed.

The active public chain is `/ -> DashboardPage -> IntelligenceConsole`.
Legacy recommendation components have zero runtime reachability from the public
root. Market Radar now reports real sparse-safe AH/OU facts and movement only
when 2+ comparable snapshots exist. Model Lab is diagnostic-only, uses warning
semantics and exposes the frozen Phase 0.5 `NO_EDGE / FAIL / 7566 / -5.32% /
NOT_PROVEN` context without rerunning Phase 0.5.

The production read path is the existing frozen shadow checkpoint authority.
All 69 shadow artifacts contain Round-3 data; a live public future DayView read
returned 64 cards, 14,784 eligible observations and zero Provider calls or DB
writes. No recommendation or recommendation-lock rows exist.

The deployed source is `51ebbeab…`, the exact active whitelist remains 13 and
the accepted Free bridge is restored to `SHADOW_ONLY`. The code default remains
`OFF`; the deployment feature flag is the one-step rollback control. No
collection cadence or allowlist was expanded for the UI.

Complete evidence is in `ROUND_3_FINAL_RECEIPT.md`.

## Stop line

Wait for an Owner post-Round-3 product decision. Do not start another round,
reopen Phase 0.5/H, buy or switch Provider access, expand the whitelist or
collection cadence, introduce betting/value/opportunity semantics, or enable
Candidate/Formal/Lock/Production/real-money behavior.
