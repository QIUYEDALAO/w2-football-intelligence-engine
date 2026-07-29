# W2 Free-Tier 2024 Backtest and Calibration

Date: 2026-07-07

> PRELIMINARY: this is not a calibration acceptance report. It is based on
> proxy xG features and only 6/13 annual leagues. `calibration_status` remains
> `BLOCKED` because true xG is missing and 7 annual leagues have no 2024
> fixture raw in the local dataset.

This document records the first free-tier 2024 historical backtest and
calibration pass. The run uses existing local raw data first, then performs a
controlled provider collection only when local 2024 fixtures are missing.

## Scope

- Season override: `2024`
- Scope: 13 annual whitelist competitions
- World Cup: excluded from the 2024 annual sweep
- Model: `INDEPENDENT_POISSON`
- Prediction rule: build features before updating state with the fixture result
- Forbidden inputs: odds, market line, closing price, fixture result as feature
- Value-pick: not enabled
- League enablement: no `enabled=true` changes
- Deploy: none
- DB writes: 0

## Provider Collection

The controlled provider collection was configured below the daily hard cap:

```text
daily_hard_cap=25
max_statistics_calls=13
request_interval_seconds=10
```

The collector reused existing local raw files instead of re-fetching them. It
made one provider request for missing Serie A 2024 fixtures, then stopped
because provider quota headers reached the local warning threshold.

| field | value |
| --- | --- |
| provider_calls_this_run | 1 |
| stopped_reason | QUOTA_WARNING |
| raw output | runtime/w2_free_tier_2024/ |
| committed raw payloads | false |
| committed provider headers/key | false |

No xG/statistics requests were made after the quota warning stop.

## Data Coverage

The current local dataset covers 6/13 annual competitions and 2,135 settled
fixtures.

| competition | settled fixtures |
| --- | ---: |
| premier_league | 380 |
| la_liga | 380 |
| bundesliga | 308 |
| serie_a | 380 |
| ligue_1 | 307 |
| brasileirao_serie_a | 380 |
| argentina_primera | 0 |
| mls | 0 |
| chinese_super_league | 0 |
| allsvenskan | 0 |
| eliteserien | 0 |
| eredivisie | 0 |
| primeira_liga | 0 |

Missing fixture raw:

- argentina_primera
- mls
- chinese_super_league
- allsvenskan
- eliteserien
- eredivisie
- primeira_liga

Input gaps:

- xG/statistics: partial or missing
- squad_value: missing source

## Overall Metrics

The metrics below are post-hoc evaluation metrics. They do not enable value
picks and do not update online calibration.

| metric | value |
| --- | ---: |
| settled_sample | 2135 |
| Brier | 0.622464 |
| log_loss | 1.035683 |
| RPS | 0.217053 |
| ECE | 0.043355 |
| ECC | 0.043355 |

Uniform baseline:

| metric | value |
| --- | ---: |
| Brier | 0.666667 |
| log_loss | 1.098612 |
| RPS | 0.235545 |
| ECE | 0.095706 |

Interpretation:

- The model beats the uniform baseline (`log_loss=1.035683` vs `1.098612`,
  `Brier=0.622464` vs `0.666667`).
- The result is still materially below market-grade 1X2 performance, with
  market-grade log-loss expected near `~0.96` for this kind of comparison.
- `ECE=0.043355` indicates decent calibration shape for this preliminary
  sample, but the model is not sharp enough. In plain terms: reasonably
  calibrated, not yet sufficiently discriminative.

## Calibration Status

```text
status=BLOCKED
blockers=MISSING_TRUE_XG,MISSING_2024_FIXTURE_RAW
warnings=XG_STATISTICS_PARTIAL_OR_MISSING,SQUAD_VALUE_MISSING
online_calibration_changed=false
```

The settled sample is large enough for offline comparison, but calibration
cannot be accepted as full-scope while 7 annual competitions are missing and xG
/ squad-value inputs are incomplete. The current report must not be described
as "calibration passed."

## Outcome-Tracked Samples

The runtime report includes deterministic outcome-tracked sample rows with:

- fixture_id
- competition_id
- prediction_hash
- actual result
- actual score
- actual probability
- log_loss

Runtime report:

```text
runtime/w2_free_tier_2024/backtest_report.json
```

Report hash:

```text
0e8fe21d907e57c31c6fd16ed2e884e23b0b17d68fda67db5c8b4af3d2259820
```

## Next Safe Step

Wait for quota recovery before resuming controlled collection. The next run
should fetch only the 7 missing annual fixture datasets first. Statistics/xG
sampling should remain round-robin by competition and stop immediately on quota
warning or HTTP 429.

Do not enable any league until the full 13/13 annual competition dataset and
input coverage requirements are explicitly accepted.
