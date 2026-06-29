# W2 Formal Recommendation P0 Design

## New Definition

Formal recommendation means the strategy produces a self-consistent pre-match output from real data. It does not require proof that W2 beats the market, and historical hit rate is a post-match reporting metric rather than an opening gate.

`beats_market` remains a post-hoc field when present, but it is not a FORMAL gate. B3 walk-forward and hit-rate summaries are for later performance review only. A recommendation may become FORMAL when the data is real, the simulation is ready, market lines are available, and the recommendation direction is consistent with the simulation or explicitly explained as reverse-factor price value.

## Existing Problem

The old handicap mapping used `fair_handicap_from_supremacy`, effectively converting a small normalized team-score spread through `spread / 0.16 * 0.25`. Because the team score is bounded and compressed, strong mismatches can collapse to small handicaps such as `-0.25` or `-0.5`. That creates cards where independent factors favor one team while the displayed lean or value appears to favor the other team without explanation.

That path can remain for legacy shadow diagnostics, but it must not drive FORMAL recommendations.

## Architecture

### SimulationInputs

The formal path uses a typed input object with only real pre-match sources:

- fixture and team ids
- rolling xG for and against
- internal ratings or Elo-style ratings
- squad value
- team fixture history and H2H readiness signals
- optional real lineup adjustment when lineups are READY
- input readiness flags

It does not consume market AH, market OU, odds movement, bookmaker hypothesis, current odds, final result, or settlement output when calculating lambdas or fair lines.

### Lambda Calibration

`strategy/calibration.py` maps xG, rating gap, squad value ratio, and home advantage into realistic goal rates. The first implementation uses locked baseline prior parameters and reports `calibration_status=BASELINE_PRIOR`, not historical validation. xG is the main input; ratings and squad value adjust the strength delta and total-goal level.

### Monte Carlo Simulation

`strategy/simulate.py` runs a deterministic Monte Carlo simulation using a seed derived from `fixture_id` and model version. It emits:

- `lambda_home` and `lambda_away`
- score matrix summary and top scorelines
- fair AH from the simulated goal-difference distribution
- fair OU from the simulated total-goals distribution
- AH and OU probabilities
- readiness and status

The same engine generates AH, OU, and scorelines, so the card cannot silently mix unrelated conclusions.

### Formal Rule

`strategy/formal_recommendation.py` consumes simulation output, market line and odds, devig probabilities when available, data readiness, and factor leader. It does not use bookmaker hypothesis as an input. The hypothesis can be shown as context only.

FORMAL requires:

- real pre-match data
- simulation status READY
- market line and odds
- sufficient value edge
- no leakage or live/finished blocker
- self-consistent direction, or an explicit reverse-factor explanation containing price value

WATCH is emitted for missing simulation inputs, missing market, small edge, unexplained contradiction, or critical readiness blockers.

### Frontend Card

FORMAL cards show:

- "正式推荐"
- market, selection, line, and odds
- simulation fair line and market line
- a concise value explanation
- key independent-factor context
- bookmaker hypothesis only as reference context

WATCH and insufficient-data cards do not show FORMAL. FORMAL cards do not show fake hit rates, guaranteed language, or old "非正式推荐" main labels.

## Explicit Non-Inputs

The P0 path does not use:

- market OU to fit lambda
- `beats_market` as a gate
- fake hit rate
- bookmaker hypothesis as a recommendation input
- final results or settlement outputs
- current odds to backfill historical as-of lines

## Acceptance Examples

### Strong Home

When home xG, rating, and squad value are materially stronger, the simulation should produce higher `lambda_home`, a home-favoring fair AH with meaningful depth, and a FORMAL home-side recommendation only if the market price gives enough value.

### Strong Away

When away inputs dominate, the simulation should produce higher `lambda_away`, a positive home handicap / away-favoring line, and a FORMAL away-side recommendation only when the market line and price are self-consistent with value.

### Balanced

Balanced inputs should produce lambdas and fair AH near level. If the market does not create enough value, the output remains WATCH.

### Insufficient Data

Missing core xG and insufficient alternative signals produce `INSUFFICIENT_INPUTS`. The card remains WATCH and does not hard emit FORMAL.

### Reverse-Factor Price Value

If factor direction and value direction differ, FORMAL is allowed only when the reason explicitly says it is a "盘口价值" recommendation and explains why price/value differs from raw factor leadership.
