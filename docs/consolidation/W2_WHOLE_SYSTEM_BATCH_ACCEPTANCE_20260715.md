# W2 Whole-System Batch Acceptance · 2026-07-15

Status: `READY_FOR_STAGING_DEPLOY_REVIEW`  
Scope: repository code, tests and governance only. This document does not authorize deployment.

## Outcome

The whole-system correctness and AH validation engineering batch is complete on main through
`4c70fd9a9051a3870fe27d9c0bb9b0af44b06f1a`. Staging has not received this batch and still reports
the older `493b4b6...` release. Production remains unchanged.

## Merged change set

| PR | Scope | Merge SHA |
|---|---|---|
| #278 | validation outcome status baseline | `86e8200a9df2dfffa15535652e0e9cd58e4e5c2c` |
| #279 | AH visible-direction containment | `b236e1e6cc01fb6078abc165d60d287869275358` |
| #280 | FME Snapshot v2 distribution semantic closure | `ad151b6c65495fb003795145a015de9ffec10f66` |
| #281 | decision-source hard gate | `e5d16c4534b68c2744d75cd80fd1e8349199f39f` |
| #282 | immutable MarketQuote and evidence identity | `7216c3fef9553ddc4c58f578a21f34c3b714c845` |
| #283 | canonical replay/audit/performance identity | `3cd7bbca177361bd33c0a634fdbc08e3162466c5` |
| #284 | atomic evidence storage and degraded readers | `eaea4ec2bc1a60468cdbb436ebdfb62dc5d10950` |
| #285 | liveness/readiness contract | `c4a733a5a90058d3b91a8dd6fe1ce89e65fef9bf` |
| #286 | selected-quote freshness | `3c5c9243ebbb7f105b27eddb0a05a6d7aae84bb7` |
| #287 | read-model concurrency isolation | `d1aab2835a37c7ae51e686fc518252a395281e54` |
| #288 | degraded-read fallback preservation | `007abdd9f7440217d92db4a8f6f8650b4d95ac59` |
| #289 | staging ops access control | `4de27442940d530ec9b93caec7e0cf5ec926320b` |
| #290 | AH Strict Shadow dual confirmation | `1b94602f0cc514140f1da0f12fff562ea19d73f0` |
| #291 | AH direction concentration governance | `c326f9de63516d27811a6f1f1ddaee0f4cb6f986` |
| #292 | AH 35/100 evidence review tooling | `4c70fd9a9051a3870fe27d9c0bb9b0af44b06f1a` |

Historical Draft PR #277 was closed because its pre-program `PROJECT_STATE` rewrite was no longer
safe to rebase. This final context change is its explicit replacement.

## Correctness invariants

- FME Snapshot v2 freezes Dixon-Coles distribution context, score matrix, fair lines and settlement
  distributions and verifies integrity plus semantic replay.
- Model probabilities and MarketQuote implied probabilities remain separate domains.
- Every new visible pick must bind a valid estimate and quote; invalid or legacy evidence fails closed.
- AH selection settlement uses the selected side line, including positive AWAY_AH lines.
- Canonical performance counts one final eligible prematch candidate per fixture, market, scope and
  strategy version. OFFICIAL, VALIDATION, Wide Shadow and Strict Shadow never cross-count.
- Evidence append/timeline storage is cross-process atomic and preserves corruption/degraded state.
- Quote freshness uses the selected quote capture time only.
- `/ready` checks critical dependencies; request caches are concurrent-request isolated; degraded DB
  reads preserve fallback data; staging `/ops` fails closed behind authentication.
- Strict AH requires two eligible, direction-consistent, distinct quotes at least 15 minutes apart in
  T-24h to T-30m. It remains invisible and cannot affect decision, pick or tier.

## Verification

- Full pytest: `1316 passed, 4 skipped`.
- Skips: three local Docker staging-parity fixtures and one PostgreSQL migration URL; GitHub
  `staging-parity`, `predeploy-e2e` and DB-backed `verify` passed for every merged PR.
- Ruff: PASS.
- Mypy: PASS across 241 source files.
- TypeScript: PASS.
- Web production build: PASS.
- Offline acceptance and tracked-output checks: PASS.
- AH evidence review current local runtime: `ACCUMULATING`, corrected settled `0`, HOME `0`, AWAY
  `0`, remaining to 35=`35`, remaining to 100=`100`.

## Safety and remaining gates

- Provider calls: `0`.
- Business database writes: `0`.
- Staging deploy: `false`.
- Production deploy: `false`.
- Scheduler restart: `false`.
- Worker restart: `false`.
- Historical Snapshot/outcome rewrites: `0`.
- RECOMMEND, recommendation locks, production release, league enablement and model artifacts: unchanged.

The next permitted action is a separately approved staging deployment review. AH remains
shadow-only and evidence-accumulating; neither staging review nor 35/100 sample maturity automatically
opens direction visibility, RECOMMEND or lock.
