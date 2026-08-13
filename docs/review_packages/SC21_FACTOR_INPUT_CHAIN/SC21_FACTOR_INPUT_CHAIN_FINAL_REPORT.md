# SC21 Factor Input Chain Final Report

- Evidence as-of: `2026-08-13T20:16:58.717297Z`
- Exact-13 T+7 fixtures: `36`
- Provider calls by SC21 audit/materialization: `0`
- Business writes before guarded materialization: `0`
- Candidate mode: `SHADOW_ONLY`
- Formal / Lock / Production / Round 4: `OFF / OFF / OFF / NOT_STARTED`

## Coverage truth

- Four-field xG READY: `9/36`
- Simulation READY: `9/36`
- Rating bilateral READY: `8/36`
- TeamValueAsOf bilateral READY: `0/36`
- Lineup READY: `0/36`
- Lineup causes: `{'NOT_YET_DUE': 36}`
- Market stale: `72/72`
- Bookmaker depth insufficient: `0/72`
- Current exact quote not ready: `72/72`
- BASELINE_PRIOR: `9` fixtures
- Immutable Shadow candidates: `6`
- Current fully-ready market chains: `0`

## Materialization findings

- Rating snapshots: `16`; new candidates: `0`.
- Rating source is canonical match history and excludes rolling xG proxy; there is no automatic result-to-Elo refresh consumer.
- Player valuations: `31507`; registered rosters: `0`; TeamValue artifacts: `0`.
- TeamValue remains fail-closed pending reviewed as-of roster evidence.
- Saved-raw xG dry-run found no new true-xG rows for current T+7; Statistics remains policy-disabled pending Owner decision.

## Authority and safety

AH and OU are audited independently at fixture × market scope. Radar medians are not executable quotes. Current quote age does not rewrite historical forward records. No threshold, cadence, whitelist, model, Decision V4, Candidate, Formal, Lock or Production policy was relaxed.
