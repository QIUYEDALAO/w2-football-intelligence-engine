# W2 MI Round 3 — Codex Continuous Execution

```text
TASK = W2_MI_R3_MARKET_RADAR_AND_MODEL_LAB
OWNER_AUTHORIZATION = ROUND_3_OWNER_AUTHORIZATION.md
ROUND_3 = AUTHORIZED_IN_PROGRESS
```

## 0. Start from live truth

Before editing:

```bash
git fetch origin main context/current --prune
```

Record exact `origin/main` and `origin/context/current` SHAs. The main SHA at authorization was:

```text
R3_AUTHORIZATION_MAIN_SHA = c241b877a4168659f465163108f7a53fb8fd82a5
```

Read in order:

```text
CURRENT_STATE.yaml
NEXT_ACTION.md
ROUND_3_OWNER_AUTHORIZATION.md
ROUND_3_CODEX_EXECUTION.md
ROUND_3_ACCEPTANCE_CRITERIA.md
FREE_PLAN_BRIDGE_CONTROLLED_RUNTIME_RECEIPT.md
CURRENT_PRODUCT_DESIGN.md
REPOSITORY_HYGIENE_POLICY.md
```

Use code, DB/read models, real persisted lineage, tests, CI and runtime output as truth. Do not trust PR prose or comments as proof.

## 1. Independent code audit before implementation

Trace the real public/read path from persisted market observations to the current intelligence console.

At minimum inspect:

```text
src/w2/dashboard/intelligence.py
src/w2/dashboard/day_view.py
src/w2/markets/analysis_evidence.py
src/w2/markets/devig.py
market observation repositories/read models
fixture identity/readiness paths
apps/web/src/components/IntelligenceConsole.tsx
apps/web/src/types/dashboard.ts
relevant API routes/adapters/tests
```

Identify:

- existing authoritative normalized market-observation schema;
- how main/canonical AH and OU lines are chosen today;
- how bookmaker identity and quote freshness are represented;
- existing movement/timeline code, if any;
- current model simulation/calibration outputs;
- every public dependency on legacy V4 edge fields.

Do not create a parallel market model if existing authoritative facts can be reused.

## 2. Evidence eligibility gate

Create one explicit Round-3 evidence eligibility contract before analytics.

A market observation is eligible only if the evidence proves, as applicable:

```text
real/non-synthetic source
raw payload lineage present
endpoint capture lineage present
fixture identity resolved
competition in exact active 13
valid bookmaker identity
supported canonical market = ASIAN_HANDICAP or TOTALS
valid line and decimal price
valid captured_at / quote timestamp
pre-kickoff when used for prematch radar
no known identity conflict
no duplicate conflicting observation identity
```

Rejected evidence must carry reason codes; do not silently discard or coerce it.

Do not treat old recommendation status as evidence eligibility.

## 3. Canonical market timeline

Build a read-only timeline contract from existing normalized observations.

For each fixture × market, retain enough identity to distinguish:

```text
competition
fixture
market
canonical/main line
bookmaker
selection side
capture/quote time
price
raw/capture/observation lineage
```

Comparable snapshots must refer to the same market identity. AH home/away lines must preserve sign symmetry; totals over/under lines must preserve same-line identity.

Do not compare a quote from one line against a model or price from another line.

### 3.1 Current market facts

For each supported fixture/market where evidence permits, expose:

```text
current_line
current_prices_by_side
current_bookmaker_count
current_bookmakers
captured_at
quote_updated_at where authoritative
freshness_status
snapshot_count
observation_count
```

### 3.2 De-vig and overround

Reuse the existing proportional de-vig contract unless current authoritative code establishes another product method.

For each complete two-sided bookmaker quote:

```text
raw implied probabilities
overround
de-vig probabilities
```

Then produce market-distribution facts:

```text
bookmaker_count
probability median by side
probability min/max by side
overround min/p25/p50/p75/max where sample count supports it
```

Do not interpret high/low overround as value, opportunity or information quality.

## 4. Market Radar movement contract

Round 3 must distinguish factual movement from statistical anomaly.

Required movement statuses:

```text
INSUFFICIENT
STABLE
PRICE_MOVEMENT
LINE_MOVEMENT
LINE_AND_PRICE_MOVEMENT
```

Minimum logic:

