# W2 Premier League 2024 True-xG Delta Experiment

Date: 2026-07-07

This document records the controlled comparison between proxy xG features and
Understat public true rolling xG for Premier League 2024.

## Goal

Answer whether true rolling xG can move the W2 pre-match model from the proxy
feature floor toward market-grade performance.

The experiment compares:

- proxy path: existing rolling proxy features
- true-xG path: rolling team xG from Understat public league data cache

The target fixture's own xG is never used as a pre-match feature. It is loaded
only after prediction and is used only to update future rolling xG state.

## Scope

- Competition: `premier_league`
- Season override: `2024`
- Fixture source: existing local fixture raw
- True-xG source: `understat_xg_local`
- Understat requests: 1 public league data request, then local cache reuse
- API-Football calls: 0 for the Understat run
- Value-pick: not enabled
- League enablement: no `enabled=true` changes
- DB writes: 0
- Deploys: 0

## Data Collection Result

The earlier API-Football statistics attempt stopped after one statistics request
because the provider quota header reached the local warning threshold. This
follow-up run did not use API-Football. It fetched the public Understat league
data once, cached it locally, and then reused the cache.

| field | value |
| --- | ---: |
| API-Football provider_calls_this_run | 0 |
| Understat public requests | 1 |
| Understat fixture rows cached | 380 |
| statistics_fixtures_available | 380 |
| comparable delta sample | 330 |
| committed raw payloads | false |
| committed provider headers/key | false |

Runtime output, not committed:

```text
runtime/w2_pl_2024_understat_xg/
```

Understat usage note: the cache is sourced from the public Understat league data
page for research comparison. It is kept out of git and separated from
API-Football provider lineage.

## Proxy Baseline

The full proxy path still evaluates the full Premier League 2024 fixture set.

| metric | value |
| --- | ---: |
| settled_sample | 380 |
| Brier | 0.620254 |
| log_loss | 1.032025 |
| RPS | 0.217661 |
| ECE | 0.060351 |
| ECC | 0.060351 |

Uniform baseline:

| metric | value |
| --- | ---: |
| Brier | 0.666667 |
| log_loss | 1.098612 |
| RPS | 0.236988 |
| ECE | 0.074561 |

## Proxy vs Understat True-xG Delta

The delta is computed on the same 330 fixtures where both teams had at least
five prior true-xG matches. Negative values are improvements for Brier,
log-loss, RPS, and ECE.

| metric | proxy | Understat true-xG | delta |
| --- | ---: | ---: | ---: |
| Brier | 0.615851 | 0.608303 | -0.007548 |
| log_loss | 1.025853 | 1.016431 | -0.009422 |
| RPS | 0.217718 | 0.213853 | -0.003865 |
| ECE | 0.074443 | 0.101217 | +0.026774 |

The target fixture's own Understat xG is excluded from pre-match features. Each
fixture is predicted first, and only then does that fixture update the rolling
xG state for future fixtures.

## Current Conclusion

```text
MIXED_OR_SMALL_TRUE_XG_GAIN
```

Understat true rolling xG improves log-loss by about 0.0094 on the comparable
sample, so the feature has signal. However, it does not move the model close to
market-grade log-loss around 0.96, and ECE worsens. The current architecture is
not yet proven strongly enough to justify paid full-scale provider validation by
itself. Treat this as a small positive signal: improve the model and feature
shape before using paid data for broad validation.

## Repro Command

```bash
uv run --python 3.12 python scripts/run_w2_free_tier_2024_backtest.py \
  --competition premier_league \
  --xg-source=understat \
  --out-dir runtime/w2_pl_2024_understat_xg \
  --output runtime/w2_pl_2024_understat_xg/understat_true_xg_report.json \
  --json
```

The command is reproducible and cache-aware. If the Understat cache already
exists, it performs zero network requests.

## Safety

- api_football_provider_calls_this_run=0
- understat_public_requests_this_run=1
- db_reads=0
- db_writes=0
- enabled_true=false
- staging_deploy=false
- production_deploy=false
- scheduler_restart=false
- checkpoint_write=false
- lock_capture_write=false
- settlement_write=false
- raw_payload_committed=false
- key_or_header_committed=false
