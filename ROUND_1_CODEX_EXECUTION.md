# W2 MI Round 1 — Codex Execution Authority

This file is current execution authority for Codex. It is maintained directly on branch `context/current` without PR/CI/deployment.

## 0. Authorized task

```text
PRODUCT = W2 Football Intelligence
PROGRAM = W2_FOOTBALL_MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
TASK = W2_MI_R1_PRODUCT_SEMANTICS_AND_STATUS_REFRAME
OWNER_DECISION = APPROVED
```

Round 1 is one bounded runtime API/Web refactor. Do not split it into preparatory/API/Web/cleanup PRs.

## 1. Authority and source

Before editing code:

```bash
git fetch origin main context/current --prune
```

Use latest trusted `origin/main` as the code baseline. Record its exact SHA.

Use `origin/context/current` as the task/product authority. Read in order:

1. `CURRENT_CONTEXT.md`
2. `CURRENT_STATE.yaml`
3. `CURRENT_PRODUCT_DESIGN.md`
4. `CURRENT_TASK_CHECKLIST.md`
5. `NEXT_ACTION.md`
6. `ROUND_1_CODEX_EXECUTION.md`
7. `ROUND_1_ACCEPTANCE_CRITERIA.md`
8. `AI_PROJECT_CONTEXT.md`
9. `AI_QUANT_PROJECT_CONTEXT.md`
10. `AGENTS.md`
11. `QUANT_AGENTS.md`
12. `.github/copilot-instructions.md`

If old files on `main` conflict with `context/current`, `context/current` controls the current task. Do not copy context files into the runtime PR.

## 2. League correction — binding

The current active whitelist baseline is **13 competitions**, not 11.

```text
ACTIVE_WHITELIST_BASELINE_COUNT = 13
ROUND_1_WHITELIST_CHANGE = FORBIDDEN
```

Current 13 baseline identities:

```text
chinese_super_league
allsvenskan
eliteserien
premier_league
la_liga
bundesliga
serie_a
ligue_1
brasileirao_serie_a
argentina_primera
mls
eredivisie
primeira_liga
```

The previously documented European `5 + 6` grouping is **not** a replacement whitelist.

Core Benchmark (5, all already inside the 13 baseline):

```text
Premier League
La Liga
Bundesliga
Serie A
Ligue 1
```

Extended Radar cohort (6):

```text
Eredivisie                 # already in baseline
Primeira Liga              # already in baseline
Belgian Pro League         # net-new candidate
Turkish Super Lig          # net-new candidate
Greek Super League         # net-new candidate
Scottish Premiership       # net-new candidate
```

Therefore the future Round 2 candidate universe is the union:

```text
13 EXISTING + 4 NET_NEW = 17 TOTAL CANDIDATES
```

This is only future planning. **Round 1 must not register, enable, call, audit, or schedule any of the 4 net-new competitions.**

## 3. Permanent product guard

```text
MODEL_MARKET_DIVERGENCE != MARKET_OPPORTUNITY
RecommendationDecisionV4 = DIAGNOSTIC_INPUT_NOT_PRODUCT_AUTHORITY
```

Do not delete V4, DecisionContract, settlement, historical replay, or historical validation evidence.

V4 may remain visible to technical diagnostics, but it must no longer control the public product's top-level state, card visibility, market-fact visibility, ranking, counters, next action, or opportunity/recommendation language.

## 4. Required public intelligence projection

Create or adapt one canonical public intelligence projection. Prefer additive read-model projection; do not introduce a DB migration unless code evidence proves it is unavoidable.

Every public fixture/card projection must expose one deterministic top-level state:

```text
MARKET_STABLE
MARKET_MOVEMENT
MARKET_ANOMALY
MODEL_MARKET_DISAGREEMENT
DATA_INCOMPLETE
MODEL_DIAGNOSTIC_WARNING
COLLECTION_INCIDENT
```

Freeze precedence for Round 1:

```text
COLLECTION_INCIDENT
> DATA_INCOMPLETE
> MODEL_DIAGNOSTIC_WARNING
> MARKET_ANOMALY
> MODEL_MARKET_DISAGREEMENT
> MARKET_MOVEMENT
> MARKET_STABLE
```

Retain secondary deterministic reason codes so lower-precedence facts are not lost.

Round 1 may only map existing explicit movement/anomaly evidence. Do **not** invent Round 3 thresholds, overround percentiles, persistence rules, bookmaker-confirmation formulas, or alert scores.

`MARKET_STABLE` is a valid success result. Zero material alerts must remain non-empty and must not lower thresholds to create content.

## 5. Four independent risk dimensions

Public product risk must expose four separate dimensions:

```text
EVENT_RISK
DATA_RISK
MODEL_RISK
COLLECTION_RISK
```

