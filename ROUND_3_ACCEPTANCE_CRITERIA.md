# W2 MI Round 3 — Acceptance Criteria

Round 3 passes only when every hard gate below passes. A blocked/insufficient market or model row is a valid truthful output; a fabricated ready state is a failure.

## A. Source and authority

- latest `origin/main` and `origin/context/current` fetched and exact SHAs recorded;
- Round-3 owner/execution authorities read before work;
- code/runtime/DB/real lineage/tests/CI evidence used as truth;
- PR descriptions/comments not treated as proof.

## B. Product stop lines

Must remain true throughout:

```text
ACTIVE_WHITELIST = EXACT_EXISTING_13
AUDIT_ONLY_RUNTIME_REACHABILITY = 0
API_FOOTBALL_PLAN = FREE
API_FOOTBALL_PRO_RENEWAL = NOT_AUTHORIZED_NOW
FREE_BRIDGE_MODE = SHADOW_ONLY
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
H_RESULT_ACCESS = PERMANENTLY_CLOSED
REAL_MONEY = NOT_AUTHORIZED
```

No Round-3 change may create a betting/value/opportunity claim.

## C. Evidence eligibility

PASS requires an explicit eligibility contract and tests covering at least:

- synthetic evidence rejected;
- missing raw lineage rejected;
- missing capture lineage rejected;
- unresolved fixture/competition identity rejected;
- out-of-whitelist competition rejected;
- unsupported market rejected;
- invalid line/price rejected;
- identity-conflicting quote rejected;
- duplicate conflicting observation rejected;
- valid real AH/OU evidence accepted.

Rejected rows must have reason codes.

## D. Same-line identity

For every Radar/Model Lab comparison:

```text
SAME_FIXTURE = true
SAME_MARKET = true
SAME_CANONICAL_LINE = true
VALID_SELECTION_PAIR = true
```

AH home/away sign symmetry and OU over/under same-line identity must be tested.

Cross-line model-market comparison = FAIL.

## E. Market Radar current facts

For ready evidence the contract must expose truthful:

```text
current line
prices
bookmaker depth
freshness
capture/quote time
snapshot/observation counts
overround/de-vig facts
lineage identity
```

Missing facts must be null/not-ready with reason codes, not numeric zero placeholders.

## F. De-vig and overround

- de-vig reuses authoritative market method;
- complete two-sided bookmaker quote required;
- bookmaker-level overround computed correctly;
- consensus distribution is deterministic;
- percentile summaries only when sample count permits;
- `HIGH_OVERROUND != HIGH_VALUE` and `HIGH_OVERROUND != HIGH_INFORMATION` preserved.

## G. Market Radar movement

Required statuses are implemented and tested:

```text
INSUFFICIENT
STABLE
PRICE_MOVEMENT
LINE_MOVEMENT
LINE_AND_PRICE_MOVEMENT
```

Hard cases:

- fewer than 2 comparable eligible snapshots -> `INSUFFICIENT`;
- no factual line/price change -> `STABLE`;
- same-line price/probability change -> `PRICE_MOVEMENT`;
- line change -> `LINE_MOVEMENT` or `LINE_AND_PRICE_MOVEMENT`;
- timestamps and factual deltas preserved;
- movement does not imply opportunity/value.

## H. Statistical anomaly calibration

Round 3 may not invent a hard anomaly threshold.

Receipt must explicitly record:

```text
STATISTICAL_ANOMALY_CALIBRATION = CALIBRATED | NOT_CALIBRATED
```

If `CALIBRATED`, evidence/method/sample basis must be documented and tested.

If evidence is insufficient, required result is `NOT_CALIBRATED`; statistical magnitude alone must not emit `MARKET_ANOMALY`.

Truthful `NOT_CALIBRATED` does not fail Round 3.

## I. Model Lab market consensus

A public consensus-range diagnostic requires:

```text
bookmaker_count >= 3
complete same-line two-sided quotes
fresh market evidence
valid de-vig probabilities
```

Market median/min/max must be computed from bookmaker-level de-vig probabilities, not raw odds averages.

## J. Model Lab model readiness

Model comparison requires existing authoritative model/simulation evidence with model/calibration identity.

Missing/invalid model uncertainty or calibration must fail closed to `MODEL_NOT_READY` / diagnostic warning, not a disagreement claim.

## K. Model Lab statuses

Implement/test:

```text
MODEL_NOT_READY
MARKET_NOT_READY
INSUFFICIENT_BOOKMAKER_DEPTH
COMPARABLE_WITHIN_MARKET_RANGE
MODEL_OUTSIDE_MARKET_RANGE
```

`MODEL_MARKET_DISAGREEMENT` may be emitted only from `MODEL_OUTSIDE_MARKET_RANGE` after all readiness, depth, same-line and freshness gates pass.

Model inside observed bookmaker range must not be labeled disagreement.

