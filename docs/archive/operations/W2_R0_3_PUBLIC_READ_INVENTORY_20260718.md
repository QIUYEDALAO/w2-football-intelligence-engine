# W2 R0.3 Public Read Inventory — 2026-07-18

Status: `PASS`

| Public surface | Bounded authority | Limit/fail-closed behavior |
|---|---|---|
| Dashboard, DayView, validation summary | request-local service plus bounded fixture/observation readers | 512 fixtures, 64 fixture IDs per observation batch |
| Fixture detail | one fixture payload, observations and market snapshots | 32 fixture payloads searched, 256 observations, 64 snapshots |
| Analysis-card | one fixture payload plus fixture/team scoped feature inputs | 256 observations, 32 raw payloads/256 items, 20 xG rows per team |
| Odds timeline and market probabilities | fixture observations/snapshots | cross-fixture rows fail closed |
| Model probabilities | frozen dashboard projection only | no global forward-lock fallback |
| Tracking/replay | append-only frozen ledgers | no observation/raw/provider read path |

The legacy `future_market_observations`, `raw_payloads`, `team_xg_matches` and
fixture history scans remain available only to explicit offline workflows. A
bounded public request never falls back to them when a scoped reader is missing,
fails or returns cross-fixture rows.
