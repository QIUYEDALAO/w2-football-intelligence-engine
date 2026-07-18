# W2 Dashboard Market Freshness Staging Canary — 2026-07-19

## Result

`PASS` for local implementation `f2389e80418502dc85ad9718c0b3481b32d9ab3f`.
GitHub was not accessed or synchronized.

## Root causes corrected

- The fixture-scoped public reader previously truncated an unstratified 256-row
  slice, allowing non-target markets to crowd out full-time AH and totals.
- API-Football shared handicap lines were not canonicalized to complementary
  home/away lines.
- Rolling xG was looked up by the upcoming fixture instead of the latest team
  snapshot before kickoff.
- The T6 odds checkpoint was absent from the active schedule.
- The Dashboard described a pre-checkpoint wait as a pipeline failure and the
  fresh browser date used the calendar day instead of the pre-noon football day.

## Data-quality evidence

The three visible fixtures were not associated with 3,200 provider requests.
They each had one historical odds capture batch containing approximately
3,200 normalized detail rows from 12 bookmakers. One HTTP odds response can
expand into many bookmaker, market, line and selection rows.

At the canary boundary:

- provider request ledger: `738 -> 738`
- future market observations: `3,812,702 -> 3,812,702`
- recommendation locks: `0 -> 0`
- recommendations: `0 -> 0`
- settlements: `0 -> 0`
- Redis DB1 Celery queue: `0 -> 0`

The Beijing 2026-07-19 provider ledger contained four HTTP requests before the
canary: one status, one fixtures and two odds requests. These counts are kept
separate from capture batches and normalized observation rows.

## Contract evidence

For fixtures `1494210`, `1494212` and `1494213`, an in-container read-only build
used 256 bounded rows per fixture. All three reported rolling xG `READY`; both
AH and totals quote identity and freshness were `COMPLETE` at the capture time.
No old capture was rematerialized as if it were current.

The public page keeps the existing layout and now shows `赛前数据按计划等待`,
`等待赛前刷新` and the 16:30 T6 tick instead of `数据阻塞` or `数据陈旧` before
the scheduled collection point. A fresh browser before Beijing noon displays
football day `2026-07-18`.

## Gates and runtime

- full pytest: `1176 passed / 4 skipped`
- Ruff, Mypy, TypeScript, production Web build: `PASS`
- Playwright: `7 passed`
- acceptance, tracked-output guard, secret scan, diff check: `PASS`
- `/health`, canonical `/ready`, `/v1/version`: `PASS`
- API, worker, scheduler and Web: restart `0`, OOM `false`
- scheduler restored to its pre-canary running state
- deployed release: `f2389e80418502dc85ad9718c0b3481b32d9ab3f`

This correction resets the consecutive read-only production cycle count to
`0/3`. The first eligible 09:00 cycle is 2026-07-19.
