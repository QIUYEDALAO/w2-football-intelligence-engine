# W2 R4.1b Divergence Champion Selection

Date: 2026-07-08

Status: eval-only, staging/flag-compatible, no provider calls.

## Scope

R4.1b only consolidates the model side used by the divergence radar. It does not change the displayed probability source, which remains de-vig market probability when odds exist. It does not re-open the EV / RECOMMEND leg.

## Champion Selection

| Competition | Champion model | Rationale |
|---|---|---|
| bundesliga | R4_1_CALIBRATED | R4.1 reduced model-minus-market gap from `+0.0470` to `+0.0430`; still below the admission line, but reviewer asked to wire the improved variant for divergence signal only. |
| chinese_super_league | R4_1_CALIBRATED | R4.1 reduced gap from `+0.0524` to `+0.0354`, crossing the <= `+0.0400` divergence-radar threshold. |
| allsvenskan | R4_1_CALIBRATED | R4.1 reduced gap from `+0.0551` to `+0.0188`, crossing the <= `+0.0400` divergence-radar threshold. |
| brasileirao_serie_a | FITTED_CALIBRATED | R4.1 worsened gap from `+0.0538` to `+0.0550`; keep original fitted model. |
| other leagues | FITTED_CALIBRATED | R4.1b is a conservative wiring pass. Non-targeted or worsened leagues keep the original fitted model until separately admitted. |

## Validation Snapshot

Command:

```bash
uv run --python 3.12 python scripts/run_w2_market_baseline_eval.py --phase all
```

Result highlights:

| Competition | Champion | Champion gap | Original gap | R4.1 gap |
|---|---|---:|---:|---:|
| bundesliga | R4_1_CALIBRATED | `+0.0430` | `+0.0470` | `+0.0430` |
| chinese_super_league | R4_1_CALIBRATED | `+0.0354` | `+0.0524` | `+0.0354` |
| allsvenskan | R4_1_CALIBRATED | `+0.0188` | `+0.0551` | `+0.0188` |
| brasileirao_serie_a | FITTED_CALIBRATED | `+0.0538` | `+0.0538` | `+0.0550` |

## Safety

- provider_calls=0
- db_reads=0
- db_writes=0
- enabled_true=false
- staging_deploy=false
- production_deploy=false
- market probability display remains MARKET_DEVIG
- EV / RECOMMEND leg remains default-off and governed by the R3.0 preregistered forward gate
