# W2 MI Round 3 — Owner Authorization

```text
OWNER_AUTHORIZATION_ID = W2_MI_R3_MARKET_RADAR_MODEL_LAB_20260808
OWNER_DECISION = APPROVED_CONTINUOUS_EXECUTION
PRODUCT = W2 Football Intelligence
PROGRAM = W2_FOOTBALL_MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
ROUND_1 = PASS
ROUND_2 = PASS_WITH_TERMINAL_PROVIDER_PLAN_RESTRICTION
FREE_PLAN_BRIDGE_CONTROLLED_RUNTIME = PASS
ROUND_3 = AUTHORIZED_IN_PROGRESS
TASK = W2_MI_R3_MARKET_RADAR_AND_MODEL_LAB
```

## Mission

Build and ship the intelligence layer that turns real persisted market observations into `Market Radar` facts and turns existing model output into a strictly diagnostic `Model Lab` comparison.

Round 3 is **not** a betting-recommendation round and is not authorization to reopen the failed Phase 0.5 edge hypothesis.

```text
MODEL_MARKET_DIVERGENCE != MARKET_OPPORTUNITY
BETTING_EDGE_CLAIM = FORBIDDEN
RecommendationDecisionV4 = DIAGNOSTIC_INPUT_NOT_PRODUCT_AUTHORITY
H_RESULT_ACCESS = PERMANENTLY_CLOSED
```

## Continuous execution authority

Codex is authorized to execute the complete Round 3 goal continuously:

```text
live-main audit
-> evidence eligibility contract
-> Market Radar backend/read model
-> Model Lab diagnostic backend/read model
-> public intelligence projection
-> Web/API integration
-> tests / CI / bounded remediation
-> merge
-> immutable staging deployment
-> real persisted-evidence acceptance
-> rollback / hygiene
-> Round 3 receipt
```

For failures inside this scope:

```text
FAIL_CLOSED = STOP_AT_FAILED_GATE -> DIAGNOSE -> MINIMAL_FIX -> RERUN -> CONTINUE
FAIL_CLOSED != ABANDON_ROUND_3
```

Do not stop after a PR, test failure, CI failure, merge, deployment, or first runtime validation merely to ask the owner again.

A new owner decision is required only to cross a permanent stop line listed below.

## Data authority

Use only real evidence with complete lineage as Round 3 market truth:

```text
Provider payload
-> RawPayloadStore
-> endpoint capture
-> fixture identity
-> normalized market observation
```

Eligible observations must be non-synthetic, mapped to the exact existing 13 active-whitelist competitions, have valid fixture/bookmaker/market identity, and retain capture/raw lineage.

The deployed Free bridge remains `SHADOW_ONLY` and may continue normal accepted collection under its existing 100/day Provider limit, W2 80/day ceiling and 20-call reserve. Round 3 development/CI does not authorize manual Provider probing or a new collection schedule.

## League boundary

```text
ACTIVE_WHITELIST = EXACT_EXISTING_13
AUDIT_ONLY_RUNTIME_REACHABILITY = 0
```

The four Round-2 audit-only candidates remain outside runtime, Scheduler, future refresh, DayView and Round-3 public cards.

## Market Radar semantics

Market Radar is factual market observation, not opportunity scoring.

Required factual outputs include, where evidence exists:

```text
current canonical line
current decimal prices
quote/capture timestamp
quote freshness
bookmaker count/depth
per-bookmaker and consensus de-vig probabilities
overround distribution summary
previous comparable snapshot
line delta
same-line price/probability delta
snapshot count
movement classification
```

Movement may be reported from observable changes. Do not invent a statistical anomaly threshold merely because `MARKET_ANOMALY` exists in the public vocabulary.

If there is insufficient eligible temporal evidence, report `INSUFFICIENT` and do not fabricate movement.

`MARKET_ANOMALY` may only be emitted from an explicit validated anomaly contract. If Round 3 does not have enough evidence to calibrate a statistical anomaly rule, keep statistical anomaly calibration `NOT_CALIBRATED`.

Permanent guards:

