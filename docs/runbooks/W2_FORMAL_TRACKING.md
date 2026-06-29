# W2 Formal Recommendation Tracking

This runbook covers post-match tracking for pre-match `FORMAL` recommendations.

## Scope

- Tracking is posthoc only.
- Tracking is not a FORMAL gate.
- Snapshots are captured only before kickoff.
- Settlement uses the locked recommendation line and existing strict Asian handicap outcomes: `WIN`, `HALF_WIN`, `PUSH`, `HALF_LOSS`, `LOSS`, `VOID`.
- `PUSH` is not counted as a win.
- `VOID` is excluded from samples.

## Capture

Dry-run:

```bash
python scripts/run_w2_formal_tracking.py --mode capture --window next36 --dry-run --json
```

Write immutable artifacts:

```bash
python scripts/run_w2_formal_tracking.py --mode capture --window next36 --no-dry-run --write-artifacts --json
```

Artifacts are written to:

```text
runtime/formal_recommendation_snapshots/
```

## Settlement

```bash
python scripts/run_w2_formal_tracking.py --mode settle --no-dry-run --write-artifacts --json
```

Settlement artifacts are written to:

```text
runtime/formal_recommendation_settlements/
```

## Report

```bash
python scripts/run_w2_formal_tracking.py \
  --mode report \
  --no-dry-run \
  --write-artifacts \
  --output-report reports/w2_formal_tracking/latest/report.json \
  --json
```

The report is observing-only until each displayed bucket has at least 30 included samples. Below that threshold, `win_rate` and `roi` remain `null`.

## Verification

```bash
python scripts/check_w2_formal_tracking.py --json
```

The public summary endpoint is:

```text
/v1/formal/tracking/summary
```

