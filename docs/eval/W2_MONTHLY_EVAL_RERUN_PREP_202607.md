# W2 Monthly Eval Rerun Prep - 2026-07

## Goal

Create a repeatable, read-only entry point for the monthly W2 evaluation rerun.
This stage prepares the checklist and dry-run output only. It does not run the
formal eval, does not write runtime outputs, and does not make any R3.0 / R4.1
release decision.

## Inputs

Required structural inputs:

- `scripts/run_w2_market_baseline_eval.py`
- `scripts/run_w2_r1_1_checkpoint_dry_run.py`
- `scripts/check_w2_direction_allowed_prereg.py`
- `docs/consolidation/W2_TASK_ACCEPTANCE_LEDGER.md`
- `docs/consolidation/W2_MARKET_BASELINE_EVAL_2026_07.md`
- `docs/consolidation/W2_R4_1_MODEL_GAP_REDUCTION_EVAL_20260708.md`

Optional runtime inputs:

- `runtime/forward_outcome_ledger/`
- `runtime/market_baseline_eval/model_phase_report.json`
- `runtime/market_baseline_eval/market_phase_report.json`
- `runtime/market_baseline_eval/W2_MARKET_BASELINE_SUMMARY.md`
- `runtime/market_baseline_eval/football_data/`
- `runtime/model_artifacts/r4_1/`

Runtime files are inputs only for this dry-run. They are not committed.

## Current Rerun Semantics

The formal monthly eval is still `scripts/run_w2_market_baseline_eval.py`. It is
offline and has `provider_calls=0`, but running it writes outputs under
`runtime/market_baseline_eval/`. Therefore this PR only reports whether the
inputs are present and whether a future formal run would be structurally
possible.

## Relationship To R1.1

R1.1 is the first sample-readiness checkpoint. The monthly dry-run includes:

- double-snapshot card count
- shadow pick non-empty rate
- `clv_shadow` sample count and median
- entry-window coverage
- FT / AET / PEN outcome buckets
- provider usage summary

No settlement samples are always `ACCUMULATING`, not a numeric conclusion. Below
threshold sample counts are `NOT_ENOUGH_SAMPLE`.

## Relationship To Direction Allowed

The dry-run embeds the read-only prereg gate from
`scripts/check_w2_direction_allowed_prereg.py`.

It does not change `direction_allowed`. It can report at most that a league is
eligible for review. A later reviewer-approved PR is required before any
per-league release.

Candidate order remains:

1. `eliteserien`
2. `allsvenskan`
3. `chinese_super_league`

`brasileirao_serie_a` remains disabled by the pre-registered guard.

## Relationship To R3.0

R3.0 EV / RECOMMEND remains default off. This dry-run does not generate a
formal R3.0 decision and does not use offline log-loss or offline +EV as an
activation rule.

## Explicitly Not Included

- No provider calls.
- No DB reads or writes.
- No staging deploy.
- No production deploy.
- No scheduler restart.
- No `direction_allowed` change.
- No EV / RECOMMEND leg change.
- No Stage 16.
