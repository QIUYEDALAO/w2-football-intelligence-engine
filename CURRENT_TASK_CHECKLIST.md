# W2 Current Task Checklist

Current mutable task authority is `origin/context/current`.

```text
PROGRAM = W2_FOOTBALL_MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
PRODUCT = W2 Football Intelligence
ROUND_1 = PASS
ROUND_2 = AUTHORIZED_R2_C_NOW
ACTIVE_PHASE = R2_C_FINAL_CAPABILITY_DECISION
WAIT_14_DAYS = false
ROUND_3 = NOT_STARTED
TASK_PASS_REQUIRES_REPOSITORY_HYGIENE_PASS = true
```

Newest authorities:

```text
ROUND_2_TERMINAL_CLOSURE_AUTHORIZATION.md
ROUND_2_ACCEPTANCE_CRITERIA.md
REPOSITORY_HYGIENE_POLICY.md
```

## R2-A — COMPLETE

```text
PR = 494
MERGE_SHA = b04dcc7e521dce413740bcf754b1a45755a3e83e
DRY_RUN_ROWS = 17
DAY0_PROVIDER_CALLS = 17
PLAN_RESTRICTED_ROWS = 17
ACTIVE_WHITELIST = 13_UNCHANGED
```

## R2-B — TERMINATED EARLY, NOT FAILED

```text
REQUIRE_WINDOW_END = false
```

Missing temporal evidence is `TEMPORAL_EVIDENCE_INSUFFICIENT`; do not wait solely for elapsed time.

## R2-C — EXECUTE NOW

- [ ] Re-fetch latest `origin/main` and `origin/context/current`.
- [ ] Verify PR #494 merge and Day-0 evidence identities/hashes.
- [ ] Optionally take one final read-only freeze snapshot; Provider calls 0, business writes 0.
- [ ] Do not wait for another daily snapshot or 2026-08-22.
- [ ] Produce exactly 17 final capability rows.
- [ ] Preserve `PLAN_RESTRICTED` unless newer real evidence exists.
- [ ] Mark missing temporal evidence `TEMPORAL_EVIDENCE_INSUFFICIENT`.
- [ ] Keep four net-new rows `AUDIT_CANDIDATE_ONLY` as current runtime state.
- [ ] Set `promotion_authorized=false` on all 17 rows.
- [ ] Confirm active whitelist remains exact 13.
- [ ] Confirm Provider policy/allowlist/Scheduler diffs = EMPTY.
- [ ] Confirm Candidate/Formal/Lock/Production remain OFF.
- [ ] Confirm Round 3 remains NOT_STARTED.

## Mandatory repository hygiene before PASS

Execute `REPOSITORY_HYGIENE_POLICY.md` after the final capability logic is assembled and before final task acceptance.

- [ ] Enumerate files/assets added, changed, superseded or exposed as obsolete by Round 2.
- [ ] Classify every candidate asset as `KEEP`, `DELETE`, `RETAIN_FOR_EVIDENCE`, or `REVIEW_REQUIRED`.
- [ ] Prove deletion safety using imports/references/entrypoints/workflows/config/test/CI evidence.
- [ ] Delete all provably dead task assets.
- [ ] Remove dead imports/exports/flags/tests/docs references after deletion.
- [ ] Inspect temporary audit scaffolding, debug helpers, scratch outputs, obsolete heartbeat glue, stale 14-day-only control assets, duplicate task/context entrypoints and superseded fixtures.
- [ ] Do not delete reusable audit tooling, migrations/history, final receipts, required sanitized audit evidence or protected baselines.
- [ ] Rerun required focused/static/contract tests after cleanup.
- [ ] Record hygiene metrics in `ROUND_2_FINAL_RECEIPT.md`.

Required closure fields:

```text
REPOSITORY_HYGIENE = PASS
DEAD_ASSETS_FOUND = <count>
DEAD_ASSETS_DELETED = <count>
OBSOLETE_CODE_LINES_REMOVED = <count when measurable>
RETAINED_FOR_EVIDENCE = <list/count>
UNRESOLVED_HYGIENE_ITEMS = 0
```

## Round 2 completion

```text
ROUND_2 = PASS_WITH_TERMINAL_PROVIDER_PLAN_RESTRICTION
ACTIVE_WHITELIST = 13_UNCHANGED
AUDIT_UNION = 17_COMPLETE_WITH_TRUTHFUL_OUTCOMES
NET_NEW_AUDIT_CANDIDATES = 4_NOT_ENABLED
WAIT_14_DAYS = false
REPOSITORY_HYGIENE = PASS
ROUND_3 = NOT_STARTED
NEXT = AWAIT_OWNER_POST_R2_CAPABILITY_DECISION
```

## Permanent stop lines

```text
BETTING_EDGE_CLAIM = FORBIDDEN
MODEL_DIVERGENCE_AS_OPPORTUNITY = FORBIDDEN
ACTIVE_WHITELIST_CHANGE = false
PRODUCTION_PROVIDER_POLICY_CHANGE = false
PRODUCTION_PROVIDER_ALLOWLIST_CHANGE = false
PRODUCTION_SCHEDULER_POLICY_CHANGE = false
NEW_PERSISTENT_COLLECTION_FOR_NET_NEW = false
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
REAL_MONEY = NOT_AUTHORIZED
```
