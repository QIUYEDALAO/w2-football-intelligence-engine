# NEXT ACTION

```text
ACTIVE_NEXT_ACTION = W2_MI_R2_C_FINAL_CAPABILITY_DECISION_NOW
ROUND_1 = PASS
ROUND_2 = AUTHORIZED_R2_C_NOW
ROUND_3 = NOT_STARTED
WAIT_14_DAYS = false
```

Newest authorities:

```text
ROUND_2_TERMINAL_CLOSURE_AUTHORIZATION.md
REPOSITORY_HYGIENE_POLICY.md
```

They supersede all older instructions that require R2-B to remain open until 2026-08-22 and make repository hygiene mandatory before task PASS.

## Execute now

Codex must re-fetch `origin/main` and `origin/context/current`, then immediately perform R2-C.

Required sequence:

```text
1. verify latest main/context SHAs
2. verify PR #494 merge + Day-0 receipt + ledger/evidence hashes
3. optionally take one final read-only persisted-evidence freeze snapshot
4. make 0 new Provider calls by default
5. do not wait for another daily snapshot
6. do not wait until 2026-08-22
7. build the final 17-row capability matrix
8. preserve PLAN_RESTRICTED for all 17 Provider rows unless newer real evidence exists
9. mark absent temporal evidence TEMPORAL_EVIDENCE_INSUFFICIENT
10. set promotion_authorized=false on all 17 rows
11. execute REPOSITORY_HYGIENE_POLICY.md against Round 2 changes and newly obsolete assets
12. delete every provably dead/unused Round 2 code/file/asset and remove resulting stale references
13. rerun required focused/static/contract tests after cleanup
14. create ROUND_2_FINAL_RECEIPT.md including hygiene evidence
15. stop/disable w2-mi-round-2 heartbeat if Codex controls it
16. update context/current to final Round 2 state
17. stop before Round 3
```

## Frozen evidence

```text
AUDIT_TOOLING_PR = 494
AUDIT_TOOLING_MERGE_SHA = b04dcc7e521dce413740bcf754b1a45755a3e83e
AUDIT_UNION = 17
DAY0_PROVIDER_CALLS = 17
PLAN_RESTRICTED_ROWS = 17
FIXTURES_CALLS = 0
ODDS_CALLS = 0
DEEPER_PROBE_CALLS = 0
ACTIVE_WHITELIST = 13_UNCHANGED
```

Persisted snapshot truth:

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

Do not turn missing evidence into invented distributions.

## Hygiene completion requirement

Round 2 cannot be marked PASS until:

```text
REPOSITORY_HYGIENE = PASS
UNRESOLVED_HYGIENE_ITEMS = 0
```

Do not delete reusable audit tooling or required historical/audit evidence just to reduce file count. Delete only assets proven dead by repository evidence.

## Completion target

If revised `ROUND_2_ACCEPTANCE_CRITERIA.md` passes:

```text
ROUND_2 = PASS_WITH_TERMINAL_PROVIDER_PLAN_RESTRICTION
ACTIVE_WHITELIST = 13_UNCHANGED
NET_NEW_RUNTIME_PROMOTIONS = 0
REPOSITORY_HYGIENE = PASS
ROUND_3 = NOT_STARTED
NEXT = AWAIT_OWNER_POST_R2_CAPABILITY_DECISION
```

Permanent guards remain unchanged: no Provider/Scheduler policy changes, no persistent net-new collection, no league enablement, Candidate/Formal/Lock/Production OFF, no betting-edge/opportunity semantics.