## L. Forbidden edge semantics

Round-3 public API/read model/Web product authority must not expose or depend on:

```text
expected_value
EV
ev_eligible
formal_eligible
lock_eligible
cashflow_price_edge
analysis_direction_allowed
MODEL_MARKET_EDGE_READY
MODEL_MARKET_EDGE_INSUFFICIENT
MIN_MARKET_ANCHOR_DIVERGENCE as an alert authority
```

Add code/contract tests proving this boundary.

Legacy compatibility code may remain only if still referenced outside Round-3 authority.

## M. Seven-state precedence

Existing precedence must pass deterministic tests:

```text
COLLECTION_INCIDENT > DATA_INCOMPLETE > MODEL_DIAGNOSTIC_WARNING > MARKET_ANOMALY > MODEL_MARKET_DISAGREEMENT > MARKET_MOVEMENT > MARKET_STABLE
```

Examples must prove a lower-priority market state cannot mask collection/data/model warnings.

## N. Risk dimensions

Four dimensions remain independently populated:

```text
EVENT_RISK
DATA_RISK
MODEL_RISK
COLLECTION_RISK
```

No single scalar risk/opportunity score is introduced.

## O. API/read-model safety

- public/dashboard read requests trigger 0 Provider calls;
- read path fails closed on missing evidence;
- deterministic ordering;
- no duplicate API tree solely for Round 3;
- no obvious N+1 per fixture/bookmaker/snapshot query loop;
- query-count/performance evidence recorded.

## P. Web product acceptance

Existing public surfaces remain:

```text
Market Overview
Match Intelligence
Data & Operations Summary
```

Match Intelligence renders `Market Radar` and `Model Lab` when supported.

Insufficient evidence renders explicit not-ready/insufficient language.

No forbidden recommendation/value language appears.

Required Web typecheck/build and relevant Playwright tests PASS.

## Q. Free bridge invariants

Round 3 must not regress the accepted bridge:

```text
PROVIDER_DAILY_LIMIT = 100
W2_DAILY_CALL_CEILING = 80
MIN_PROVIDER_DAILY_REMAINING = 20
AUTOMATIC_RETRY = false
IDS_BATCHING = false
NEW_INDEPENDENT_SCHEDULER_DAEMON = 0
```

No manual Provider traffic is required for Round-3 development/CI.

## R. Runtime real-evidence acceptance

After immutable staging deployment:

- Market Radar must process real persisted eligible observations;
- Model Lab must process real persisted same-line evidence when model+depth permits;
- real insufficient cases remain insufficient;
- dashboard/API views add 0 Provider calls;
- recommendation rows created by Round 3 = 0;
- recommendation-lock rows created by Round 3 = 0.

Round 3 does not fail merely because current real evidence has no movement or no model-ready comparison; it fails if it fabricates one.

## S. PR / CI / release

All final code heads require, as applicable:

- focused Python tests PASS;
- full repository Python tests PASS;
- Ruff PASS;
- Mypy PASS;
- Web typecheck/build PASS;
- relevant Playwright PASS;
- secret scan PASS;
- protected-baseline/release gates PASS;
- PR Fast PASS;
- required Release Candidate PASS;
- Provider calls during CI = 0.

Maximum 2 Round-3 PRs.

## T. Immutable deployment

- deploy only accepted final main;
- immutable source/image identity recorded;
- required service health PASS;
- no Candidate/Formal/Lock/Production activation;
- Free bridge remains SHADOW_ONLY.

## U. Rollback

Round-3 public integration must have a verified non-destructive rollback.

Rollback must preserve:

- raw/capture/market evidence;
- exact active 13 whitelist;
- Free bridge accepted operation unless separately disabled for rollback test;
- no recommendation/execution gates opened.

## V. Repository hygiene

Before PASS:

```text
REPOSITORY_HYGIENE = PASS
UNRESOLVED_HYGIENE_ITEMS = 0
```

Provably dead temporary/duplicate assets removed; reusable canonical contracts/tests/evidence retained.

## W. Final receipt

`ROUND_3_FINAL_RECEIPT.md` must contain exact:

```text
base/final main SHAs
PR final heads/merge SHAs
CI/RC/promotion run IDs
immutable deployment IDs/digests
eligible/rejected evidence counts
Radar status counts
anomaly calibration status
Model Lab status/disagreement counts
public forbidden-edge-field proof
query/performance proof
Provider-call proof
Free bridge invariants
whitelist/audit-only proof
Candidate/Formal/Lock/Production proof
rollback proof
hygiene proof
```

## Final PASS state

Only when A-W pass:

```text
ROUND_3 = PASS_MARKET_RADAR_MODEL_LAB
ACTIVE_WHITELIST = 13_UNCHANGED
FREE_BRIDGE_MODE = SHADOW_ONLY
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
NEXT = AWAIT_OWNER_POST_R3_PRODUCT_DECISION
```
