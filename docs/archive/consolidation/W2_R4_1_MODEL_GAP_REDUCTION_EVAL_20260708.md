# W2 R4.1 Model Gap Reduction Eval

Status: eval-only, offline, zero provider calls. This report does not change
the live decision path, does not enable any league, and does not deploy.

## Scope

R4.1 evaluates the reviewer-requested model upgrades against the same market
baseline harness:

- Dixon-Coles low-score `rho` via `tau_correction`.
- Time-decay sample weights with a 365-day half-life.
- League-specific home-field coefficients.
- Windowed, opponent-strength-adjusted xG features replacing season cumulative
  sum/count features.

Acceptance is league-level gap reduction only. Pooled log-loss improvement is
not sufficient.

## Result Summary

Market gap is `model log_loss - market_devig log_loss` on the same joined
fixtures. Lower is better; a negative `Δgap` means R4.1 reduced the market gap.

| league | n | old gap | R4.1 gap | Δgap | gate |
|---|---:|---:|---:|---:|---|
| bundesliga | 295 | +0.0470 | +0.0430 | -0.0040 | gap decreased, still above 0.04 |
| chinese_super_league | 204 | +0.0524 | +0.0354 | -0.0170 | PASS, crosses 0.04 radar gate |
| brasileirao_serie_a | 360 | +0.0538 | +0.0550 | +0.0012 | FAIL, do not adopt R4.1 for this league |
| allsvenskan | 198 | +0.0551 | +0.0188 | -0.0363 | PASS, crosses 0.04 radar gate |

Non-target league movement is tracked for regression awareness:

| league | old gap | R4.1 gap | decision |
|---|---:|---:|---|
| premier_league | +0.0294 | +0.0270 | improved |
| la_liga | +0.0277 | +0.0258 | improved |
| serie_a | +0.0262 | +0.0113 | improved |
| ligue_1 | +0.0125 | +0.0332 | worsened but still below 0.04; keep prior model for best-gap table |
| mls | +0.0268 | +0.0146 | improved |
| eliteserien | +0.0164 | +0.0067 | improved |
| argentina_primera | -0.0115 | -0.0059 | still observation-only due known subset bias |

## Interpretation

R4.1 works where the original model showed the clearest structural weakness in
time/local-league dynamics: Chinese Super League and Allsvenskan now cross the
`gap <= 0.04` divergence-radar threshold. Bundesliga improves but remains just
outside the threshold, so German league model opinions must stay L2-only until a
future iteration reduces the gap further. Brasileirao worsens, so R4.1 must not
be adopted there.

The live product remains market-anchored. R4.1 can only improve the
model-divergence radar and MODEL_FALLBACK quality; it does not reopen the
EV/RECOMMEND leg.

## Artifacts

Runtime artifacts are intentionally uncommitted:

- `runtime/market_baseline_eval/model_phase_report.json`
- `runtime/market_baseline_eval/market_phase_report.json`
- `runtime/market_baseline_eval/W2_MARKET_BASELINE_SUMMARY.md`

Command:

```bash
uv run --python 3.12 python scripts/run_w2_market_baseline_eval.py --phase all
```

Safety:

- provider_calls=0
- db_reads=0
- db_writes=0
- staging_deploy=false
- production_deploy=false
- enabled_true=false
- raw/key/header not committed
