# W2 Current Task Checklist

Current mutable task authority is `origin/context/current`.

## Program status

```text
PROGRAM = W2_FOOTBALL_MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
PRODUCT = W2 Football Intelligence
ROUND_1 = PASS
ROUND_2 = AUTHORIZED_R2_C_NOW
ACTIVE_TASK = W2_MI_R2_FIRST_DIVISION_PROVIDER_CAPABILITY_AUDIT
ACTIVE_PHASE = R2_C_FINAL_CAPABILITY_DECISION
WAIT_14_DAYS = false
ROUND_3 = NOT_STARTED
```

Newest owner override:

```text
ROUND_2_TERMINAL_CLOSURE_AUTHORIZATION.md
```

It supersedes the former fourteen-day elapsed-time requirement.

## MI-R2 status

### R2-A — COMPLETE

```text
STATUS = COMPLETE_WITH_TRUTHFUL_PLAN_RESTRICTIONS
PR = 494
MERGE_SHA = b04dcc7e521dce413740bcf754b1a45755a3e83e
DRY_RUN_ROWS = 17
DRY_RUN_PROVIDER_CALLS = 0
DAY0_PROVIDER_CALLS = 17
PLAN_RESTRICTED_ROWS = 17
FIXTURES_CALLS = 0
ODDS_CALLS = 0
DEEPER_PROBE_CALLS = 0
ACTIVE_WHITELIST = 13_UNCHANGED
```

### R2-B — CLOSED EARLY BY OWNER TERMINAL-EVIDENCE AUTHORITY

```text
STATUS = TERMINATED_EARLY_NOT_FAILED
REQUIRE_WINDOW_END = false
```

Snapshot 1 truth:

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

Rule:

```text
MISSING_REAL_TEMPORAL_EVIDENCE => TEMPORAL_EVIDENCE_INSUFFICIENT
```

Do not wait for additional days solely to satisfy elapsed time.

### R2-C — EXECUTE NOW

```text
STATUS = AUTHORIZED_NOW
```

Checklist:

- [ ] Re-fetch latest `origin/main` and `origin/context/current`.
- [ ] Verify PR #494 merge identity and Day-0 receipt/ledger/evidence hashes.
- [ ] Optionally take one final read-only persisted-evidence freeze snapshot; Provider calls 0, business writes 0.
- [ ] Do not wait for another daily snapshot.
- [ ] Do not wait until 2026-08-22.
- [ ] Produce exactly 17 unique final capability rows.
- [ ] Preserve `PLAN_RESTRICTED` for all 17 Provider rows unless newer real evidence exists.
- [ ] Mark unsupported temporal evidence `TEMPORAL_EVIDENCE_INSUFFICIENT`.
- [ ] Record Provider identity/plan/fixtures/results/AH/OU/bookmaker/lineup/injury/statistics/schema/call-cost truth without guessing.
- [ ] Keep four net-new rows `AUDIT_CANDIDATE_ONLY` as current runtime state.
- [ ] Set `promotion_authorized=false` on all 17 rows.
- [ ] Confirm active whitelist remains exact 13.
- [ ] Confirm new enabled/scheduled/DayView leagues = 0.
- [ ] Confirm production Provider policy/allowlist/Scheduler diffs = EMPTY.
- [ ] Confirm Candidate/Formal/Lock/Production remain OFF.
- [ ] Confirm Round 3 remains NOT_STARTED.
- [ ] Create `ROUND_2_FINAL_RECEIPT.md`.
- [ ] Stop/disable `w2-mi-round-2` heartbeat if Codex controls it; do not create replacement heartbeat.
- [ ] Update context/current to final Round 2 state.

## Round 2 completion

If revised `ROUND_2_ACCEPTANCE_CRITERIA.md` passes:

```text
ROUND_2 = PASS_WITH_TERMINAL_PROVIDER_PLAN_RESTRICTION
ACTIVE_WHITELIST = 13_UNCHANGED
AUDIT_UNION = 17_COMPLETE_WITH_TRUTHFUL_OUTCOMES
NET_NEW_AUDIT_CANDIDATES = 4_NOT_ENABLED
WAIT_14_DAYS = false
ROUND_3 = NOT_STARTED
NEXT = AWAIT_OWNER_POST_R2_CAPABILITY_DECISION
```

## Permanent stop lines

```text
BETTING_EDGE_CLAIM = FORBIDDEN
MODEL_DIVERGENCE_AS_OPPORTUNITY = FORBIDDEN
SIGNAL_LEDGER_FOR_EXECUTION = NOT_AUTHORIZED
PORTFOLIO = NOT_AUTHORIZED
RISK_KELLY = NOT_AUTHORIZED
TWO_LEG_PARLAY = NOT_AUTHORIZED
REAL_MONEY = NOT_AUTHORIZED
ACTIVE_WHITELIST_CHANGE = false
PRODUCTION_PROVIDER_POLICY_CHANGE = false
PRODUCTION_PROVIDER_ALLOWLIST_CHANGE = false
PRODUCTION_SCHEDULER_POLICY_CHANGE = false
NEW_PERSISTENT_COLLECTION_FOR_NET_NEW = false
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
```
