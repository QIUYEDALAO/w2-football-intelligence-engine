# W2 Understat Model Iteration 1 Robustness Check

Date: 2026-07-07

Status: `ROBUST_IMPROVEMENT`

This report validates whether the Model Iteration 1 validation log-loss
(`0.969900`) is stable rather than a single split artifact. The check uses only
public Understat data and makes zero API-Football calls.

## Data And Safety

| field | value |
| --- | ---: |
| source | `understat_xg_local` |
| seasons | `2023`, `2024` |
| competitions | EPL, La Liga, Bundesliga, Serie A, Ligue 1 |
| fixtures loaded | 3504 |
| Understat xG fixtures available | 3504 |
| eligible walk-forward samples | 3195 |
| API-Football calls | 0 |
| Understat public cache requests for this run | 5 |
| DB writes | 0 |
| enabled=true changed | false |
| deploys | 0 |

Understat cache files remain under `runtime/` and are not committed. No raw
payload, provider header, or key is committed.

## Method Discipline

- Every split is chronological.
- Lambda coefficients are fitted only on the training prefix.
- Temperature scaling is fitted only on the training prefix.
- Validation fixtures are strictly after the fitting boundary.
- Rolling xG features are built as-of kickoff and exclude the target match's own
  xG.
- Online lambda-fit gates remain closed.

## Train Versus Validation Gap

The combined 2023+2024 split uses a chronological training prefix of `2236`
samples and validation suffix of `959` samples.

| model | split | sample | log_loss | Brier | RPS | ECE |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| uniform | train | 2236 | 1.098612 | 0.666667 | 0.234024 | 0.098241 |
| Elo-only | train | 2236 | 1.035881 | 0.622483 | 0.214478 | 0.058980 |
| baseline prior | train | 2236 | 1.018683 | 0.609097 | 0.208101 | 0.102040 |
| fitted raw | train | 2236 | 0.982175 | 0.584193 | 0.195706 | 0.028552 |
| fitted + temperature | train | 2236 | 0.981510 | 0.583632 | 0.195132 | 0.017158 |
| uniform | validation | 959 | 1.098612 | 0.666667 | 0.237110 | 0.074383 |
| Elo-only | validation | 959 | 1.026387 | 0.615669 | 0.215502 | 0.050727 |
| baseline prior | validation | 959 | 1.011660 | 0.604703 | 0.210627 | 0.086560 |
| fitted raw | validation | 959 | 0.986495 | 0.588441 | 0.202582 | 0.025543 |
| fitted + temperature | validation | 959 | 0.989987 | 0.590663 | 0.203378 | 0.039732 |

Gap, computed as validation minus train for fitted + temperature:

| metric | gap |
| --- | ---: |
| log_loss | 0.008477 |
| Brier | 0.007031 |
| RPS | 0.008246 |
| ECE | 0.022574 |

Interpretation: the train/validation gap is small; there is no evidence of a
large overfit pattern.

## Cross-Season Out-Of-Sample

| train season | validation season | validation sample | fitted log_loss | fitted Brier | fitted RPS | fitted ECE | delta log_loss vs prior | delta ECE vs prior | status |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 2023 | 2024 | 1685 | 0.989528 | 0.589933 | 0.201282 | 0.036243 | -0.024113 | -0.054554 | `MODEL_ITERATION_PROMISING` |
| 2024 | 2023 | 1510 | 0.987792 | 0.587310 | 0.196716 | 0.044235 | -0.032057 | -0.060520 | `MODEL_ITERATION_PROMISING` |

Both directions beat the baseline prior and the Elo-only reference. The
cross-season result is above the single 2024 suffix result (`0.969900`), but it
stays in the same sub-1.00 band and remains directionally stable.

## Rolling-Origin Walk-Forward

| fold | train sample | validation sample | temperature | fitted log_loss | fitted Brier | fitted RPS | fitted ECE | prior log_loss | Elo-only log_loss | delta log_loss vs prior | status |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 1437 | 479 | 0.90 | 0.976957 | 0.583138 | 0.192915 | 0.042095 | 1.017201 | 1.029684 | -0.040244 | `MODEL_ITERATION_PROMISING` |
| 2 | 1757 | 479 | 0.92 | 0.985057 | 0.585783 | 0.200874 | 0.035583 | 1.012744 | 1.024581 | -0.027687 | `MODEL_ITERATION_PROMISING` |
| 3 | 2076 | 479 | 0.92 | 0.996999 | 0.598206 | 0.200744 | 0.057302 | 1.018464 | 1.035167 | -0.021465 | `MODEL_ITERATION_PROMISING` |
| 4 | 2396 | 479 | 0.92 | 1.000485 | 0.595985 | 0.206249 | 0.051974 | 1.016593 | 1.032287 | -0.016108 | `MODEL_ITERATION_PROMISING` |

Summary:

| metric | value |
| --- | ---: |
| fold count | 4 |
| wins versus baseline prior | 4 |
| mean fitted log_loss | 0.989874 |
| stddev fitted log_loss | 0.009400 |
| mean delta log_loss versus prior | -0.026376 |

The rolling-origin checks win every fold versus baseline prior and Elo-only.
Fold 4 is weaker than the single-split result, but still beats both references.

## Conclusion

`0.969900` is not just a single-fold accident: the exact value is optimistic,
but the fitted lambda + temperature direction is robust across the train/val
gap, two cross-season validations, and four rolling-origin folds.

The honest operating conclusion is `ROBUST_IMPROVEMENT`: the model architecture
is validated enough for offline challenger design, but this is not production
enablement. Online lambda fitting, league enablement, and deployment remain
closed.

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
  --fit-understat-robustness \
  --robustness-season 2023 \
  --robustness-season 2024 \
  --out-dir runtime/w2_understat_model_iter1 \
  --output runtime/w2_understat_model_iter1/model_robustness_report.json \
  --json
```

## Safety

- api_football_provider_calls=0
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
