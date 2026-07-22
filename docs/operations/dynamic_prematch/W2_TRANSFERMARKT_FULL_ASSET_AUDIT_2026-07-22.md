# W2 Transfermarkt Full Asset Audit — 2026-07-22

`SOURCE_READY` applies only to the verified official source asset and its SE1
coverage. It does not claim staging materialization, a reviewed W2/provider to
Transfermarkt crosswalk, reviewed player identities, or a real lineup canary.

- Source: `dcaribou/transfermarkt-datasets` official full DuckDB distribution.
- Asset: 204,746,752 bytes; SHA-256
  `1217a880b61d9abe9ac6a822ebeed64dee5d47eecf463b0178e818216cbfb208`.
- Read-only DuckDB 1.5.4 inspection passed and `SHOW TABLES` includes
  `game_lineups`.
- SE1: 329 games (2025-03-29 to 2026-07-06), 19 historical clubs, and 16
  distinct 2026 game participants. The latter is source scope only, not 16/16
  reviewed W2 mappings.
- Lineups: 9,664 rows across 243 games: 5,346 starting-XI rows and 4,318
  substitute rows.
- Valuations: 2,746 rows (2006-02-03 to 2025-12-30). As-of use remains
  fail-closed until identity review and staging materialization establish the
  applicable player/fixture coverage.

The complete structured manifest, source pin, and exact SQL are in the paired
JSON file. The raw DuckDB is private and untracked.
