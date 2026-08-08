# W2 MI Round 2 — Acceptance Evidence Index

```text
ROUND_2 = AUTHORIZED_IN_PROGRESS
R2_A = COMPLETE_WITH_TRUTHFUL_PLAN_RESTRICTIONS
R2_B = ACTIVE
R2_C = BLOCKED_UNTIL_R2_B_WINDOW_COMPLETE
ROUND_3 = NOT_STARTED
```

This is an evidence map, not a final acceptance receipt. Every satisfied or
ongoing invariant must be reverified at finalization.

| Gate | Current status | Authoritative evidence | Remaining proof |
|---|---|---|---|
| A. Source and authority | SATISFIED_REVERIFY_FINAL | `ROUND_2_DAY0_RECEIPT.md`; initial/execution SHA `f786081...`; merge `b04dcc7...` | Re-fetch both authorities and prove Round 3 remains not started |
| B. Audit universe | SATISFIED_REVERIFY_FINAL | 17-row dry-run; Day-0 matrix; whitelist diff empty | Recount exact 13+4 and verify no runtime additions |
| C. Audit-only isolation | SATISFIED_REVERIFY_FINAL | PR #494 isolation tests; `config/audit_candidates/` namespace; 67 focused tests | Re-run protected-path/runtime reachability checks |
| D. Audit-tooling PR scope | SATISFIED | PR #494 only; head `581d970...`; merge `b04dcc7...`; Provider calls in PR/CI = 0 | Preserve immutable PR/CI evidence |
| E. Dry-run contract | SATISFIED | 17 unique rows; Provider calls 0; business/checkpoint writes 0; SHA in Day-0 receipt | Preserve artifact/hash |
| F. Net-new identity | SATISFIED_BLOCKED_OUTCOME | All four net-new rows = `PLAN_RESTRICTED`; no guessed IDs; deeper calls 0 | Carry exact blocker into final rows |
| G. Ledger integrity | SATISFIED | 17 calls = 17 sanitized records; duplicate index 0; ledger SHA in Day-0 receipt | Reconcile cumulative total at finalization |
| H. Budget and reserve | SATISFIED_REVERIFY_FINAL | Day-0 actual/daily/cumulative = 17; minimum interval 11s; no retry | Confirm no later audit calls and cumulative <=200 |
| I. Hard stops | SATISFIED | 17 `PLAN_DOES_NOT_COVER_SEASON` stops; no later endpoint calls; persistent ledger | Preserve stop evidence and no retry |
| J. Day-0 baseline | SATISFIED_WITH_PLAN_RESTRICTIONS | 17-row matrix; 17/68 calls; all required fields; no unsupported capability claims | Preserve matrix/hash |
| K. Deep probes | NOT_APPLICABLE_NO_ELIGIBLE_ROWS | Identity/plan gate failed for all 17; deeper calls = 0 | Do not reinterpret absence as capability |
| L. AH/OU and bookmaker truth | SATISFIED_AS_BLOCKED | Day-0 marks markets not audited; public reference-only evidence is not promoted to completeness | Keep per-fixture depth distinct from league-level distinct bookmaker names |
| M. 14-day observation | IN_PROGRESS_TIME_GATE | `ROUND_2_OBSERVATION_LOG.md`; start/end frozen | Cannot complete before `2026-08-22T01:53:55.509495+00:00` |
| N. Descriptive distributions | IN_PROGRESS_INSUFFICIENT_SO_FAR | Snapshot 1 has zero within-window quote rows; pre-window overround context explicitly segregated | At end, report real distributions or `TEMPORAL_EVIDENCE_INSUFFICIENT` per league×market |
| O. Final 17-row matrix | BLOCKED_NOT_DUE | Day-0 matrix is not the final matrix | Build exactly 17 final rows only after M completes |
| P. No automatic promotion | ONGOING_INVARIANT | Active whitelist 13; new enabled/scheduled/DayView rows 0 | Reverify final runtime state |
| Q. Product semantics | ONGOING_INVARIANT | Intelligence-first context; no edge/value/opportunity interpretation | Reverify final wording and outputs |
| R. Runtime/safety | ONGOING_INVARIANT | Production Provider/allowlist/Scheduler diffs empty; persistent jobs 0; all lifecycle gates OFF | Re-run exact protected-path and runtime checks |
| S. Evidence hygiene | SATISFIED_REVERIFY_FINAL | Secret scans passed; ledger sanitized; no raw payloads or credentials persisted | Scan final context/artifacts |
| T. Completion receipt | BLOCKED_NOT_DUE | R2-A/Day-0 receipt exists but explicitly is not final | Produce complete final receipt only after M/N/O |

## Frozen evidence identities

```text
ROUND2_INITIAL_MAIN_SHA = f7860813646ce9718931dff331c09ce2fe7a71ba
ROUND2_EXECUTION_BASE_SHA = f7860813646ce9718931dff331c09ce2fe7a71ba
AUDIT_TOOLING_PR_NUMBER = 494
AUDIT_TOOLING_FINAL_HEAD_SHA = 581d970aab0bec8df34ae5a211a20c1c50cb7948
AUDIT_TOOLING_MERGE_SHA = b04dcc7e521dce413740bcf754b1a45755a3e83e
DAY0_DRY_RUN_SHA256 = 458e6648004d5c1489ca544758b06dad1c93bcd7583df7f70ddd7b9c3fd91b44
DAY0_17_ROW_MATRIX_SHA256 = 85df3fd4d03296d96262dd2c0d8ed72fdeff097b66423ab45cb47d39ad583e23
SANITIZED_PROVIDER_LEDGER_SHA256 = 498c53d146117902ce22c49644e257a6fa4dcede148e11867b33d46d43cea37e
```

## Finalization sequence after the time gate

Only after the exact observation end:

1. Re-fetch `origin/main` and `origin/context/current` and record drift.
2. Reverify the 13 active identities and four audit-only identities.
3. Read existing persisted evidence only; do not backfill or create collection.
4. Produce league×market descriptive evidence or truthful insufficiency outcomes.
5. Build exactly 17 final capability rows with `promotion_authorized = false`.
6. Reverify Provider/allowlist/Scheduler diffs, lifecycle gates and secret hygiene.
7. Produce the binding Round 2 completion receipt.
8. Stop before Round 3 and await an owner capability decision.
