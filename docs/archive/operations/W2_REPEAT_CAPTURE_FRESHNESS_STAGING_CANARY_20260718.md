# W2 repeated-capture freshness staging canary — 2026-07-18

## Result

Final implementation SHA: `94bcd62c67ed3fe50bba5ee65be10133556f83d0`.

The fix preserves append-only quote audit history while allowing a later
provider response with unchanged business odds to advance the authoritative
quote confirmation time. Dashboard layout is unchanged. The command bar now
labels page update, odds confirmation and next planned collection separately.

The accepted runtime also invalidates a warm Dashboard cache when either the
fixture-scoped quote confirmation watermark or next collection watermark
changes. A completed checkpoint is recorded only after the refreshed fixture's
frozen public artifact has been built and atomically written.

No GitHub fetch, pull, push, workflow or PR was used.

## Real repeated-odds evidence

- Natural scheduler checkpoint: fixture `1494704`, T1 at
  `2026-07-18T15:00:00Z`; no manual provider request was made.
- Previous capture: `2026-07-16T16:00:18.040481Z`, 3,396 audit rows.
- New capture: `2026-07-18T15:00:29.957318Z`, 3,870 audit rows.
- 1,241 rows had the same fixture, bookmaker, provider bet, canonical market,
  selection, line, price and live/suspension state in both captures.
- Those 1,241 old and 1,241 new rows have separate observation identities.
  Neither `captured_at` nor historical rows were overwritten.

## Local gates

- Pytest: `1173 passed, 4 skipped`.
- Ruff and Mypy (`src apps`, 230 source files): PASS.
- TypeScript typecheck, production Web build and six Chromium E2E cases: PASS.
- Acceptance, tracked-output guard, secret scan and `git diff --check`: PASS.
- Offline acceptance proved `provider_calls=0` and `db_writes=0`.

## Staging acceptance

- Natural T-15 checkpoint ran at `2026-07-18T15:45:15Z` and completed in 13.13
  seconds with no blockers. It used four normal scheduler provider requests,
  appended 7,726 observation rows and materialized exactly fixtures `1494704`
  and `1494707` before marking both checkpoint plans `COMPLETED`.
- For fixture `1494704`, all 3,870 rows in the 23:45 capture matched the business
  identity and price of all 3,870 rows in the 23:00 capture. Both batches retain
  3,870 distinct observation IDs; authoritative `captured_at` advanced from
  `15:00:29.957318Z` to `15:45:16.642207Z`.
- Its public frozen artifact atomically changed from source hash
  `811c1d5b...` / artifact hash `440d3a14...` to source hash `303c6209...` /
  artifact hash `faa19529...`, with `quote_freshness=COMPLETE`.
- The public DayView immediately reported page update `15:47:01Z`, odds last
  confirmed `15:45:17Z` and next collection `2026-07-19T08:30:00Z`; the warm
  cache did not retain the already-completed 15:45 tick.
- Fixture `1494704` no longer reports `DATA_STALE_ODDS`: its odds field is
  present, `stale=false`, and the AH quote identity is COMPLETE. Its current
  fail-closed state is `MARKET_UNAVAILABLE`, which is a distinct missing-market
  condition and does not manufacture a pick.
- `/health`, `/ready`, `/v1/version`, DayView and Dashboard returned HTTP 200.
  API, Web and DayView all exposed exact release SHA `94bcd62...`; Alembic
  current/head and readiness artifacts remained matched.
- Public probes left provider requests at `734 -> 734`, observations at
  `3,806,180 -> 3,806,180`, and locks, predictions, recommendations and
  settlements at zero. Thus the public verification itself made no provider or
  business DB writes.
- Redis DB1 Celery queue was zero. API, worker, scheduler and Web had restart=0,
  OOM=false and exit137=0; watchdog remained active.
- Final RssAnon was API 214,372 KiB, worker 295,284 KiB, scheduler 149,912 KiB
  and Web 8,764 KiB. Ratios against the frozen baseline were at most 1.020,
  below the 1.20 gate.
- Browser verification confirmed the original Dashboard geometry. The command
  bar showed page update 23:47, odds confirmation 23:45 and next collection
  16:30; the selected fixture changed from “赔率过期/数据陈旧” to “盘口未齐/数据阻塞”.

## Safety

- Champion, thresholds, league switches, RECOMMEND, lock and OFFICIAL did not
  change.
- The three consecutive Beijing 09:00 read-only cycles reset to `0/3`; the first
  eligible cycle for this implementation is 2026-07-19.
- The predeploy release and four service images remain available under
  revision-scoped rollback tags.
