# ADR-0012: Live Forward Holdout Autorun

## Status

Accepted for Stage 7E in local/staging only.

## Context

Stage 7D introduced a disabled automation foundation for the forward holdout. Stage 7E enables a
controlled live loop for local or staging so W2 can lock WATCH/SKIP forward predictions, capture
same-time market snapshots, append match results, and update the Gate 4 audit without training or
recommendation output.

## Decision

Forward holdout autorun may run only when all runtime guards pass:

- environment is `local` or `staging`
- `W2_FORWARD_HOLDOUT_AUTORUN=true`
- `W2_FORWARD_HOLDOUT_NETWORK=true`
- `W2_DEEPSEEK_ENABLED=false`
- `W2_RECOMMENDATION_ENABLED=false`
- frozen challenger, feature allowlist, calibration, and promotion criteria hashes match

The daily hard budget is `6000`, the minimum reserve is `1500`, and each cycle is capped at `1000`
requests. Unknown remaining quota stops the run. HTTP 401, 403, or 429 opens the circuit breaker.
Request audits must not include provider keys or authentication headers.

Scheduler cadence for local/staging:

- discovery: every 6 hours
- T-24h eligibility and lock: every 60 minutes
- T-1h eligibility and lock: every 10 minutes
- settlement: every 30 minutes
- Gate audit: daily

Stage 7E uses a local runtime override under `runtime/stage7e/`; production configuration is not
modified.

## Consequences

The system can now perform controlled live forward holdout operations while keeping Gate 4 pending.
All outputs remain WATCH/SKIP only. Stage 9 stays blocked until the pre-registered forward holdout
criteria are satisfied in a later stage.