```text
HIGH_OVERROUND != HIGH_VALUE
HIGH_OVERROUND != HIGH_INFORMATION
MOVEMENT != OPPORTUNITY
ANOMALY != OPPORTUNITY
```

## Model Lab semantics

Model Lab is diagnostic-only.

It must compare the model to the **same canonical market/line** and a real multi-bookmaker market consensus, not to an arbitrary or mismatched quote.

Minimum bookmaker depth for a public market-range diagnostic remains 3.

Required outputs where ready:

```text
model status/version/calibration status
market/line identity
bookmaker count
bookmaker de-vig probability distribution
market median probability
market observed min/max probability
model effective settlement probability
model-minus-market-median delta
distance outside observed market range
diagnostic comparison status
```

A conservative `MODEL_MARKET_DISAGREEMENT` is supportable only when:

```text
model evidence = READY
market identity = COMPLETE
freshness = COMPLETE
bookmaker depth >= 3
all compared probabilities refer to the same market/line
model effective probability lies outside the observed bookmaker probability range
```

Otherwise use a truthful non-disagreement/insufficient status.

Round 3 public authority must not consume or expose as product authority:

```text
EV
expected_value
cashflow_price_edge
analysis_direction_allowed
formal_eligible
lock_eligible
MODEL_MARKET_EDGE_READY
MODEL_MARKET_EDGE_INSUFFICIENT
MIN_MARKET_ANCHOR_DIVERGENCE as a product alert threshold
```

Legacy V4/edge code may remain for compatibility if still referenced, but Round 3 must isolate it from Market Radar / Model Lab product authority.

## Public product contract

Preserve the seven public intelligence states and precedence:

```text
COLLECTION_INCIDENT
DATA_INCOMPLETE
MODEL_DIAGNOSTIC_WARNING
MARKET_ANOMALY
MODEL_MARKET_DISAGREEMENT
MARKET_MOVEMENT
MARKET_STABLE
```

Precedence remains:

```text
COLLECTION_INCIDENT > DATA_INCOMPLETE > MODEL_DIAGNOSTIC_WARNING > MARKET_ANOMALY > MODEL_MARKET_DISAGREEMENT > MARKET_MOVEMENT > MARKET_STABLE
```

Risk dimensions remain independent:

```text
EVENT_RISK
DATA_RISK
MODEL_RISK
COLLECTION_RISK
```

Public surfaces remain:

```text
Market Overview
Match Intelligence
Data & Operations Summary
```

## Provider / quota boundary

```text
API_FOOTBALL_PLAN = FREE
PROVIDER_DAILY_LIMIT = 100
W2_DAILY_CALL_CEILING = 80
MIN_PROVIDER_DAILY_REMAINING = 20
AUTOMATIC_RETRY = false
API_FOOTBALL_PRO_RENEWAL = NOT_AUTHORIZED_NOW
NEW_PROVIDER_PURCHASE = NOT_AUTHORIZED
NEW_PROVIDER_CUTOVER = NOT_AUTHORIZED
```

Round 3 must primarily consume persisted evidence; no manual Provider batch is required for acceptance.

## Deployment authority

After all required source/PR/release gates pass, Round 3 may be deployed using the repository's existing immutable `W2_STAGING` release path.

Deployment does not authorize Candidate/Formal/Lock/Production or real-money behavior.

## Repository hygiene

`REPOSITORY_HYGIENE_POLICY.md` is mandatory before Round 3 PASS.

Delete provably dead/superseded task assets; retain reusable market-intelligence contracts, runtime code, tests and required evidence.

## Permanent stop lines

Round 3 does **not** authorize:

```text
API-Football Pro renewal
new Provider purchase/cutover
active-whitelist change
promotion of the four audit-only leagues
new recommendation tier
Candidate
Formal
Lock
Production
Kelly/portfolio/parlay
betting-edge/value/opportunity claims
real-money execution
reopening Phase 0.5/H
```

## Completion

Round 3 may close only when `ROUND_3_ACCEPTANCE_CRITERIA.md` passes and `ROUND_3_FINAL_RECEIPT.md` records exact code, CI, deployment, runtime evidence, stop-line proof and repository hygiene.
