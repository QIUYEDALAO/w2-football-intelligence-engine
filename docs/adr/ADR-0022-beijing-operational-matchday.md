# ADR-0022: Beijing Operational Matchday

## Status

Accepted for local/staging.

## Decision

W2 has one user-facing matchday window: Asia/Shanghai. The database and domain
events remain UTC, while API and Dashboard views expose Beijing display fields.

## Policy

- `W2_DISPLAY_TIMEZONE=Asia/Shanghai`
- `W2_OPERATIONS_TIMEZONE=Asia/Shanghai`
- `DATABASE_TIMEZONE=UTC`
- Operational day is `[00:00:00, next 00:00:00)` in Asia/Shanghai.
- Provider discovery must cover all UTC dates intersecting the Beijing window,
  then filter precisely by UTC kickoff.
- No Japan/Tokyo user matchday window is supported.

## Consequences

The Dashboard may show a fixture whose UTC date is the previous day when the
fixture belongs to the current Beijing operational day. Coverage reports must
explain every provider fixture as included or excluded with a unique reason.
