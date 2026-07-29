# W2 R0.0 Baseline Freeze — 2026-07-18

Result: `PASS_WITH_OPEN_CORRECTNESS_BOUNDARIES`

This document freezes facts from the recovery tree. It does not claim the
confirmed R0.1–R0.3 defects are fixed.

## Repository and CI

- Main commit: `7c7f16fd2c44468ba4932ef83473bd35f285cbd4`.
- Tree: `31eae0ba07361eb7ad195afccc985784f868c5c7`.
- PR #347 head: `0d8c6fef01cfa08adbf74b1c4cc03d257d5dfdcb`.
- PR #347 workflow run: `29617918571`; `verify`, `staging-parity` and
  `predeploy-e2e` all passed.
- Main push workflow run: `29618114633`, passed.
- Test counts from commits before this recovery tree are not accepted evidence.

Current-tree local checks:

- Pytest: `1071 passed, 4 skipped, 2 warnings`.
- The skips require a Docker staging-parity fixture or `W2_TEST_POSTGRES_URL`;
  the matching GitHub jobs passed.
- Ruff: pass.
- Mypy: pass for 224 source files.
- Web TypeScript and production build: pass.
- Offline acceptance: pass with zero provider calls and zero DB writes.
- Tracked-output guard and secret scan: pass.

## Staging identity and runtime

- API/Web/Worker/Scheduler release: `b5cfd6575ba7274692714c9fc814916a00c13e36`.
- The deployed release tree equals the recovery main tree.
- Four application services are healthy with restart count 0 and OOM false.
- Redis Celery queue length: 0.
- Runtime files: 1,043; forward ledger files: 11.
- Runtime manifest: `5590a5f4db05006392ad7ad036a5f894c026108714b2de6e9ecf008b977d90f1`.
- Ledger manifest: `4dfc2762fb7abb3e5a46b5cea69d263b083b92b323360ab9e32521803876c60e`.
- Artifact manifest: `cb2a1be458d8c9e5f32e78fc82d029f1ad166e4ba9c4df180a5772fee42c56b4`
  across 10 files.
- Checkpoint manifest: `abcfa6a9d4df344d1781bc2560b5e4cdcae08b39ed303063535e7e1e926a304a`.

## Database restore proof

- Database size at freeze: 1,781 MB.
- Alembic current/head: `0023_create_checkpoint_refresh_schedule`.
- Public table count: 115.
- Encrypted-host-local operational backup path:
  `/opt/w2/shared/backups/r0/w2_r0_baseline_20260718_r00.dump`.
- Backup SHA-256: `6e948628ef6487f6adb3049181c8b40e69add6bd866ffa6d957fcbdce4d28b68`.
- Backup mode/size: `0600`, 237,271,570 bytes.
- Restore was performed into disposable database `w2_r0_restore_20260718_r00`.
- Source and restore both reported revision 0023 and 115 public tables.
- Normalized source/restore schema SHA-256:
  `1d587cffb1ff819b2d7b9f3d028e95e341015535da942cfae13df18876919906`.
- The disposable restore database was removed after verification.

## Safety state

- Recommendation, candidate, formal recommendation and production flags: false.
- Recommendation locks, Gate 5 lock events and shadow locks: 0.
- XG backfill: false.
- DayView next36: 14 cards, all WATCH/PARTIAL; ANALYSIS_PICK=0,
  RECOMMEND=0, lock eligible=0.
- Acceptance probes reported provider calls 0 and DB writes 0.
- Provider ledger baseline at collection: total 673, live requests on the current
  Beijing day 55. Those are scheduler activity, not acceptance calls.

The recovery API currently reports legacy ledger figures `fixture_count=73`,
`record_count=12045`, outcomes 43 and shadow outcomes 60. R0.0 records these
values without reclassifying them as canonical V3 denominators.

## Confirmed boundaries retained for repair

1. `/health` and both ready surfaces return the same weak 200 HealthPayload;
   Docker still probes liveness rather than service readiness.
2. Public analysis-card can rebuild features, ratings, Poisson and simulation at
   read time and can use wall-clock as-of.
3. Quote identity and captured_at freshness are not yet hard domain invariants;
   non-READY decisions are not uniformly no-pick.
4. Request metrics and the exported registry are disconnected and retain
   unbounded latency lists.
5. Public fallback reads still include global observation, raw payload and team
   history scans.

R0.1a is the only authorized next implementation after this evidence PR merges.

