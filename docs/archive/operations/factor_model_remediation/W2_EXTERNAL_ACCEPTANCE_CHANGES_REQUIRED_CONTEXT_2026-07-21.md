# W2 PR #370 External Acceptance Context: Changes Required

Generated: 2026-07-21

## Verified Baseline

- PR: #370
- PR state: open Draft
- Verified exact head: `322df5b6fdf862fb06623d53991d505079a8fe5b`
- Verified GitHub Actions run: `29800609060`
- CI result: PASS
  - `staging-parity`: PASS
  - `predeploy-e2e`: PASS
  - PostgreSQL `verify`: PASS
  - tracked-output guard, all-stage checker, Ruff, Mypy, Pytest, Alembic smoke,
    Docker Compose, and secret scan: PASS

## Accepted Progress

The stronger label `ANALYSIS_RECOMMENDATION_CHAIN_VALIDATED` remains withdrawn.
Current labels are accepted as directionally correct:

```text
ANALYSIS_MODEL_MARKET_CHAIN_COMPUTABLE
ANALYSIS_RECOMMENDATION_ACCEPTANCE_PENDING
FORMAL_AH_BLOCKED
FORMAL_OU_NOT_IMPLEMENTED
LOCK_DISABLED
PRODUCTION_DISABLED
MANUAL_APPROVAL_REQUIRED
PR_370_KEEP_DRAFT
```

Current stale quote behavior is accepted:

```text
1494218 => WATCH / DATA_STALE_ODDS / V3 NOT_READY
1494224 => WATCH / DATA_STALE_ODDS / V3 NOT_READY
```

Formal zero-sigma gate is accepted:

```text
lambda_uncertainty_method=none or zero sigma => FORMAL_UNCERTAINTY_NOT_VALIDATED
```

## Changes Required

PR #370 remains blocked and must stay Draft until these are closed:

1. Analysis uncertainty gate:
   - `NO_EDGE` and `ANALYSIS_PICK` must require non-null candidate uncertainty/EV SE.
   - Missing uncertainty must produce V3 `NOT_READY` with
     `MODEL_UNCERTAINTY_NOT_READY`.
   - No synthetic or constant production sigma.

2. Fresh primary-market resolution:
   - Fresh decorated market decisions may be `ANALYSIS_PICK`.
   - Primary market resolution must not look only for `decision == "PICK"`.
   - Prefer canonical selection fields when available; at minimum accept both
     `PICK` and `ANALYSIS_PICK`.

3. Universal bounded V3:
   - Every `public_analysis_card_bounded()` outcome, including fail-closed paths,
     must include `recommendation_decision_v3`.
   - Reader unavailable/read failed/cross-fixture/frozen-artifact failures must have
     precise reason codes, `selected_candidate=null`, `lock_eligible=false`,
     `outcome_tracked=false`, and self-validating hashes.

4. V3 envelope integrity:
   - Core hash alone is insufficient.
   - Add envelope integrity or expand the hash to cover audit refs/statuses/warnings/
     next action/full reason.
   - Validator must enforce `card_hash == decision_contract.card_hash ==
     recommendation_decision_v3.audit_refs.v2_card_hash` when a card context is
     supplied.

5. Probe audit:
   - Remove hard-coded `provider_calls=0`.
   - Measure before/after deltas for provider request logs, raw payloads, endpoint
     captures, recommendations, lock/event tables, OFFICIAL artifacts, formal
     settlements, and cohort hash.
   - Run 20 bounded public reads and publish sanitized JSON/MD.

6. Staging release/schema:
   - `/ready=503` remains a release blocker because DB revision does not match code
     head.
   - Provider/scheduler/future refresh disabled is expected in controlled read-only
     mode and must not be enabled merely to make `/ready` return 200.

7. API/live DB/frozen parity:
   - Compare live bounded DB, frozen canary, and actual public HTTP endpoint for the
     same fixture/evaluation time.

8. Controlled fresh quote:
   - Open one separately approved fresh-quote window only if fixtures are prematch,
     or use upcoming Allsvenskan fixtures.
   - Restore provider/scheduler/future refresh disabled immediately afterward.

## Current Gate

```text
PR #370: CHANGES REQUIRED
PR STATE: KEEP DRAFT

EXACT HEAD: VERIFIED
EXACT-HEAD CI: PASS

CURRENT STALE-QUOTE FAIL-CLOSED: PASS
NORMAL-PATH V3 PROJECTION: PASS
V3 CORE HASH: PASS
FORMAL ZERO-SIGMA GATE: PASS

ANALYSIS UNCERTAINTY GATE: FAIL
FRESH-QUOTE BOUNDED V3: NOT PROVEN
PRIMARY MARKET RESOLUTION: DEFECT PRESENT
UNIVERSAL FAIL-CLOSED V3: FAIL
FULL V3 ENVELOPE INTEGRITY: PARTIAL
20-READ ZERO-WRITE AUDIT: NOT PROVEN
OFFICIAL / COHORT INVARIANTS: NOT PROVEN
STAGING SCHEMA READINESS: FAIL
REAL PUBLIC API CANARY: BLOCKED

FORMAL AH: BLOCKED
FORMAL OU: NOT IMPLEMENTED
LOCK: DISABLED
PRODUCTION: DISABLED
MANUAL_APPROVAL_REQUIRED
```
