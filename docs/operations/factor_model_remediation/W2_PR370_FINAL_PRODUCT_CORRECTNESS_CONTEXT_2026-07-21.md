# W2 PR #370 Final Product Correctness Context

Date: 2026-07-21

## Purpose

This is the sanitized GitHub context record for the final product-correctness round on
Draft PR #370. It records the received execution contract and current implementation
state. It does not authorize merge, formal recommendation, lock, or production release.

## Frozen baseline

- Accepted baseline head before this round: `2957720008775f80490f82a289bc64475450635c`.
- Accepted baseline CI run: `29834661962`.
- The selected-side signed AH line fix and append-only supersession remain frozen.
- F1-F9 weights, EV/divergence thresholds, quote freshness, calibration, and formal gates
  must not be redesigned in this round.

## Authorized implementation scope

1. Asia/Shanghai date-first match display and a minute-updating client clock.
2. Deterministic categorical sampling of exactly 10,000 scores from the existing exact
   Dixon-Coles and empirical-uncertainty score matrix.
3. Scoreline constraints bound to the V3 selected candidate, exact selected quote line,
   canonical quarter-line settlement, and any public secondary market.
4. Desktop schedule internal scrolling without row truncation, with mobile natural
   document scrolling.
5. One public forward-validation ledger while preserving internal provenance.
6. Exact-head CI, exact-SHA staging image deployment, bounded provider regeneration,
   and read-only parity evidence.
7. Staging access control with no unauthenticated public HTTP listener.

## Implemented before exact-head publication

- Date-first display, date groups, minute clock, invalid-time fail closed.
- Seeded 10,000-score projection with input, matrix, decision, seed, and evidence hashes.
- Canonical AH/OU settlement constraints and selected quote-line mismatch blocker.
- Projection UI, consistent sample count, and exact blocker copy.
- Full schedule reachability at 5, 15, and 30 fixtures.
- Unified public forward-ledger wording and accounting.
- Web and API loopback-only staging bindings plus response security headers.

## Final runtime evidence

- Runtime implementation SHA: `d377d6e07b300dda3fcaa0bc329d9186c488edb7`.
- GitHub Actions run `29844788328`: verify, staging-parity, and predeploy-e2e passed.
- Staging API, web, and worker report the implementation SHA; Alembic current equals head
  `0033_create_canonical_team_identity`.
- API and web listen on loopback only; scheduler is stopped.
- One bounded provider window used 10 requests and left 7,176 requests available. Provider
  calls were disabled immediately afterward.
- Eight current fixtures were recomputed: 5 `ANALYSIS_PICK`, 2 `NO_EDGE`, and 1
  `NOT_READY/MARKET_UNAVAILABLE`.
- Every analysis pick has a fresh exact quote, model and market probability, delta, EV,
  empirical uncertainty, and a deterministic 10,000-sample scoreline projection.
- Twenty bounded reads across HTTP, frozen artifacts, and dashboard projection preserved
  card/V3 identities and produced zero database, ledger, cohort, or OFFICIAL writes.
- Unified forward ledger: 28 total, 23 settled, 5 pending, 16 eligible, 7 evidence repair
  pending; 11 hit, 3 miss, 2 push; decisive hit rate 78.6% (11/14).
- Safety deltas remain recommendations=0, locks=0, OFFICIAL=0, formal settlements=0.

The Python runtime source was unchanged after the previously verified runtime image, so
its layers were reused with exact-SHA metadata. The changed web source was rebuilt. UI
polish is explicitly deferred by the operator and is not claimed in this evidence round.

See `W2_PR370_FINAL_PRODUCT_CORRECTNESS_EVIDENCE_2026-07-21.json` for the sanitized
machine-readable result.

## Public HTTP entrypoint recovery

On 2026-07-22 Asia/Shanghai, the operator reported that `http://118.196.30.136` did not
open. Investigation found the staging containers healthy and reachable on loopback:

- web: `127.0.0.1:18080`, release `d377d6e07b300dda3fcaa0bc329d9186c488edb7`
- API: `127.0.0.1:18000`, `/ready` status `READY`
- provider calls disabled, scheduler disabled

The direct IP was unavailable because host Nginx was inactive. The host firewall allowed
port 80, but no public listener was running. Nginx was reconfigured to proxy the current
loopback staging services and started/enabled:

- `/` -> `127.0.0.1:18080`
- `/v1/`, `/ops/`, `/api/`, `/health`, `/ready` -> `127.0.0.1:18000`

Post-fix public checks returned HTTP 200 for `http://118.196.30.136`, `meta.json`, and
`/ready`. This restores operator access to the staging dashboard over raw HTTP. It must
not be counted as `STAGING_ACCESS_CONTROL_PASS`; HTTPS/authentication remains a separate
unmet staging hardening item.

## Exact-SHA runtime correction

