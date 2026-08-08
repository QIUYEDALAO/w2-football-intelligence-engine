# W2 MI Round 2 — Codex Execution Authority

Binding current execution authority.

```text
TASK = W2_MI_R2_FIRST_DIVISION_PROVIDER_CAPABILITY_AUDIT
OWNER_AUTHORIZATION = ROUND_2_OWNER_AUTHORIZATION.md
TERMINAL_CLOSURE_AUTHORIZATION = ROUND_2_TERMINAL_CLOSURE_AUTHORIZATION.md
HYGIENE_AUTHORITY = REPOSITORY_HYGIENE_POLICY.md
ROUND_1 = PASS
ROUND_2 = AUTHORIZED_R2_C_NOW
ROUND_3 = NOT_STARTED
WAIT_14_DAYS = false
TASK_PASS_REQUIRES_REPOSITORY_HYGIENE_PASS = true
```

## 0. Read order

```text
1. ROUND_2_TERMINAL_CLOSURE_AUTHORIZATION.md
2. CURRENT_STATE.yaml
3. NEXT_ACTION.md
4. ROUND_2_OWNER_AUTHORIZATION.md
5. ROUND_2_CODEX_EXECUTION.md
6. ROUND_2_ACCEPTANCE_CRITERIA.md
7. REPOSITORY_HYGIENE_POLICY.md
8. ROUND_2_DAY0_RECEIPT.md
9. ROUND_2_OBSERVATION_LOG.md
10. ROUND_2_ACCEPTANCE_EVIDENCE_INDEX.md
11. ROUND_1_FINAL_RECEIPT.md
```

Any older statement requiring 14 elapsed days is superseded.

## 1. Established evidence

```text
AUDIT_TOOLING_PR = 494
AUDIT_TOOLING_MERGE_SHA = b04dcc7e521dce413740bcf754b1a45755a3e83e
DRY_RUN_ROWS = 17
DRY_RUN_PROVIDER_CALLS = 0
DAY0_PROVIDER_CALLS = 17
DAY0_PLAN_RESTRICTED_ROWS = 17
FIXTURES_CALLS = 0
ODDS_CALLS = 0
DEEPER_PROBE_CALLS = 0
ACTIVE_WHITELIST = 13_UNCHANGED
```

R2-B snapshot 1:

```text
DAYVIEW_CARDS = 64
DATA_INCOMPLETE = 64
CURRENT_ODDS_CARDS = 0
WITHIN_WINDOW_QUOTE_ROWS = 0
READINESS_ROWS = 5
READINESS_404_ROWS = 12
SAMPLED_ODDS_TIMELINES = 4
TIMELINE_ITEMS = 0
```

This evidence is sufficient to classify current persisted temporal evidence as insufficient/degraded. Do not wait for elapsed time solely to repeat absence.

## 2. Immediate R2-C execution

Execute now:

1. `git fetch origin main context/current --prune`.
2. Record latest exact `origin/main` and `origin/context/current` SHAs.
3. Verify PR #494 merge and Day-0 evidence identities/hashes.
4. Optionally take one final read-only freeze snapshot; default Provider calls = 0 and business writes = 0.
5. Do not wait for another daily snapshot or 2026-08-22.
6. Build exactly 17 final capability rows.
7. Preserve `PLAN_RESTRICTED` for all 17 Provider rows unless newer real evidence already exists.
8. Mark unavailable temporal distributions `TEMPORAL_EVIDENCE_INSUFFICIENT`.
9. Set `promotion_authorized=false` for every row.
10. Execute the mandatory repository-hygiene pass described below.
11. Rerun required tests after cleanup.
12. Create `ROUND_2_FINAL_RECEIPT.md` including hygiene evidence.
13. Stop/disable `w2-mi-round-2` heartbeat if Codex controls it; do not create a replacement heartbeat.
14. Update context/current to final Round 2 state.
15. Stop before Round 3.

## 3. Final 17-row truth contract

Each row must include the canonical audit ID, display name, runtime membership, audit-only flag, Provider identity/plan, Provider ID if verified, fixtures/results, AH/OU, bookmaker, lineup/injury/statistics, schema, temporal evidence, call cost, blockers/warnings, current/recommended capability state and:

```text
promotion_authorized = false
```

No unsupported field may be guessed.

## 4. Mandatory repository hygiene closure

After final capability logic is assembled and before Round 2 may be declared PASS, execute `REPOSITORY_HYGIENE_POLICY.md`.

Required:

```text
ENUMERATE_CHANGED_AND_OBSOLETE_ASSETS
CLASSIFY_KEEP_DELETE_RETAIN_FOR_EVIDENCE_REVIEW_REQUIRED
PROVE_DELETE_SAFETY_FROM_REPOSITORY_REFERENCES
DELETE_ALL_PROVABLY_DEAD_TASK_ASSETS
REMOVE_STALE_IMPORTS_EXPORTS_FLAGS_TESTS_DOCS
RERUN_REQUIRED_TESTS_AFTER_CLEANUP
```

Specifically inspect:

```text
Round 2 temporary audit scaffolding
one-off debug helpers
tracked dry-run scratch outputs
superseded audit fixtures
obsolete observation-heartbeat glue
stale 14-day-only control artifacts
duplicate task/context entrypoints
unused assets made obsolete by PR #494 or terminal closure
```

Do not delete reusable validated league-audit tooling, required migrations/history, final receipts, sanitized evidence required for traceability, CI/release authorities still used, or protected baselines.

Required final receipt metrics:

```text
REPOSITORY_HYGIENE = PASS
DEAD_ASSETS_FOUND = <count>
DEAD_ASSETS_DELETED = <count>
OBSOLETE_CODE_LINES_REMOVED = <count when measurable>
RETAINED_FOR_EVIDENCE = <list/count>
UNRESOLVED_HYGIENE_ITEMS = 0
```

## 5. Correct interpretation of PASS

Round 2 PASS means the audit and cleanup completed truthfully. It does not mean Provider capability is good.

Expected evidence class:

```text
17 / 17 Provider rows = PLAN_RESTRICTED
Temporal evidence = INSUFFICIENT_OR_DEGRADED_AS_OBSERVED
Promotion rows = 0
Repository hygiene = PASS
```

## 6. No automatic promotion / no cleanup scope creep

Forbidden:

```text
active whitelist additions
league enablement
future-refresh additions
Scheduler additions
DayView additions
new persistent collection
Provider plan/policy changes
Provider allowlist changes
Round 3
alert-threshold freeze
opportunity/value/edge semantics
Candidate/Formal/Lock/Production enablement
unrelated architecture rewrite under the name of cleanup
```

## 7. Fail-closed

```text
FAIL_CLOSED = DO_NOT_ADVANCE_PAST_FAILED_GATE
FAIL_CLOSED != WAIT_14_DAYS
FAIL_CLOSED != ABANDON_ROUND_2
```

If final matrix, cleanup, tests, receipt or context consistency fails, fix it within Round 2 and continue now. Do not restore the old time gate.

## 8. Completion

Expected final state when `ROUND_2_ACCEPTANCE_CRITERIA.md` passes:

```text
ROUND_2 = PASS_WITH_TERMINAL_PROVIDER_PLAN_RESTRICTION
ACTIVE_WHITELIST = 13_UNCHANGED
REPOSITORY_HYGIENE = PASS
ROUND_3 = NOT_STARTED
NEXT = AWAIT_OWNER_POST_R2_CAPABILITY_DECISION
```