Each dimension needs deterministic status/reason codes/human explanation.

Rules:

- `NOT_READY` / `BLOCKED` are not high-risk matches.
- missing identity/xG/ratings/required quote/readiness -> data/model readiness evidence;
- Provider/Scheduler/schema/runtime failures -> collection risk/incidents;
- actual lineup/injury/event facts -> event risk;
- model readiness/calibration/feature staleness/divergence -> model risk;
- never merge data + collection back into one generic betting-risk score;
- no risk dimension implies a betting recommendation.

## 6. Market facts must be independent from V4 selection

Current market facts must not disappear merely because V4 is `NOT_READY`, `NO_EDGE`, has no selected candidate, or has no pick.

Where truth exists, preserve read-only display of:

```text
fixture/team/competition identity
AH and OU current or last-known market
line/price
bookmaker/confirmation evidence already available
captured_at
freshness
market probabilities where legitimately available
existing line/price movement evidence
lineup/data readiness
model probabilities/model diagnostics
evidence lineage/blockers
```

Never promote stale/reference-only quotes into current/executable quotes.

## 7. Public surfaces

The root public product must become intelligence-first and visibly identify:

```text
W2 Football Intelligence
W2 Football Market Intelligence & Model Diagnostics
```

Minimum Round 1 structure:

```text
Market Overview
Match Intelligence
Data & Operations Summary
```

Minimum Market Overview counters:

```text
monitored fixtures
market-complete fixtures
fresh quotes
market-stable fixtures
market-movement fixtures
model diagnostic warnings
data incidents
collection incidents
```

Optional additional intelligence counters:

```text
market anomalies
model-market disagreements
```

Do not use recommendation-first counters as public product KPIs:

```text
analysis picks
formal recommendations
lock eligible
NO_EDGE
opportunities
positive EV
```

Historical settlement/performance data may remain available as explicitly historical diagnostics; it must not be presented as proof of current betting edge.

## 8. Divergence guard — machine and browser

Any model-market divergence may produce only diagnostic language such as:

```text
model-market disagreement
model calibration review required
model feature may be stale
market information not explained by model
model drift/overconfidence review
```

It must never generate public product semantics equivalent to:

```text
value opportunity
positive edge
market mispricing
recommended side
high-confidence pick
worth entering
价值机会
正 EV 机会
市场错误定价
推荐方向
高置信度选择
值得介入
```

Remove the current public chain where divergence magnitude/status/direction_allowed determines recommendation readiness or ranking.

## 9. Likely implementation paths from code audit

Inspect real current code first. Expected active paths include:

```text
src/w2/api/repository.py
src/w2/dashboard/day_view.py
src/w2/api/routers.py
src/w2/api/schemas.py
apps/web/src/App.tsx
apps/web/index.html
apps/web/src/components/DashboardPage.tsx
apps/web/src/components/DecisionCounts.tsx
apps/web/src/lib/dashboardApi.ts
apps/web/src/types/dashboard.ts
apps/web/src/reference/dashboard-v2/*
apps/web/src/reference/boss-console/*
```

Do not make cosmetic renames merely to satisfy terminology. Change the actual public authority and behavior.

## 10. Hard Round 1 stop lines

```text
LEAGUE_EXPANSION = false
ACTIVE_WHITELIST_COUNT = 13_UNCHANGED
PROVIDER_POLICY_CHANGE = false
PROVIDER_ALLOWLIST_CHANGE = false
SCHEDULER_POLICY_CHANGE = false
NEW_PROVIDER_CALLS = 0
ROUND_2_CAPABILITY_AUDIT = NOT_STARTED
ROUND_3_MARKET_RADAR = NOT_STARTED
DB_MIGRATION_EXPECTED = 0
MODEL_RECOMPUTE_EXPECTED = 0

CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
```

Do not reopen Phase 0.5 or H. Do not build Signal Ledger for execution, Portfolio, Kelly/Risk, 2x1, auto-betting, or real-money workflows.

## 11. Single delivery cycle

Use exactly one bounded runtime PR.

Implementation may use focused local tests. Once the PR is stable:

1. `PR_FAST_REQUIRED = SUCCESS`.
2. Freeze final PR head.
3. Run exactly one final exact-head Full Release Candidate using the repository's existing `release-candidate.yml` with the final PR head SHA.
4. Do not change code after the successful RC head is frozen.
5. Merge once using merge commit; no squash, rebase, or auto-merge.
6. Deploy the verified immutable API/Web images once.
7. API and Web must expose the same verified source/release SHA.
8. Perform one public browser acceptance.
9. Stop. Do not begin Round 2 automatically.

## 12. Completion authority

Round 1 can be marked PASS only if every requirement in `ROUND_1_ACCEPTANCE_CRITERIA.md` passes.
