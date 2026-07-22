# W2 LMM0 Coverage Audit — 2026-07-19

## Result

LMM0 is **PARTIAL / HARD GATE PENDING**. The real staging read-only audit found
132 stored lineup payload snapshots across 91 fixtures. Non-empty payloads
contain 60 team snapshots, 660 starter rows, complete provider positions for all
660 rows, complete formations for all 60 teams and 30 two-team 22-player
snapshots.

This proves that staging has useful real lineup data. A versioned Transfermarkt
players snapshot dated 2026-07-11 was read directly from its public R2 artifact;
its SHA-256 is recorded in the JSON evidence. Across the latest World Cup lineup
snapshots, 505/638 starters have a unique normalized-name candidate and 403/638
have a current valuation candidate. These are candidate rates, not accepted
identity mappings: team-scoped verification is still zero, so no league receives
A/B status.

The currently enabled Allsvenskan, Brasileirão, Chinese Super League and
Eliteserien fixtures have no non-empty formal starting XI in the frozen staging
window. They therefore remain grade C instead of inheriting the World Cup or
current-club candidate rates. No top-five matchday fixture exists in this audit
window, so the strict 22/22 gate remains unproven and fail closed.

## Safety

- `provider_calls_this_audit=0`
- `db_writes=0`
- No raw payload, credential material, environment value or provider header was printed.
- No repository or staging runtime mutation occurred during evidence collection.

## Consequence

Implementation and local tests may continue, but staging deployment is blocked
until the recorded Transfermarkt snapshot is imported through the offline
importer and team-scoped mappings are materialized. Until then all non-top-five
leagues remain grade C and both lineup numerical adjustment weights remain zero.
Five top leagues continue to fail closed without 22/22 confirmed identity and
valuation coverage.
