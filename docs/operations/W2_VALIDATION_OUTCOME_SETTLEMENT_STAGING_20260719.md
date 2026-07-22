# W2 Validation Outcome Settlement — Staging Acceptance

Date: 2026-07-19 (Asia/Shanghai)

## Outcome

- Accepted implementation: `8aa4a888df463f8cc075c42ed468174f83e15444`.
- Delivery was local-only. GitHub was not fetched, pulled, pushed or otherwise synchronized.
- `/health`, `/ready`, `/v1/version`, DayView and Dashboard returned HTTP 200.
- All API, worker, scheduler and Web containers run the accepted SHA with zero restart and OOM events.
- Scheduler and watchdog were restored after the controlled settlement run; Redis DB1 Celery queue is zero.

## Settlement evidence

- The shared ledger is explicitly rooted at `/app/runtime/forward_outcome_ledger`; no current-working-directory inference remains.
- The first dry-run exposed duplicate cross-day legacy captures and a shadow capture without an entry quote. The candidate was rolled back before manual backfill, the calculator was corrected, and the full gate was repeated.
- During a later deployment window the controlled scheduler appended provable outcomes. These append-only rows were audited individually by fixture, market, selection, line, 90-minute score and scope.
- The final candidate quarantines a finished capture that has no settlement quote as `SETTLEMENT_ERROR`. It does not manufacture a VOID and does not query the provider again while the pending identity is unchanged.
- Idempotency re-run result: `NO_DUE_WORK`, `provider_calls=0`, `db_writes=0`, `written=0`.
- Validation fixture count remained 23. Final validation state is 23 handled, 0 pending: 14 hit, 4 miss, 2 push and 3 void. Decisive hit rate is 77.78%; PUSH and VOID do not enter that denominator.
- OFFICIAL remains zero and SHADOW remains independently accounted. No recommendation lock was created.

## Gates

- Full Python suite: `1217 passed / 4 skipped`.
- Ruff and Mypy: PASS.
- TypeScript typecheck, Web production build and Playwright 8/8: PASS.
- Acceptance, tracked-output guard, secret scan and `git diff --check`: PASS.
- Exact-archive isolated predeploy, staging migration, fake-provider and public-read contracts: PASS.
- Staging Alembic current/head: `0024_create_lineup_intelligence` / match.

## Final runtime snapshot

- Release SHA: `8aa4a888df463f8cc075c42ed468174f83e15444`.
- Ledger files: 12; aggregate hash: `6c8fe9db73148b96ad1284c23e41cffb652f5d26a0aa974236b90db4acd13dfd`.
- Provider request count for the Beijing day after dry-runs and controlled result refreshes: 44, below the shared 120/day hard cap.
- Future market observations: 3,812,702; raw payloads: 2,294; recommendation locks: 0.
- RSS: API 208.5 MiB, worker 267.6 MiB, scheduler 138.2 MiB, Web 4.449 MiB.

## Release state

The settlement repair is `staging_accepted`. Because the implementation and runtime contract changed, the read-only stability sequence is reset to `0/3`; eligible Beijing 09:00 patrols are 2026-07-20, 2026-07-21 and 2026-07-22 on the same SHA and images. Champion, RECOMMEND/lock, OFFICIAL and write-enabled production remain unchanged.
