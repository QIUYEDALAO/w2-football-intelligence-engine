# SC21 Stage14 Factor Coverage Audit V2

## Evidence boundary

- Evidence as-of: `2026-08-13T19:09:28.493050Z`
- Provider calls by audit: `0`
- Business writes by audit: `0`
- Exact-13 persisted T+7 / Dashboard / Shadow scan sets: `36` / `36` / `36` (equal)
- Player valuation source rows observed: `31507`

## Current truth

- Four-field xG missing fixtures: **27 / 36**
- Stale markets at audit time: **70 / 72**
- Insufficient bookmaker-depth markets: **0 / 72**
- Current exact quote not ready: **72 / 72**
- Simulation not ready: **27 / 36**
- Baseline-prior simulations: **9 / 36**
- Bilateral Rating ready: **8 / 36**
- Bilateral TeamValueAsOf ready: **0 / 36**
- Lineup ready: **0 / 36**
- Shadow Candidate ACTIVE (immutable forward records): **6 / 36**

## Interpretation

The current market audit and an already-written forward record are separate facts. A quote that is stale now does not rewrite an earlier valid Shadow decision. AH and OU are audited independently at `fixture × market` grain. Radar evidence is never treated as an executable quote.

Calibration `BASELINE_PRIOR` permits Shadow analysis but does not prove incremental ability and cannot open Formal authority. Injuries and Statistics remain policy-disabled. No threshold, cadence, allowlist, model, or historical ledger record was changed by this audit.