The first exact-SHA runtime probe confirmed loopback-only binding, but found that Nginx
location-level cache headers suppressed inherited security headers on `/`, `index.html`,
`meta.json`, and assets. The follow-up source change explicitly applies the security
headers in every cache-specialized location. The original implementation SHA must not
be treated as the final access-control SHA.

## Safety state

```text
PR_370_KEEP_DRAFT
FORMAL_DISABLED
LOCK_DISABLED
PRODUCTION_DISABLED
MANUAL_APPROVAL_REQUIRED
```

## Dashboard V2 pixel-locked integration intake

On 2026-07-22 Asia/Shanghai, the Dashboard V2 reference pack was received as a frozen
UI-only integration task. The remote PR branch was re-fetched before editing; the actual
starting head was `641a719108264fe4307ca879b57f0566ef0901a6`. Runtime remains
`d377d6e07b300dda3fcaa0bc329d9186c488edb7`.

The three separately supplied design images match the pack's golden images byte-for-byte.
The protected baseline hash guard passes for the React component, stylesheet, fixed fixture,
view-model types, copy/behavior/pixel contracts, and all three golden screenshots.

Integration work completed without provider or backend changes:

- copied the protected reference files and contracts without modifying their bytes;
- replaced the production `BossDecisionView` render with `DashboardV2`;
- added the fixed `__visual/dashboard-v2` route;
- restricted that fixture route to Vite development/test mode and verified fixture IDs are
  absent from the production bundle;
- mapped the real V3 selected market together with its evaluated quote, model probability,
  market devig probability, delta, EV, uncertainty, scoreline projection, and readiness
  fields in the mutable adapter;
- preserved `evaluated_candidate` through the frontend API normalizer and consumed its
  canonical `analysis_evidence`; the selected-match regression now proves the exact
  bookmaker, model probability, market probability, probability delta, EV, and uncertainty
  reach the frozen presentation;
- added the protected hash guard to the all-stage check and GitHub verify workflow;
- TypeScript typecheck and production web build pass;
- 15-fixture scroll reachability, scoreline-panel constraints, and unified-ledger behavior
  tests pass;
- in-app browser interaction checks pass with no console errors.

Latest local gate results after the real V3 mapping correction:

- protected baseline guard: PASS;
- TypeScript typecheck: PASS;
- production web build: PASS;
- Dashboard decision/read-model E2E: 12/12 PASS;
- Dashboard V2 geometry/behavior E2E: 3/3 PASS;
- W2 all-stage verification, Ruff, Mypy, and Pytest: PASS (1411 passed, 4 skipped
  because local Docker/PostgreSQL parity prerequisites were not configured);
- related Dashboard Python source contracts: 6/6 PASS;
- secret scan, tracked-output check, and `git diff --check`: PASS;
- full browser suite: 15 PASS, 3 pixel comparisons FAIL for the frozen authority conflict
  below; the 0.15% threshold remains unchanged.

### Reference-pack authority conflict

The pixel gate is blocked by an internal conflict in the supplied pack, not by a protected
file edit. The golden images were produced from the hand-authored `preview/index.html` DOM,
while the protected React component renders the protected fixture differently:

- React sorts analysis fixtures by `kickoffUtc`; the golden manually places the selected
  21:00 fixture ahead of two 20:00 fixtures;
- React creates separate Shanghai date groups for `07-26` and `07-27`; the golden manually
  places the `07-27 01:00` fixture under the `07-26` header;
- several secondary row labels differ between the protected React logic and preview DOM.

With protected hashes still passing, full-page Playwright comparison reports approximately
3%, 4%, and 7% differing pixels at 2048, 1440, and 390 respectively, above the frozen 0.15%
limit. No golden was regenerated, no protected file was changed, and no threshold was
relaxed. The pack also does not contain approved scroll-bottom or scoreline-panel crop
goldens, so those states are currently verified by geometry, visibility, interaction, and
exact-copy assertions only.

Required human resolution is one of:

1. publish corrected goldens captured from the existing protected React component and
   fixture; or
2. explicitly authorize a protected React/fixture revision that matches the current
   hand-authored golden images.

Until that authority conflict is resolved:

```text
DASHBOARD_V2_PROTECTED_BASELINE_PASS
DASHBOARD_V2_ADAPTER_INTEGRATED
DASHBOARD_V2_BEHAVIOR_CONTRACT_PASS
DASHBOARD_V2_PIXEL_CONTRACT_BLOCKED_BY_REFERENCE_PACK_CONFLICT
NO_PROVIDER_CALLS
NO_MODEL_OR_BACKEND_CHANGE
NO_STAGING_DEPLOYMENT
PR_370_KEEP_DRAFT
```

The exact Dashboard V2 integration implementation commit is
`e50012cfd4bb02d7803ed57b9a77d6ffd0602b56`. It is source-review ready but is not a
staging deployment candidate until the protected React/golden authority conflict is resolved.
