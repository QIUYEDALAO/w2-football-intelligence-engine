# W2 Current Context

Current mutable authority is `origin/context/current`.

## Current decision

```text
PRODUCT = W2 Football Intelligence
ROUND_1 = PASS
ROUND_2 = PASS_WITH_TERMINAL_PROVIDER_PLAN_RESTRICTION
ACTIVE_NEXT_ACTION = AWAIT_OWNER_FREE_BRIDGE_PR_REVIEW_AND_CONTROLLED_ACTIVATION_DECISION
POST_R2_ACCESS_DECISION = PASS_FREE_PLAN_SEASON_RESTRICTION_CONFIRMED
FREE_PLAN_FIXTURE_CENTRIC_VALIDATION = FREE_FIXTURE_CENTRIC_CURRENT_DATA_WORKS
BRIDGE_PR = 495_OPEN_CI_PASS_DISABLED_BY_DEFAULT
ROUND_3 = NOT_STARTED
```

Read current execution authority in this order:

```text
1. CURRENT_STATE.yaml
2. NEXT_ACTION.md
3. FREE_PLAN_FIXTURE_CENTRIC_BRIDGE.md
4. FREE_PLAN_FIXTURE_CENTRIC_VALIDATION.md
5. FREE_PLAN_DAILY_CALL_BUDGET.md
6. POST_R2_PROVIDER_ACCESS_ROOT_CAUSE.md
7. REPOSITORY_HYGIENE_POLICY.md
```

Round 2 is closed: 17/17 Provider rows are `PLAN_RESTRICTED`, 17/17 temporal evidence is insufficient, zero rows are promotion-authorized, and the runtime whitelist remains exact 13.

The Post-R2 season diagnosis remains complete and correct. Four earlier controlled calls proved `FREE_PLAN_SEASON_ENTITLEMENT_RESTRICTION`: Premier League seasons 2025/2026 were rejected and 2024 succeeded on the active Free account.

The subsequent owner-authorized no-season proof used exactly five more read-only calls with no retry or writes. `/fixtures?date=2026-08-08` returned 1,153 fixtures, including 25 mapped to existing W2 target league IDs. Fixture 1493055 was a real Argentina Primera season-2026 match. Its detail, 14-bookmaker odds response with AH/OU, and fixture statistics all succeeded. Free rejected only the multi-fixture `ids` parameter. The final confirmed remaining header was 96.

The supported result is `FREE_FIXTURE_CENTRIC_CURRENT_DATA_WORKS` with caveat `FREE_PLAN_IDS_PARAMETER_RESTRICTED`. Paid API-Football is not a current engineering prerequisite.

PR #495 implements a bounded bridge planner and replay adapter. It is open, mergeable, Fast-CI green and disabled by default. It reuses formal raw payload, endpoint capture, fixture identity and AH/OU normalization contracts; it adds local fixture-id de-duplication, request-key cache reuse, capability-gated batching, a conservative quota planner and no-idle-polling. It does not wire the Scheduler or production runtime.

Current authority is waiting for owner review and a separate controlled merge/activation decision. PR merge, Provider cutover, persistent collection, Scheduler changes, league enablement and Round 3 were not executed or inferred.

Permanent guards remain: intelligence-first semantics; active whitelist 13 unless separately authorized; V4 diagnostic-only; no betting-edge/opportunity claim; Candidate/Formal/Lock/Production OFF; H permanently closed; no real-money execution; Round 3 not started.
