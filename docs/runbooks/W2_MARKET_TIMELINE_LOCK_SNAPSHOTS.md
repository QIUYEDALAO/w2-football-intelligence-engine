# W2 Market Timeline Lock Snapshots

This runbook covers the M1 market timeline artifact path used to unblock B3
as-of handicap walk-forward samples.

## Scope

- Artifact path: `runtime/market_timeline_snapshots/<fixture_id>.json`
- Schema version: `w2.market_timeline.v1`
- Checkpoints: `opening`, `T-24h`, `T-12h`, `T-6h`, `T-3h`, `T-1h`, `lock`
- Markets: `ASIAN_HANDICAP`, `TOTALS`
- Asian handicap sign convention: the stored `line` is the home-team line;
  negative means home gives goals.

Snapshots are immutable once written. A checkpoint-market pair with the same
source hash is idempotent; a different source hash is rejected as an immutable
conflict.

## Refresh

Preview from existing read-model/runtime observations:

```bash
uv run --python 3.12 python scripts/run_w2_market_timeline_refresh.py \
  --window next36 \
  --checkpoint auto \
  --dry-run \
  --json
```

Artifact writes require both flags:

```bash
uv run --python 3.12 python scripts/run_w2_market_timeline_refresh.py \
  --window next36 \
  --checkpoint auto \
  --no-dry-run \
  --write-artifacts \
  --json
```

The script reports `provider_calls=0` for the current artifact-first path. Any
future provider fallback must remain behind quota guard and must not take reserve
from prematch odds or lineups.

## Automation

Staging enables the scheduler flag `W2_MARKET_TIMELINE_REFRESH_ENABLED=true`.
The scheduler queues `w2.market_timeline_refresh` every 10 minutes with:

- `window=next36`
- `checkpoint=auto`
- `write_artifacts=true`
- `max_fixtures=10`

The worker writes only due checkpoints. `opening` may be written early, T-* checkpoints
are written only inside their short due window, and `lock` is written only inside the
pre-kickoff lock window. Missed checkpoints remain missing; the job must not use
current odds to backfill a past checkpoint.

## Check

```bash
uv run --python 3.12 python scripts/check_w2_market_timeline.py \
  --window next36 \
  --json
```

Missing lock snapshots are warnings. Schema errors, non-immutable snapshots, and
post-kickoff `as_of` values are failures.

## Walk-Forward

```bash
uv run --python 3.12 python scripts/run_w2_handicap_walkforward.py \
  --mode real \
  --from 2026-06-01 \
  --to 2026-07-31 \
  --output-report /tmp/w2_walkforward_with_locks.json \
  --json
```

A valid `lock` snapshot removes `MISSING_AS_OF` for the fixture. It does not
calibrate the model, set `beats_market=true`, or unlock FORMAL/CANDIDATE.

## Dashboard Movement / Hypothesis Fields

Dashboard cards may expose read-only market observation fields derived from the
same immutable timeline artifacts:

- `market_movement`: opening/latest or lock line movement, water drift, pattern,
  timing, checkpoints seen, and source.
- `market_divergence`: `fair_ah - market_ah` deltas in the home-line sign
  convention, with `calibration_status=UNVALIDATED` and
  `direction_allowed=false`.
- `bookmaker_hypothesis`: an explicitly unverified hypothesis with alternative
  explanations such as injuries, lineup information, public attention, market
  protection, or uncalibrated rules.

These fields are display-only. They must not change recommendation tier,
candidate/formal flags, `beats_market`, or S2 gate state. Until B4 calibration is
complete, UI copy must say the divergence is uncalibrated and only for
observation; it must not provide betting direction.
