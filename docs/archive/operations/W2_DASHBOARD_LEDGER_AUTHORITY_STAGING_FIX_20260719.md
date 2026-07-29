# W2 Dashboard ledger authority and stale-odds wording fix — 2026-07-19

## Outcome

Staging regression fixed and accepted on
`438ac07e8ad3b30dbe1c4107b759100e1cae7418`. GitHub was not accessed or
synchronized.

The LMM image installed the package non-editably and started `uvicorn`
directly. `w2.api.repository` derived its root from the installed module path,
so it looked for the ledger under `/app/.venv/lib/python3.12/runtime` and
reported zero validation fixtures. The real shared ledger was never deleted:
12 JSONL files remained under `/opt/w2/shared/runtime/forward_outcome_ledger`.

The API, worker and scheduler now receive explicit `W2_APP_ROOT=/app` and
`W2_RUNTIME_ROOT=/app/runtime`. The accepted API reports `ROOT=/app`,
`RUNTIME=/app/runtime` and sees all 12 ledger files.

## Restored validation evidence

- validation fixtures: `23`
- settled: `15`
- pending: `8`
- hit: `10`
- miss: `3`
- push: `2`
- void: `0`
- decisive hit rate: `76.923%`

The ledger aggregate hash remained
`8634a31f58b0537bea402dbd15ce92fa03f49f7ffffef76e6f30fa0d2dfb9ef2`
before and after deployment. Provider request count remained `738`; queue
remained `0`.

## Honest stale-odds wording

The current three Swedish fixtures have stored early odds captured around
2026-07-17 22:48 Beijing. Those quotes are older than the 30-minute executable
freshness limit, so they remain reference-only. The next scheduled collection
is 2026-07-19 16:30 Beijing.

The Dashboard no longer says only “数据陈旧”. It now states that the missing
input is an odds quote captured within the last 30 minutes, shows that only the
older early market is available, and says that the system will decide again
after the 16:30 collection. It does not promise a pick: a fresh, complete AH or
OU quote and the decision threshold must still pass.

These fixtures are non-top-five league fixtures, so a confirmed lineup is not
a hard gate. Top-five league fixtures still require complete 22/22 lineup,
identity, valuation and formation evidence under the LMM policy.

## Gates and runtime

- full local gate: `1207 passed / 4 skipped`
- Ruff and Mypy: PASS
- Web typecheck/build and Playwright `8/8`: PASS
- acceptance, tracked output, secret scan and diff check: PASS
- exact-archive isolated predeploy on staging host: PASS
- health, root readiness, legacy readiness, version, DayView and Dashboard:
  HTTP 200
- API, worker, scheduler and Web: healthy; restart `0`; OOM false
- final RSS: API `205.4 MiB`, worker `268.4 MiB`, scheduler `132.7 MiB`, Web
  `4.477 MiB`
- watchdog: active and enabled

## Cycle consequence

The 2026-07-19 10:00 patrol cannot count because it exposed a real data/runtime
regression. This runtime correction resets the sequence to `0/3`. The next
eligible schedule is 2026-07-20, 2026-07-21 and 2026-07-22 at 09:00 Beijing on
the unchanged accepted SHA and images.