- `< 2` eligible comparable snapshots -> `INSUFFICIENT`;
- canonical line unchanged and selected comparable prices unchanged -> `STABLE`;
- line unchanged but comparable selected prices/de-vig probabilities changed -> `PRICE_MOVEMENT`;
- canonical line changed -> `LINE_MOVEMENT` or `LINE_AND_PRICE_MOVEMENT` as supported.

Record factual deltas:

```text
line_delta
price_delta_by_side
probability_delta_by_side
previous_captured_at
current_captured_at
elapsed_seconds
```

The public `MARKET_MOVEMENT` state may consume a ready non-stable movement contract.

### 4.1 Statistical anomaly

Do **not** invent a percentile or sigma threshold merely to emit `MARKET_ANOMALY`.

Create an anomaly-calibration field:

```text
STATISTICAL_ANOMALY_CALIBRATION = CALIBRATED | NOT_CALIBRATED
```

If the existing real evidence is not sufficient for a defensible, documented calibration, keep it `NOT_CALIBRATED` and do not emit statistical `MARKET_ANOMALY` from magnitude alone.

Explicit structural/source anomalies may continue to surface through existing validated contracts and precedence.

## 5. Model Lab diagnostic contract

Build a new public diagnostic projection that does not inherit recommendation authority.

For the exact same market/line:

1. use current complete, fresh bookmaker quotes;
2. de-vig each complete bookmaker pair;
3. require at least 3 bookmakers for a public consensus-range comparison;
4. obtain model effective settlement probability from existing simulation/calibration outputs;
5. compare the model probability against the real bookmaker distribution.

Required statuses:

```text
MODEL_NOT_READY
MARKET_NOT_READY
INSUFFICIENT_BOOKMAKER_DEPTH
COMPARABLE_WITHIN_MARKET_RANGE
MODEL_OUTSIDE_MARKET_RANGE
```

Required facts:

```text
market
line
selection/side
bookmaker_count
market_probability_median
market_probability_min
market_probability_max
model_effective_probability
model_minus_market_median
distance_below_market_min
distance_above_market_max
model_version
calibration_version/status
model_input_hash where available
quote/capture lineage identity
```

`MODEL_MARKET_DISAGREEMENT` is allowed only when status is `MODEL_OUTSIDE_MARKET_RANGE` and all readiness/depth/same-line/freshness gates are satisfied.

Do not call it actionable, profitable, value, edge or opportunity.

## 6. Legacy edge semantic isolation

Audit all public/read-model paths for fields from `analysis_evidence.py` and V4 that can leak edge semantics into Round 3.

