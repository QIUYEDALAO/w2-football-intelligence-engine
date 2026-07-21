# W2 PR #370 Final Product Correctness Context

Date: 2026-07-21

## Purpose

This is the sanitized GitHub context record for the final product-correctness round on
Draft PR #370. It records the received execution contract and current implementation
state. It does not authorize merge, formal recommendation, lock, or production release.

## Frozen baseline

- Accepted baseline head before this round: `2957720008775f80490f82a289bc64475450635c`.
- Accepted baseline CI run: `29834661962`.
- The selected-side signed AH line fix and append-only supersession remain frozen.
- F1-F9 weights, EV/divergence thresholds, quote freshness, calibration, and formal gates
  must not be redesigned in this round.

## Authorized implementation scope

1. Asia/Shanghai date-first match display and a minute-updating client clock.
2. Deterministic categorical sampling of exactly 10,000 scores from the existing exact
   Dixon-Coles and empirical-uncertainty score matrix.
3. Scoreline constraints bound to the V3 selected candidate, exact selected quote line,
   canonical quarter-line settlement, and any public secondary market.
4. Desktop schedule internal scrolling without row truncation, with mobile natural
   document scrolling.
5. One public forward-validation ledger while preserving internal provenance.
6. Exact-head CI, exact-SHA staging image deployment, bounded provider regeneration,
   and read-only parity evidence.
7. Staging access control with no unauthenticated public HTTP listener.

## Implemented before exact-head publication

- Date-first display, date groups, minute clock, invalid-time fail closed.
- Seeded 10,000-score projection with input, matrix, decision, seed, and evidence hashes.
- Canonical AH/OU settlement constraints and selected quote-line mismatch blocker.
- Projection UI, consistent sample count, and exact blocker copy.
- Full schedule reachability at 5, 15, and 30 fixtures.
- Unified public forward-ledger wording and accounting.
- Web and API loopback-only staging bindings plus response security headers.

## Runtime work still pending at this context point

- Commit and push the implementation head.
- Exact-head GitHub PostgreSQL verify, staging-parity, and predeploy-e2e.
- Exact-SHA image deployment and Alembic parity verification.
- One bounded provider quote window and truthful full upcoming-fixture recomputation.
- HTTP/live DB/frozen parity, zero-write read audit, and final sanitized evidence package.

## Exact-SHA runtime correction

The first exact-SHA runtime probe confirmed loopback-only binding, but found that Nginx
location-level cache headers suppressed inherited security headers on `/`, `index.html`,
`meta.json`, and assets. The follow-up source change explicitly applies the security
headers in every cache-specialized location. The original implementation SHA must not
be treated as the final access-control SHA.

## Safety state

```text
PR_370_KEEP_DRAFT
FORMAL_DISABLED
LOCK_DISABLED
PRODUCTION_DISABLED
MANUAL_APPROVAL_REQUIRED
```
