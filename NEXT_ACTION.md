# W2 Next Action

## Current gate

W2_DYNAMIC_PREMATCH_V1 is `locally_verified`.
W2_DYNAMIC_PREMATCH_STAGING is authorized.

W2_DYNAMIC_PREMATCH_V1 is deployed to staging and is waiting for a real
confirmed-lineup window. The exact running release is
`81b4dd2bd4a23d6ad8f5782abf05f904a88c38a8`; Draft PR #370 remains Draft.
GitHub Actions run `29916913849` passed `verify`, `staging-parity` and
`predeploy-e2e`.

The implementation is complete for the non-numeric lifecycle: append-only EV
evaluation versions and supersession, `LINEUP_CONFIRMED`,
`T-30m_VALIDATION_LOCK`, expected-XI/baseline comparison, fail-closed
identity/as-of-value features, and the mandatory post-lineup fresh-exact-odds
gate. The staging host is `root@118.196.30.136`; all six services are healthy.

The server's existing raw captures were repaired without provider calls:
Eliteserien, Brasileirao Serie A and Chinese Super League each have eight
fixture identities and eight observed fixtures, with zero orphan market
fixtures. The public dashboard for 2026-07-25 shows fixture IDs `1494712`,
`1492308` and `1523211` respectively.

This is deliberately not a live-lineup acceptance. Provider calls, scheduler
refresh and future-fixture refresh remain disabled. No real official XI has
yet triggered a fresh post-lineup quote, and the 20-read zero-delta probe has
not been run. Transfermarkt's full source asset is verified, but reviewed team
crosswalks, player identities and as-of valuation observations are not yet
materialized in staging. Missing coverage therefore fails closed.

Lineup remains `LINEUP_ADVISORY_ONLY`; AH, totals and lambda adjustments are
all exactly `0.0`.

## Next execution

1. In a real official-lineup window, temporarily authorize one bounded
   `lineups` + post-confirmation `odds` canary for one fixture. Prove
   `LINEUP_CONFIRMED → LINEUP_READY_MARKET_REFRESH_PENDING → fresh exact quote
   → re-evaluation`, including `SUPERSEDED` evidence. If no such window exists,
   retain `WAITING_FOR_REAL_LINEUP_WINDOW`.
2. After the controlled canary, restore provider calls, scheduler and
   future-fixture refresh to disabled, then run the 20-public-read zero-delta
   probe and record the evidence.
3. Materialize reviewed team crosswalks, provider/player identities and
   as-of Transfermarkt valuations. Recompute league-level coverage before
   claiming any real replacement-value feature coverage.
4. Run leakage-safe rolling-origin ablation and forward shadow validation for
   lineup adjustments. Do not enable numerical AH/OU/lambda adjustment without
   the predeclared evidence and explicit manual approval.

Formal recommendation, recommendation lock, OFFICIAL capture, champion switch
and Production remain unauthorized. Manual approval is required for any of
those transitions.
