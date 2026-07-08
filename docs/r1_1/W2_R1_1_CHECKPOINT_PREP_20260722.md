# W2 R1.1 Checkpoint Prep - 2026-07-22

## Purpose

R1.1 is a calendar-time checkpoint for the staging forward evidence stream. It
does not release `direction_allowed`, does not enable EV / RECOMMEND, and does
not change production behavior.

Target checkpoint date: approximately `2026-07-22`.

## Required Fields

The dry-run helper must report:

- `checkpoint_date`
- `environment`
- `double_snapshot_card_count`
- `shadow_nonempty_rate`
- `clv_shadow_sample_count`
- `clv_shadow_median`
- `entry_window_met_rate`
- `excluded_no_prematch_closing_count`
- `unsettled_missing_fulltime_count`
- `outcome_count_ft`
- `outcome_count_aet`
- `outcome_count_pen`
- `provider_usage_curve_summary`
- `model_family_distribution`
- `r4_1_artifact_provenance_distribution`
- `direction_allowed_candidate_leagues`
- `readiness_status`
- `blockers`
- `provider_calls=0`
- `db_writes=0`

## Sample Thresholds

The first hard threshold is at least `100` double-snapshot cards. The same
threshold is used for `clv_shadow` samples before any league can be considered
ready for independent review.

No settlement samples must always be shown as `ACCUMULATING`, never as a numeric
conclusion. Sample counts below threshold must be shown as `NOT_ENOUGH_SAMPLE`
with explicit blockers.

## Candidate Order

Candidate review order remains:

1. `eliteserien`
2. `allsvenskan`
3. `chinese_super_league`

`brasileirao_serie_a` remains disabled by the pre-registered guard because R4.1
worsened the Brazil gap.

## Release Rule

`direction_allowed` still requires independent reviewer approval. This
checkpoint only prepares evidence for that review.

## Explicitly Not Included

- No provider calls.
- No DB writes.
- No staging deploy.
- No production deploy.
- No scheduler restart.
- No lock / settlement writes.
- No runtime artifact committed.
- No Stage 16.
