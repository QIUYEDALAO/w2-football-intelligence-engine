> SUPERSEDED_BY: `docs/operations/factor_model_remediation/W2_DIRECT_HOTPATCH_DEPLOYMENT_CONTEXT_2026-07-21.md`
> SUPERSEDED_BY_DEPLOYED_SHA: `f631bc11f7641791618f4a0d245fce8fe1732740`
> SUPERSEDED_REASON: Final exact-image staging canary replaced the earlier pending/503/uncertainty-null evidence. This report is retained as historical audit context only.

# W2 PR #370 Changes Required Remediation Report

Generated: 2026-07-21

## Status

```text
PR #370: CHANGES REQUIRED
PR STATE: KEEP DRAFT

ANALYSIS_MODEL_MARKET_CHAIN_COMPUTABLE
ANALYSIS_RECOMMENDATION_ACCEPTANCE_PENDING
FORMAL_AH_BLOCKED
FORMAL_OU_NOT_IMPLEMENTED
LOCK_DISABLED
PRODUCTION_DISABLED
MANUAL_APPROVAL_REQUIRED
```

## Code Remediation Completed

1. Analysis uncertainty gate:
   - AH/OU analysis evidence now requires validated lambda uncertainty.
   - `lambda_uncertainty_method=none`, missing sigma, or zero sigma fails closed.
   - Missing uncertainty now produces `MODEL_UNCERTAINTY_NOT_READY`.
   - `NO_EDGE` and `ANALYSIS_PICK` can no longer be produced from `ev_se=null`.

2. Fresh primary-market resolution:
   - Public dashboard projection no longer searches only for `decision == "PICK"`.
   - It accepts canonical pick decisions `PICK`, `ANALYSIS_PICK`, and `RECOMMEND`.
   - It also respects `selection_role=PRIMARY`, `quote_usage=EXECUTABLE`, and
     `market_candidate.ev_eligible`.

3. Universal bounded V3:
   - Bounded reader unavailable/read failed/cross-fixture/fallback paths now attach V3.
   - Frozen artifact failure paths now attach V3.
   - Fail-closed V3 has `selected_candidate=null`, precise reason code,
     `lock_eligible=false`, `outcome_tracked=false`, core hash, and envelope hash.

4. V3 envelope integrity:
   - V3 now includes `decision_envelope_hash`.
   - Validator checks both `decision_hash` and `decision_envelope_hash`.
   - Card parity validation checks:

```text
card_hash == decision_contract.card_hash == recommendation_decision_v3.audit_refs.v2_card_hash
```

5. Probe safety audit:
   - `scripts/probe_analysis_chain.py` no longer prints hard-coded `provider_calls=0`.
   - It records before/after table counts and content hashes.
   - It supports `--read-count 20`.

## Local Verification

```text
uv run pytest tests/unit/test_recommendation_decision_v3.py \
  tests/unit/test_public_analysis_card_bounded.py \
  tests/unit/test_frozen_analysis_canary_read.py \
  tests/unit/test_analysis_market_evidence.py \
  tests/unit/test_market_candidate.py -q

41 passed

uv run ruff check src/w2/markets/analysis_evidence.py \
  src/w2/domain/recommendation_decision_v3.py \
  src/w2/api/repository.py \
  scripts/probe_analysis_chain.py \
  tests/unit/test_recommendation_decision_v3.py \
  tests/unit/test_public_analysis_card_bounded.py \
  tests/unit/test_frozen_analysis_canary_read.py \
  tests/unit/test_analysis_market_evidence.py \
  tests/unit/test_market_candidate.py

All checks passed
```

## Staging 20-Read Zero-Write Audit

Execution controls:

```text
W2_PROVIDER_SCHEDULER_ENABLED=false
W2_PROVIDER_CALLS_DISABLED=true
```

Command:

```text
scripts/probe_analysis_chain.py --read-count 20 1494218 1494224
```

Result:

```text
zero_write_pass=true
```

All audited tables had `count_delta=0` and unchanged content hash:

- `provider_request_logs`
- `raw_payload_references`
- `matchday_endpoint_captures`
- `matchday_evidence_manifests`
- `recommendations`
- `recommendation_locks`
- `forward_prediction_lock`
- `gate5_recommendation_lock_event`
- `shadow_strategy_lock`
- `shadow_strategy_event`
- `shadow_strategy_settlement`
- `settlements`

Sanitized JSON:

```text
docs/operations/factor_model_remediation/W2_PR370_20_READ_ZERO_WRITE_AUDIT_2026-07-21.json
```

## Fixture Results

| Fixture | Decision | Reason | V3 | V3 Identity | Envelope | Pick |
| --- | --- | --- | --- | --- | --- | --- |
| `1494218` | `WATCH` | `DATA_STALE_ODDS` | `NOT_READY` | `PASS` | present | none |
| `1494224` | `WATCH` | `DATA_STALE_ODDS` | `NOT_READY` | `PASS` | present | none |

Both fixtures passed hash parity:

```text
card_hash == decision_contract.card_hash == v3.audit_refs.v2_card_hash
```

## Still Blocked

- Staging `/ready=503` remains a release blocker because DB revision does not match code head.
- Real public API/live DB/frozen parity still requires staging exact-SHA release/schema reconciliation.
- Fresh-quote bounded V3 still requires a separately approved controlled provider window or new real upcoming fixtures.
- Formal AH remains blocked by F5/F8/calibration/offline/forward/human approval.
- Formal OU is not implemented.

## Final Gate

```text
ANALYSIS UNCERTAINTY GATE: REMEDIATED
PRIMARY MARKET RESOLUTION: REMEDIATED
UNIVERSAL FAIL-CLOSED V3: REMEDIATED
FULL V3 ENVELOPE INTEGRITY: REMEDIATED
20-READ ZERO-WRITE AUDIT: PASS

STAGING SCHEMA READINESS: FAIL
REAL PUBLIC API CANARY: BLOCKED
FRESH-QUOTE BOUNDED V3: REQUIRES CONTROLLED PROVIDER WINDOW

FORMAL AH: BLOCKED
FORMAL OU: NOT_IMPLEMENTED
LOCK: DISABLED
PRODUCTION: DISABLED
MANUAL_APPROVAL_REQUIRED
```
