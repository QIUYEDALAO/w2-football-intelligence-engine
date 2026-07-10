# W2 Direction Allowed Prereg Gate - 2026-07

## Purpose

This document defines the read-only prereg gate for per-league
`direction_allowed` review. It does not release any league and does not change
runtime behavior.

## Preregistered Conditions

The ledger source of truth is
`docs/consolidation/W2_TASK_ACCEPTANCE_LEDGER.md`.

Superseding preregistered conditions, fixed on 2026-07-10:

> Future `direction_allowed` release is evaluated per league and market. It
> requires a separate approved PR, at least 100 distinct-fixture valid same-line
> shadow CLV samples, median same-line decimal CLV above zero, latest matching
> market gap at most 0.04, entry-window coverage at least 80%, valid prematch
> closing-pair coverage at least 80%, settled-outcome coverage at least 90%, and
> provider daily usage at or below 120.

These conditions are review gates only. Passing AH does not open TOTALS, and
vice versa. The maximum result is `ELIGIBLE_FOR_REVIEW`; offline numbers and
shadow direction must not directly open EV / RECOMMEND.

## Candidate Order

The fixed review order is:

1. `eliteserien`
2. `allsvenskan`
3. `chinese_super_league`

## Disabled Leagues

`brasileirao_serie_a` remains disabled for this gate. R4.1 worsened the Brazil
gap, so Brazil is not a `direction_allowed` release candidate.

## R1.1 Dependency

The prereg gate depends on R1.1 checkpoint evidence:

- double-snapshot cards
- shadow pick non-empty rate
- `clv_shadow` sample count and median
- entry-window coverage
- missing prematch closing exclusions
- FT / AET / PEN outcome buckets
- provider usage curve
- model family and R4.1 artifact provenance
- per-league and per-market same-line CLV, line CLV, closing, entry, and outcome coverage

When R1.1 has no settlement samples, the gate must report `ACCUMULATING`, not a
numeric conclusion. When sample counts are below threshold, it must report
`NOT_ENOUGH_SAMPLE`.

## Release Rule

`release_decision` can only be:

- `REVIEW_ONLY`
- `NOT_ELIGIBLE`
- `ELIGIBLE_FOR_REVIEW`

The gate never emits a live release. `direction_allowed_changes` must remain an
empty list until a later reviewer-approved release PR.

Evidence that is absent, stale, or degraded fails closed to `WATCH`.

## Explicitly Not Included

- No provider calls.
- No DB writes.
- No staging deploy.
- No production deploy.
- No scheduler restart.
- No EV / RECOMMEND leg change.
- No `direction_allowed` change.
- No Stage 16.
