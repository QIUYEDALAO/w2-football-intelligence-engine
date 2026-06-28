# W2 Handicap Walk-forward Calibration Runbook

This runbook covers B3/B4: authoritative Asian handicap walk-forward evidence and
the calibration gate.

## Safety Policy

- Use only locked as-of market snapshots captured before kickoff.
- Do not use current odds, closing odds, or post-kickoff odds as historical as-of data.
- Demo, staging seed, fixture examples, and synthetic rows are never authoritative.
- VOID rows are excluded from samples.
- PUSH rows stay settled but do not count as wins.
- HALF_WIN and HALF_LOSS are preserved as Asian handicap outcomes.
- `beats_market` remains false.
- FORMAL/CANDIDATE remain disabled.

## CLI

Dry run:

```bash
uv run --python 3.12 python scripts/run_w2_handicap_walkforward.py \
  --dry-run \
  --json
```

Real read-model attempt:

```bash
uv run --python 3.12 python scripts/run_w2_handicap_walkforward.py \
  --mode real \
  --from 2026-06-01 \
  --to 2026-07-31 \
  --output-report reports/w2_walkforward/latest/report.json \
  --json
```

Validate a report:

```bash
uv run --python 3.12 python scripts/check_w2_s2_readiness.py \
  reports/w2_walkforward/latest/report.json
```

## Report Interpretation

`authoritative=true` means the report source is eligible for production-grade
evidence. It does not mean rows are included. Each row must still pass:

- fixture id present
- kickoff time present
- as-of time present and before kickoff
- fair AH present
- locked market AH present
- both sides of AH odds present
- devig can be computed
- final score present
- strict AH settlement succeeds

If any requirement fails, the row is excluded with a specific reason.

## Calibration Gate

`calibration_version` stays `UNVALIDATED` until all are true:

- included sample size is at least 200
- devig market advantage passes
- time split passes
- holdout replication passes
- forward shadow passes

Even when a candidate artifact can be produced, it is not runtime enabled by this
stage. A separate explicitly approved task is required before any FORMAL/CANDIDATE
or `beats_market=true` behavior can be enabled.
