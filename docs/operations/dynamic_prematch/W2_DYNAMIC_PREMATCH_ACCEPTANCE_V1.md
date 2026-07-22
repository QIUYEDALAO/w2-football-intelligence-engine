# W2 Dynamic Prematch Acceptance V1

PR #370 remains Draft. Exact release
`81b4dd2bd4a23d6ad8f5782abf05f904a88c38a8` is deployed to
`root@118.196.30.136`. GitHub Actions run `29916913849` passed `verify`,
`staging-parity` and `predeploy-e2e`; all staging services are healthy.

The dynamic EV and confirmed-lineup lifecycle is implemented and deployed:
immutable evaluation versions/supersession, `LINEUP_CONFIRMED`, the
post-lineup fresh-odds barrier, expected-XI baseline/change features, and the
single `T-30m_VALIDATION_LOCK` snapshot. This deploy deliberately reuses the
previously verified dependency image for source-only changes; it does not claim
a new third-party dependency installation.

Staging recovery also repaired existing raw market data without provider calls.
Eliteserien, Brasileirao Serie A and Chinese Super League each have eight
fixture identities, eight observed fixtures and zero orphan market fixtures.
The public 2026-07-25 dashboard contains `1494712`, `1492308` and `1523211`.

Not accepted as complete: no real confirmed-lineup window has yet produced a
post-confirmation exact odds quote, so no live lifecycle canary or 20-read
zero-delta probe exists. Transfermarkt source availability is verified only;
reviewed identity/crosswalk and as-of valuation materialization are still
pending. Consequently lineup is `LINEUP_ADVISORY_ONLY` and numerical AH,
totals and lambda adjustments remain `0.0`.

Formal, Lock and Production remain disabled and require manual approval.
