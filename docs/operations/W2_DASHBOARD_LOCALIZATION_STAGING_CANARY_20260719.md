# W2 Dashboard Localization Staging Canary — 2026-07-19

## Result

`PASS` for local implementation `5cd3034878abe7522f8b18c8be32dc86f2a3da1e`.
GitHub was not accessed or synchronized.

## Kickoff verification

The staging source rows for fixtures `1494210`, `1494212` and `1494213` all
contain `2026-07-19T14:30:00+00:00` with source timezone `UTC`. This is
Beijing `2026-07-19 22:30` and Swedish local summer time `16:30`.

The three fixture identities are:

- IF Elfsborg vs Sirius
- Halmstad vs BK Hacken
- Hammarby FF vs Degerfors IF

The equal kickoff time is therefore source-backed and not a UI normalization
error.

## Localization correction

The public DayView currently supplies English `competition_name`,
`home_team_name` and `away_team_name` while the optional `*_cn` fields are
absent. The Web localization dictionary previously covered World Cup national
teams only. The accepted change adds Chinese localization for the visible
clubs in the enabled Allsvenskan, Eliteserien, Serie A and Super League scope,
and applies it consistently to schedule rows, evidence panels, pick labels,
market lines and verification rows.

Public canary evidence shows:

- `Allsvenskan` -> `瑞典超`
- `IF Elfsborg vs Sirius` -> `埃尔夫斯堡 vs 天狼星`
- `Halmstad vs BK Hacken` -> `哈尔姆斯塔德 vs 赫根`
- `Hammarby FF vs Degerfors IF` -> `哈马比 vs 代格福什`
- all three kickoff labels remain `22:30`

## Gates and runtime

- TypeScript and Web production build: `PASS`
- Playwright: `8 passed`, including a localization and kickoff regression test
- canonical `/ready`: `READY`
- API, worker, scheduler and Web: restart `0`, OOM `false`
- Redis DB1 Celery queue: `0`
- scheduler remained running after deployment
- deployed release: `5cd3034878abe7522f8b18c8be32dc86f2a3da1e`

This is a display localization correction before the first eligible 09:00
cycle; the read-only cycle count remains `0/3`.
