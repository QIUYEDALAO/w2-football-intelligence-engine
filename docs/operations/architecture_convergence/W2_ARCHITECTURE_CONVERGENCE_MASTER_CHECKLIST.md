# W2 Architecture Convergence Master Checklist

## Current task

- ARCH-P1-03B-R1: IMPLEMENTATION_IN_PROGRESS
- Branch: `codex/arch-p1-03b-r1`
- Delivery: one Draft Implementation PR

## Required outcome

- Canonical player resolution is scoped by provider player ID, canonical team,
  competition, season, and as-of time.
- Only REVIEWED/APPROVED mappings are consumable; missing, stale, ambiguous, conflict,
  unreviewed, and database-error cases fail closed.
- Approved team rosters come from the canonical database with stable sorting and
  deduplication.
- Lineup materialization, join evidence, and team value use the same canonical
  authority.
- Production references to `PlayerIdentityCrosswalkV1` are zero.
- The existing 66 reviewed mappings retain the same count and fingerprint.
- Provider calls and staging database writes remain zero.

## Verification

- Focused identity tests
- Ruff and Mypy
- Full pytest
- Migration upgrade/downgrade/upgrade
- Web typecheck, build, and e2e
- Staging parity
- FULL CI / `CI_REQUIRED`

## Stop condition

Stop after the Draft Implementation PR and its full CI result. Do not start Formal,
Candidate, Lock, Production, scheduler, or a separate governance task.
