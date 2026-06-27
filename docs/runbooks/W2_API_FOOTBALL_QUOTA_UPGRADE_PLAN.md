# W2 API-Football Quota Upgrade Plan

Status: planning only. This document does not upgrade any API-Football plan and
does not authorize payment, credentials, or provider settings changes.

## Current Policy

- Default daily budget: `7500`.
- Reserve bucket: `1500`.
- Core prematch tasks have priority: fixtures, odds, lineups.
- Non-core enrichment and backfill must yield when reserve is at risk.
- Unknown remaining quota is treated conservatively.
- A future `75000/day` plan may be evaluated, but it cannot replace budget
  governance.

## Upgrade Evaluation Triggers

Evaluate an upgrade only when all are true:

- August validation plan identifies one or more leagues that need sustained
  fixture, odds, lineups, and xG/statistics collection.
- The 7500/day plan cannot support the planned scope while preserving reserve.
- The expected request budget is documented by competition, endpoint, and phase.
- Runtime guardrails remain in place after the upgrade.
- A human owner approves cost and provider terms outside this repository.

## Required Pre-Upgrade Evidence

- Last 7 days remaining quota distribution.
- Request count by endpoint.
- Reserve-lock incidents.
- Backfill skipped by quota guard.
- Core odds/lineups freshness.
- Expected request budget for each candidate league.
- Rollback plan that returns to the 7500/day policy.

## Forbidden Actions In Code PRs

- Do not change provider credentials.
- Do not change billing or payment settings.
- Do not store sensitive values in the repository.
- Do not remove reserve checks.
- Do not default-enable `75000/day`.
- Do not spend real quota to simulate low-quota behavior.

## Acceptance Checklist

An upgrade may be considered operationally ready only when:

- The runtime still reports `daily_budget`, `reserve_bucket`,
  `available_after_reserve`, `reserve_locked`, and `upgrade_enabled`.
- `upgrade_enabled` remains false until a separate authorized operations action.
- Tests cover unknown, empty, and null remaining quota.
- Core odds/lineups are not blocked by backfill or xG enrichment.
- The rollback path is documented and rehearsed without changing credentials.

## Rollback

If quota risk, provider errors, or unexpected costs appear, immediately return
to the 7500/day governance policy, keep reserve checks active, and disable
non-core enrichment/backfill before touching core prematch odds/lineups.
