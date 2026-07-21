# W2 Analysis Acceptance Pending Report

Generated: 2026-07-21

## Status

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

## Scope

This follow-up fixes Codex-resolvable read-model and factor-projection defects only.
It does not enable formal recommendation, lock, production, provider scheduling, or
new calibration.

## What Was Fixed

- `public_analysis_card_bounded()` now includes `RecommendationDecisionV3`.
- The bounded probe now reads `public_analysis_card_bounded()` instead of the legacy
  direct analysis card.
- V3 selected/evaluated candidate, decision hash, quote identity, and card/hash parity
  are included in probe output.
- V3 projection hash generation now matches `validate_decision_v3_identity()`.
- Formal AH now fails closed when lambda uncertainty is not validated:
  empty/`none` method or zero sigma cannot produce formal acceptance.

## Local Verification

```text
uv run pytest tests/unit/test_recommendation_decision_v3.py \
  tests/unit/test_public_analysis_card_bounded.py \
  tests/unit/test_formal_recommendation_rules.py -q

52 passed

uv run ruff check src/w2/domain/recommendation_decision_v3.py \
  src/w2/api/repository.py \
  src/w2/strategy/formal_recommendation.py \
  scripts/probe_analysis_chain.py \
  tests/unit/test_recommendation_decision_v3.py \
  tests/unit/test_formal_recommendation_rules.py

All checks passed
```

## Staging Read-Only Probe

Execution controls:

```text
W2_PROVIDER_SCHEDULER_ENABLED=false
W2_PROVIDER_CALLS_DISABLED=true
```

Probe method:

```text
ReadModelService.public_analysis_card_bounded(fixture_id, use_frozen_canary=False)
```

Results:

| Fixture | Decision | Reason | V3 outcome | V3 identity | Pick |
| --- | --- | --- | --- | --- | --- |
| `1494218` | `WATCH` | `DATA_STALE_ODDS` | `NOT_READY` | `PASS` | none |
| `1494224` | `WATCH` | `DATA_STALE_ODDS` | `NOT_READY` | `PASS` | none |

Hash parity passed for both fixtures:

```text
card_hash == decision_contract.card_hash == recommendation_decision_v3.audit_refs.v2_card_hash
```

Current market projection:

- AH: `SKIP`, no model/market probability emitted because quote gate is stale.
- OU: `SKIP`, no model/market probability emitted because quote gate is stale.
- First-half goals: `WATCH`.
- Score: `NO_EDGE`.

Fixture `1494224` reconciliation:

```text
Current bounded V3 does not produce ANALYSIS_PICK.
At current evaluation time it is WATCH / DATA_STALE_ODDS.
There is no current selected candidate and no AH/OU market READY with an analysis edge.
```

## Zero-Write Guard

Staging table counts after the read-only probe:

| Table | Count |
| --- | ---: |
| `recommendations` | 0 |
| `recommendation_locks` | 0 |
| `forward_prediction_lock` | 0 |
| `gate5_recommendation_lock_event` | 0 |
| `shadow_strategy_lock` | 0 |

No `official_locks` table exists in the current staging schema.

## Staging API Health

Endpoint diagnosis:

| Endpoint | Status |
| --- | --- |
| `/health` | 200 |
| `/ready` | 503 |

`/ready` details:

- database: `PASS`
- redis: `PASS`
- mounts: `PASS`
- artifacts: `PASS`
- schema: `FAIL`, `database revision does not match code head`
- matchday intake: `NOT_READY`

Current matchday intake blockers:

```text
PROVIDER_SCHEDULER_DISABLED
FUTURE_FIXTURE_REFRESH_DISABLED
PROVIDER_CALLS_DISABLED
ALLSVENSKAN_NOT_CONFIGURED
```

The provider/scheduler blockers are intentional for this controlled read-only follow-up.
The schema mismatch remains a staging release/canary blocker.

## What Still Cannot Be Claimed

- Fresh exact quote is not available now for fixtures `1494218` and `1494224`; both are
  stale at current evaluation time.
- Candidate-level `model_probability`, `market_probability`, `delta`, `EV`, and
  `uncertainty` cannot be emitted for these fixtures after the stale quote gate closes.
- `ANALYSIS_PICK` cannot be accepted for fixture `1494224` at current evaluation time.
- Formal AH remains blocked by missing accepted uncertainty/calibration/F5/F8/offline/
  forward/human-approval evidence.
- Formal OU is not implemented.
- Real public API canary is blocked until staging schema/head are reconciled.

## Remaining Non-Codex-Only Inputs

- F5 Allsvenskan historical AH licensed source and reviewed provider/W2 crosswalk.
- F8 authorized as-of roster/valuation artifact and reviewed mappings.
- Real calibration and forward-shadow samples.
- Human approval manifest with reviewer, review time, code SHA, factor registry SHA,
  and artifact hashes.

## Final Gate

```text
ANALYSIS_MODEL_MARKET_CHAIN_COMPUTABLE
ANALYSIS_RECOMMENDATION_ACCEPTANCE_PENDING
FORMAL_DISABLED
LOCK_DISABLED
PRODUCTION_DISABLED
MANUAL_APPROVAL_REQUIRED
```
