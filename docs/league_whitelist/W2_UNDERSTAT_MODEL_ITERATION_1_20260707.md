# W2 Understat Model Iteration 1

Date: 2026-07-07

Status: `OFFLINE_MODEL_DEVELOPMENT_ONLY`

This report records a zero-cost offline model iteration using public Understat
true xG for the five major annual leagues in season override `2024`.

## Goal

Replace the hand-set `BASELINE_PRIOR` lambda weights with an offline fitted
lambda model, then apply a simple probability calibration layer. The goal is to
test whether fitted lambdas plus calibration can move W2 log-loss toward a
market-grade reference around `0.96` while improving ECE.

## Data And Safety

| field | value |
| --- | ---: |
| source | `understat_xg_local` |
| API-Football calls | 0 |
| Understat public cache requests | 5 initial page-data requests |
| fixtures loaded | 1755 |
| Understat xG fixtures matched | 1750 |
| eligible walk-forward sample | 1510 |
| train sample | 1057 |
| validation sample | 453 |
| canonical season changed | false |
| enabled=true changed | false |
| DB writes | 0 |
| deploys | 0 |

Understat cache files remain under `runtime/` and are not committed. No raw
payload, provider header, or key is committed.

## Method

The feature path reuses the #192 Understat true-xG harness. For every fixture,
rolling xG state is built strictly as-of the target kickoff:

- predict target fixture first
- exclude the target fixture's own xG from features
- update rolling xG state only after the prediction

The model iteration is also time bounded:

- coefficients are fitted only on the chronological training prefix
- temperature scaling is fitted only on that training prefix
- validation is the chronological suffix
- online lambda-fit gates remain closed
- production prediction code is unchanged

## Model

The offline model fits a small regularized Poisson lambda model on side-level
goal rows:

- intercept
- home field
- rolling xG for
- opponent rolling xG against
- Elo gap

The fitted 1X2 probabilities are then temperature-scaled. The fitted
temperature is `0.88`.

## Train Metrics

| model | sample | log_loss | Brier | RPS | ECE |
| --- | ---: | ---: | ---: | ---: | ---: |
| uniform | 1057 | 1.098612 | 0.666667 | 0.235520 | 0.090508 |
| Elo-only | 1057 | 1.048509 | 0.631532 | 0.220998 | 0.057038 |
| baseline prior | 1057 | 1.022910 | 0.612317 | 0.211932 | 0.088890 |
| fitted raw | 1057 | 0.994636 | 0.592180 | 0.202154 | 0.035867 |
| fitted + temperature | 1057 | 0.993135 | 0.590856 | 0.201238 | 0.017032 |

## Validation Metrics

| model | sample | log_loss | Brier | RPS | ECE |
| --- | ---: | ---: | ---: | ---: | ---: |
| uniform | 453 | 1.098612 | 0.666667 | 0.240250 | 0.086093 |
| Elo-only | 453 | 1.028208 | 0.617209 | 0.220493 | 0.080288 |
| baseline prior | 453 | 1.005268 | 0.600625 | 0.213034 | 0.114102 |
| fitted raw | 453 | 0.970488 | 0.577814 | 0.202277 | 0.048973 |
| fitted + temperature | 453 | 0.969900 | 0.577688 | 0.202153 | 0.041136 |

Validation delta for fitted + temperature versus baseline prior:

| metric | delta |
| --- | ---: |
| log_loss | -0.035368 |
| Brier | -0.022937 |
| RPS | -0.010881 |
| ECE | -0.072966 |

## Conclusion

```text
MODEL_ITERATION_PROMISING
```

The fitted lambda model plus temperature scaling beats uniform, Elo-only, and
the current baseline prior on the validation suffix. It moves validation
log-loss to `0.969900`, close to the market-grade reference around `0.96`, and
fixes the ECE problem versus the prior (`0.114102 -> 0.041136`).

This supports the model architecture direction. It is not a production
enablement decision: the result is offline model development only. The next
step should be reviewer inspection of the fitting discipline and then a larger
offline challenger plan before any online lambda-fit path is opened.

## Robustness Follow-Up

The follow-up robustness check is recorded in
`docs/league_whitelist/W2_UNDERSTAT_MODEL_ITERATION_1_ROBUSTNESS_20260707.md`.
It adds train/validation gap, 2023<->2024 cross-season validation, and
rolling-origin folds. The result is `ROBUST_IMPROVEMENT`: the exact `0.969900`
single-split validation score is optimistic, but the fitted lambda plus
temperature direction remains stable.

## Repro Command

```bash
uv run --python 3.12 python scripts/run_w2_free_tier_2024_backtest.py \
  --competition premier_league \
  --competition la_liga \
  --competition bundesliga \
  --competition serie_a \
  --competition ligue_1 \
  --xg-source=understat \
  --fit-understat-model \
  --out-dir runtime/w2_understat_model_iter1 \
  --output runtime/w2_understat_model_iter1/model_iteration_report.json \
  --json
```

## Safety

- api_football_provider_calls=0
- understat_public_requests_initial_cache=5
- provider_key_read=false
- db_reads=0
- db_writes=0
- enabled_true=false
- staging_deploy=false
- production_deploy=false
- scheduler_restart=false
- online_lambda_fit_enabled=false
- canonical_season_changed=false
- raw_payload_committed=false
- key_or_header_committed=false