Round-3 public Market Radar / Model Lab contracts must not use as authority:

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
MIN_MARKET_ANCHOR_DIVERGENCE
```

If legacy code is still required by supported internal/V4 compatibility paths, preserve it behind a clearly separate adapter. Do not delete referenced compatibility code solely to make the new contract clean.

Add contract tests proving the Round-3 public payload does not expose or depend on the forbidden edge fields.

## 7. Intelligence state integration

Preserve the frozen precedence and risk dimensions.

Update the intelligence projection only as necessary to consume the new authoritative Round-3 contracts.

Required behavior examples:

```text
collection failure -> COLLECTION_INCIDENT
data/identity/freshness incomplete -> DATA_INCOMPLETE
model unavailable/calibration warning -> MODEL_DIAGNOSTIC_WARNING
explicit validated anomaly -> MARKET_ANOMALY
ready model outside real >=3-bookmaker range -> MODEL_MARKET_DISAGREEMENT
ready non-stable market timeline -> MARKET_MOVEMENT
ready comparable market with no material factual change -> MARKET_STABLE
```

Precedence must remain unchanged.

## 8. API/read model

Expose one stable Round-3 read contract consumable by public surfaces.

Prefer extending current analysis/day-view read models rather than creating a second API tree.

The read contract should provide at least:

```text
market_radar
model_lab
intelligence_state
risk_dimensions
evidence/status reason codes
```

It must fail closed when evidence is missing.

No endpoint may execute Provider calls merely because a user opens the dashboard.

## 9. Web integration

Integrate Round 3 into the existing public surfaces, not a new recommendation console.

### Market Overview

Preserve existing counters and show truthful intelligence counts derived from the same backend state.

### Match Intelligence

Add/complete two factual sections where data exists:

```text
Market Radar
Model Lab
```

Market Radar should make current line, prices, freshness, bookmaker depth, overround and movement understandable.

Model Lab should show model probability vs bookmaker market median/range and diagnostic status.

When insufficient:

```text
INSUFFICIENT / NOT_READY
```

must render explicitly rather than showing zeros as facts.

Forbidden UI language includes:

```text
value bet
edge opportunity
recommended bet
bet now
high value
profitable signal
```

Do not resurrect recommendation-first surfaces removed/frozen by Round 1.

## 10. Performance and query discipline

Avoid N+1 queries over fixture × bookmaker × snapshot.

For a day view, market-radar/model-lab evidence should be built with bounded query count and deterministic ordering.

Add tests/measurements sufficient to prove the new read path does not scale Provider calls with dashboard views and does not introduce obvious per-row DB query loops.

## 11. PR / CI governance

Use the smallest coherent PR structure.

Default: one Round-3 PR. A maximum of two PRs is allowed only if separation is needed between backend contract/runtime and Web/public integration.

For every PR:

- Provider calls during development/CI = 0;
- focused tests PASS;
- full repository-required tests PASS;
- Ruff PASS;
- Mypy PASS;
- Web typecheck/build where touched;
- Playwright/public contract tests where touched;
- secret scan PASS;
- protected-baseline gates PASS;
- PR Fast / required Release Candidate PASS.

In-scope failure -> fix and rerun without new owner approval.

Merge only accepted final heads and record exact SHAs/run IDs.

## 12. Deployment and runtime acceptance

After required PRs merge, use the existing immutable W2 staging release path.

Do not change Free bridge quota policy or SHADOW_ONLY mode.

Runtime acceptance must primarily use real persisted evidence already collected by the accepted bridge and historical persisted lineage that passes the Round-3 eligibility gate.

Manual diagnostic Provider calls for Round 3 acceptance:

```text
0 by default
```

Existing accepted scheduler/bridge calls may continue normally under its existing quota contract; do not create special traffic to make Round 3 pass.

Verify at least:

- one fixture/market with `MARKET_MOVEMENT` if real comparable snapshots support it, otherwise document why current real evidence is `INSUFFICIENT`/`STABLE` without fabricating movement;
- one Model Lab ready comparison if model and >=3-bookmaker same-line evidence exists, otherwise truthful `MODEL_NOT_READY`/`MARKET_NOT_READY`/depth status;
- no recommendation/execution rows created;
- dashboard/public API views cause zero Provider calls.

## 13. Rollback

Round-3 public projection/integration must have a non-destructive rollback path consistent with current deployment practices.

Rollback must not delete raw/capture/market evidence or disable the accepted Free bridge unless separately required.

## 14. Repository hygiene

Before PASS:

1. classify all added/replaced assets;
2. remove provably dead temporary scripts, adapters, duplicate DTOs, stale fixtures and obsolete docs;
3. retain canonical Radar/Model Lab contracts/tests and required evidence;
4. rerun required gates.

Required:

```text
REPOSITORY_HYGIENE = PASS
UNRESOLVED_HYGIENE_ITEMS = 0
```

## 15. Final receipt

Create `ROUND_3_FINAL_RECEIPT.md` with:

```text
R3_BASE_MAIN_SHA
R3_FINAL_MAIN_SHA
PR numbers and final heads/merge SHAs
CI / RC / promotion run IDs
immutable deployment identity/digests
eligible real observation counts
rejected evidence counts/reasons
Radar ready/insufficient/stable/movement counts
statistical anomaly calibration status
Model Lab ready/not-ready/depth/disagreement counts
proof forbidden edge fields are absent from public authority
Provider calls during dev/CI
manual Provider calls during acceptance
Free bridge mode/quota invariants
active whitelist before/after
audit-only reachability
Candidate/Formal/Lock/Production
Round 3 status
repository hygiene
```

Expected terminal state if all acceptance criteria pass:

```text
ROUND_3 = PASS_MARKET_RADAR_MODEL_LAB
FREE_BRIDGE_MODE = SHADOW_ONLY
ACTIVE_WHITELIST = 13_UNCHANGED
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
NEXT = AWAIT_OWNER_POST_R3_PRODUCT_DECISION
```
