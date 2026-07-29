# W2 Expert Acceptance Review Context

Generated: 2026-07-21

## GitHub Context

- PR: #370
- Expert-reviewed PR head: `a11fd2bdc97a3cd378f4becd1982f4a405fc6aff`
- Implementation head used by the prior staging probe: `301e8c229f8fb5abf06b55d43b220767e2a5a3e6`
- This file is a context sync artifact for the next acceptance pass.

## Expert Gate Conclusion

The prior closure proved that the core model/market chain is computable, but the
final label must be downgraded until V3, uncertainty, exact-head CI, staging API
canary, and formal-readiness governance are closed.

Current gate state:

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

## Required Closure Work

Do not:

- Merge PR #370.
- Enable formal recommendation.
- Enable recommendation lock.
- Enable production recommendation.
- Change thresholds or weights to force a pick.
- Treat zero sigma as validated uncertainty.

Required next execution:

1. Bind acceptance evidence to a non-skip-ci PR head.
2. Replace the prior direct analysis-card probe with a bounded canonical probe that includes
   `public_analysis_card_bounded`, `RecommendationDecisionV3`, selected/evaluated candidate,
   decision hash, quote identity hash, and parity status.
3. Reconcile fixture `1494224`: if no AH/OU market is READY with analysis edge, the V3
   candidate must either identify the true selected market or output `NO_EDGE`.
4. Add formal fail-closed behavior for `lambda_uncertainty_method=none` and zero sigma
   so `ev_se=0.0` cannot masquerade as validated certainty.
5. Preserve `EV_IMPLAUSIBLY_HIGH` for implausible formal AH candidates such as
   fixture `1494218` AWAY AH.
6. Diagnose staging API `unhealthy`/503 separately before any real public canary.

## 2026-07-21 Codex Follow-Up Execution

User instruction: fix what Codex can fix first, then regenerate a truthful report with
remaining data/service blockers for expert review.

Implemented in this follow-up:

- `public_analysis_card_bounded()` now projects `recommendation_decision_v3` into the
  public bounded card.
- `RecommendationDecisionV3` projection and validation now use the same auditable hash
  core, so V3 decisions can be independently revalidated from the payload.
- `probe_analysis_chain.py` now probes the bounded public card, V3 selected/evaluated
  candidate, decision hash, quote identity, and card/hash parity.
- Formal AH now fails closed when `lambda_uncertainty_method` is empty/`none` or both
  lambda sigma values are zero, so `ev_se=0.0` cannot be treated as validated certainty.

Staging read-only probe result after the fix:

- Fixture `1494218`: `WATCH`, `DATA_STALE_ODDS`, V3 `NOT_READY`, V3 identity `PASS`.
- Fixture `1494224`: `WATCH`, `DATA_STALE_ODDS`, V3 `NOT_READY`, V3 identity `PASS`.
- Hash parity passed for both fixtures:
  `card_hash == decision_contract.card_hash == recommendation_decision_v3.audit_refs.v2_card_hash`.
- AH/OU/first-half/score markets did not produce a current `ANALYSIS_PICK` because the
  quote gate is now stale at current evaluation time.
- `candidate=false`, `formal_recommendation=false`, `lock_eligible=false`,
  `outcome_tracked=false`.

Staging write counters after the read-only probe:

- `recommendations`: 0
- `recommendation_locks`: 0
- `forward_prediction_lock`: 0
- `gate5_recommendation_lock_event`: 0
- `shadow_strategy_lock`: 0
- No `official_locks` table exists in this staging schema.

Staging API health diagnosis:

- `/health`: 200.
- `/ready`: 503.
- Database and Redis checks pass.
- Schema check fails: `database revision does not match code head`.
- Matchday intake readiness is intentionally blocked by
  `PROVIDER_SCHEDULER_DISABLED`, `FUTURE_FIXTURE_REFRESH_DISABLED`,
  `PROVIDER_CALLS_DISABLED`, and `ALLSVENSKAN_NOT_CONFIGURED`.
- Therefore real public API canary remains blocked until staging release/schema is
  reconciled and a separately approved provider window is opened.

## Non-Codex-Only Blockers

- F5 Allsvenskan historical AH needs a licensed historical source pilot and reviewed
  provider/W2 crosswalk.
- F8 squad value needs authorized as-of roster/valuation artifacts and human-reviewed
  team/player mappings.
- Calibration and forward shadow need historical/out-of-sample and future samples.
- Human approval manifest cannot be self-issued by Codex.
