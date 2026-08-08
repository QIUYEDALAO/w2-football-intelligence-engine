# W2 MI Round 2 — Codex Execution Authority

Binding current execution authority.

```text
TASK = W2_MI_R2_FIRST_DIVISION_PROVIDER_CAPABILITY_AUDIT
OWNER_AUTHORIZATION = ROUND_2_OWNER_AUTHORIZATION.md
TERMINAL_CLOSURE_AUTHORIZATION = ROUND_2_TERMINAL_CLOSURE_AUTHORIZATION.md
ROUND_1 = PASS
ROUND_2 = AUTHORIZED_R2_C_NOW
ROUND_3 = NOT_STARTED
WAIT_14_DAYS = false
```

## 0. Precedence

Read in this order:

```text
1. ROUND_2_TERMINAL_CLOSURE_AUTHORIZATION.md
2. CURRENT_STATE.yaml
3. NEXT_ACTION.md
4. ROUND_2_OWNER_AUTHORIZATION.md
5. ROUND_2_CODEX_EXECUTION.md
6. ROUND_2_ACCEPTANCE_CRITERIA.md
7. ROUND_2_DAY0_RECEIPT.md
8. ROUND_2_OBSERVATION_LOG.md
9. ROUND_2_ACCEPTANCE_EVIDENCE_INDEX.md
10. ROUND_1_FINAL_RECEIPT.md
```

Any older statement requiring 14 elapsed days is superseded.

## 1. Established evidence

R2-A is complete:

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

R2-B snapshot 1 established:

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

This is enough to classify current persisted temporal evidence as insufficient/degraded. Do not wait for time to pass solely to repeat the same absence.

## 2. Immediate R2-C execution

Execute now:

```text
ACTIVE_NEXT_ACTION = W2_MI_R2_C_FINAL_CAPABILITY_DECISION_NOW
```

Sequence:

1. `git fetch origin main context/current --prune`.
2. Record latest exact `origin/main` and `origin/context/current` SHAs.
3. Verify PR #494 merge SHA and Day-0 evidence hashes/ledger identities.
4. If needed, take one final read-only snapshot only to freeze the current persisted evidence state.
5. New Provider calls default to 0. Do not repeat `/leagues`, fixtures, odds or deeper probes merely to re-prove `PLAN_RESTRICTED`.
6. Do not wait for the next daily snapshot or the former 2026-08-22 deadline.
7. Build exactly 17 final capability rows.
8. Preserve `PLAN_RESTRICTED` as the Provider audit outcome for all 17 unless newer real evidence already exists.
9. Mark unavailable temporal distributions `TEMPORAL_EVIDENCE_INSUFFICIENT`.
10. Set `promotion_authorized=false` on all 17 rows.
11. Produce `ROUND_2_FINAL_RECEIPT.md`.
12. Update `CURRENT_STATE.yaml`, `NEXT_ACTION.md`, `CURRENT_TASK_CHECKLIST.md`, agent handoff files and Copilot instructions to the final Round 2 state.
13. Stop/disable the `w2-mi-round-2` heartbeat if Codex controls it. Do not create a replacement heartbeat.
14. Stop before Round 3.

## 3. Final 17-row required fields

Each row must include at least:

```text
canonical_audit_id
display_name
current_runtime_membership
audit_only_candidate
provider_identity_status
provider_plan_status
provider_league_id_if_verified
future_fixture_status
result_fixture_status
ah_status
ou_status
bookmaker_depth_status
lineup_status
injury_status
statistics_status
schema_status
temporal_evidence_status
provider_call_cost
blockers
warnings
current_capability_state
recommended_future_capability_state
promotion_authorized
```

No unsupported field may be guessed.

## 4. Correct interpretation of PASS

Round 2 PASS means the audit process completed truthfully.

It does **not** mean the Provider currently supports these leagues for W2.

Expected evidence class:

```text
17 / 17 Provider rows = PLAN_RESTRICTED
Temporal evidence = INSUFFICIENT_OR_DEGRADED_AS_OBSERVED
Promotion rows = 0
```

## 5. No automatic promotion

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
```

## 6. Fail-closed

```text
FAIL_CLOSED = DO_NOT_ADVANCE_PAST_FAILED_GATE
FAIL_CLOSED != WAIT_14_DAYS
FAIL_CLOSED != ABANDON_ROUND_2
```

If final matrix/report/context consistency fails, fix it within Round 2 and continue now. Do not restore the old time gate.

## 7. Completion

Round 2 can close when revised `ROUND_2_ACCEPTANCE_CRITERIA.md` passes.

Expected final state:

```text
ROUND_2 = PASS_WITH_TERMINAL_PROVIDER_PLAN_RESTRICTION
ACTIVE_WHITELIST = 13_UNCHANGED
ROUND_3 = NOT_STARTED
NEXT = AWAIT_OWNER_POST_R2_CAPABILITY_DECISION
```