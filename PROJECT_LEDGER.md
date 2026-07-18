# W2 Project Ledger

This ledger starts at the recovery baseline. Earlier PRs and reports are historical
specifications and failure cases, not proof of behavior in the current tree.

## 2026-07-18 — R0.0 baseline freeze

- GitHub main: `7c7f16fd2c44468ba4932ef83473bd35f285cbd4`.
- Tree: `31eae0ba07361eb7ad195afccc985784f868c5c7`.
- Staging release: `b5cfd6575ba7274692714c9fc814916a00c13e36`.
- Staging and main have the same Git tree.
- PR #347 and the main push workflow both have successful current-tree CI evidence.
- Local current-tree acceptance: `1071 passed, 4 skipped`; Ruff, Mypy, Web,
  acceptance, tracked-output and secret scan passed.
- Staging database snapshot and isolated restore rehearsal passed; the temporary
  restore database was removed.
- `/health` and `/ready` currently expose the same weak 200 payload. This is
  recorded evidence, not an accepted readiness implementation.
- Staging remains fail-safe at the product boundary: RECOMMEND, lock, OFFICIAL and
  production are closed.

Detailed evidence: [W2 R0.0 Baseline Freeze](docs/operations/W2_R0_0_BASELINE_FREEZE_20260718.md).

- PR #348 passed `verify`, `staging-parity` and `predeploy-e2e`, then merged as
  `37767123313483ecd8dc9607b4bb085d7cb6db36`.

## 2026-07-18 — R0.1a quote identity observation

- Projects quote identity only from the two authoritative selected observation rows.
- Records observation IDs, fixture, provider, bookmaker, market, selection, line,
  odds, captured time, raw payload hash and source revision.
- Reports `COMPLETE`, `INCOMPLETE` or `CONFLICT` with deterministic blockers.
- Historical compatibility cards report unavailable authoritative observations;
  they never synthesize IDs from card fields.
- The projection is audit-only: it does not enter `current_odds`, pricing, pick or tier.
- Local validation: `1075 passed, 4 skipped`; 55 focused tests, Ruff, Mypy,
  TypeScript and Web production build passed.
- GitHub CI, merge and staging canary are pending.

## Delivery rule

R0.1a may start only after the R0.0 PR is merged with `verify`,
`staging-parity` and `predeploy-e2e` passing. Every later phase follows the same
merge-before-next-phase rule.
