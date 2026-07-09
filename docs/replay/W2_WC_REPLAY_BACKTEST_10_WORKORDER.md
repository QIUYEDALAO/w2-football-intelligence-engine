# W2-WC-REPLAY-BACKTEST-10 Workorder

## Purpose

Use up to ten already-finished World Cup 2026 fixtures for an isolated replay /
backtest rehearsal. This is not statistical validation and must not be described
as model accuracy proof. The goal is to rehearse the full operational chain on
real completed matches:

- build prematch inputs as of kickoff minus 30 minutes
- freeze DecisionCard-compatible prematch cards
- record shadow direction evidence when retrospective odds are available
- only then read FT / AET / PEN outcomes
- produce a per-card answer sheet

## Urgency

API-Football postmatch odds retention is limited. Matches around 2026-07-02 are
near the edge of the practical retention window, so public `fixtures` and `odds`
capture must happen before those odds disappear.

## Provider Scope

Approved scope: `APPROVED_PROVIDER_CALLS: WC_REPLAY_PUBLIC_CAPTURE_CAP_40`.

Allowed public endpoints:

- `fixtures`
- `odds`

Forbidden endpoints:

- `lineups`
- `statistics`
- `injuries`
- `h2h`
- `history`
- `xg_history_backfill`
- `market_timeline_refresh`

The runner must report `provider_calls_actual <= 40` and endpoint counts.

## Isolation

Outputs are written outside tracked repository artifacts:

- preferred: `/opt/w2/shared/runtime/replay_backtest/wc_10/<run_id>/`
- fallback: `/tmp/w2_wc_replay_backtest_10_<run_id>/<run_id>/`

Raw provider payloads are allowed only inside the isolated output directory and
must never be committed to git.

The runner captures before/after integrity for:

- `runtime/forward_outcome_ledger`
- `runtime/forward_ledger_performance`

Hard acceptance:

- `forward_ledger_unchanged=true`
- `forward_ledger_performance_unchanged=true`

If either value is false, the run must stop with
`FORWARD_LEDGER_POLLUTION_DETECTED`.

## Prematch Leakage Guard

For every selected fixture:

- `as_of = kickoff - 30 minutes`
- prematch input may include fixture id, teams, kickoff, retrospective odds
  archive summary, and model artifact provenance
- prematch input must not include final score, settlement, FT/AET/PEN result,
  postmatch outcome, closing line after kickoff, or result status

Retrospective odds archive cannot prove the historical time slice. Such runs are
therefore marked:

- `replay_quality=LIMITED`
- `odds_timeline_warning=true`
- `odds_source=RETROSPECTIVE_PROVIDER_ARCHIVE`

## CLV

All CLV fields are `N/A`.

Reason: replay cannot recover a forward odds timeline. CLV must come from
forward capture only.

## Report Language

The validation report must state:

- this is rehearsal, not statistical validation
- ten matches cannot prove model accuracy
- value comes from per-card answer checking and exposing data, market, or model
  behavior issues

## Hard Red Lines

- no production deploy
- no staging deploy
- no scheduler restart
- no DB writes
- no lock writes
- no settlement writes
- no `direction_allowed` change
- no EV / RECOMMEND leg change
- no Stage 16
- no `forward_outcome_ledger` write
- no `forward_ledger_performance` write
- no raw provider payload committed
- no reports committed from runtime
