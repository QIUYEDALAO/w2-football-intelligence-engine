# W2 Owner Review B — Bounded Remediation

```text
AUTHORITY = W2_OWNER_REVIEW_B_REMEDIATION_V1
OWNER_REVIEW_B = CHANGES_REQUIRED
REVIEWED_MAIN = f0fe9d332d05a84f1ef04be86fd9fb44b69d69e3
REVIEWED_PR = 498
REVIEWED_HEAD = a067adbd1d2796cc69ea10bd8cff9aeadf7abee9
REVIEWED_CONTEXT = 131ab138cc4c6b04f65c0a36e4e86d32652d8dd1
P3 = NOT_AUTHORIZED
ROUND_4 = NOT_STARTED
REMEDIATION_SCOPE = BOUNDED_P1_P2_CONTRACT_CLOSURE_ONLY
```

## 1. Review result

P1/P2 architecture is accepted in direction: one unified checkpoint-backed read model, no Provider call on read, no public ROI/CLV, explicit unavailable/not-connected/not-defined states, reuse of existing DayView/Round-3/scoreline/replay/performance foundations, and no P3/old Boss implementation.

Exact-head `RELEASE_REQUIRED` is green, but Owner Review B is not yet PASS because the final P2 schema/contract does not machine-bind several already-approved P0 invariants. These are contract-closure defects, not a redesign.

Use the existing PR #498. Do not create a new architecture or a second read model.

## 2. B1 — P1 field coverage omitted approved P0 Attention/replay fields

P0 requires Attention Feed fields including:

```text
intelligence state
fixture identity and kickoff context
evidence/reason code
affected domain
factual summary
readiness/risk context
next evaluation when available
```

Current P1 `DASHBOARD_DATA_CONTRACT.md` binds only fixture/kickoff, intelligence state, reason codes, and risks under `attention[]`. It does not bind affected domain, factual summary, readiness context, or next evaluation as Attention fields.

Required closure:

- update P1 contracts so every P0 Attention field has an explicit source/availability/freshness/readiness/no-call binding;
- expose a deterministic Attention payload sufficient for P3 without frontend archaeology or product-semantic recomputation;
- at minimum include affected domain, factual summary, readiness status/context, and `next_eval_at` when available;
- use existing intelligence/readiness/reason evidence only; no invented signal or Provider call.

P0 also requires history/replay to answer **what W2 judged and why**. Existing `build_replay_front_door()` already emits `decision_summary`, but P2 `WorkspaceHistoryReplay` and `workspace._validation()` drop it.

Required closure:

- add `decision_summary` to the final history/replay schema and adapter;
- preserve the existing replay front-door value; do not create a second replay engine;
- update deterministic sample and contract tests.

## 3. B2 — Seven-state and four-risk invariants are not fail-closed in the final schema

P0 freezes exactly seven intelligence states:

```text
COLLECTION_INCIDENT
DATA_INCOMPLETE
MODEL_DIAGNOSTIC_WARNING
MARKET_ANOMALY
MODEL_MARKET_DISAGREEMENT
MARKET_MOVEMENT
MARKET_STABLE
```

and exactly four independent risk dimensions:

```text
EVENT_RISK
DATA_RISK
MODEL_RISK
COLLECTION_RISK
```

Current P2 schema uses unrestricted `str` for `intelligence_state` and unrestricted `dict[str, Any]` for `risks` in both Attention and Match objects. The current P2 unit fixture itself uses lower-case risk keys and `market_risk` instead of the frozen `EVENT_RISK`, yet schema validation passes. Therefore the final schema does not enforce the approved contract.

Required closure:

- make intelligence state fail-closed to the exact seven allowed values;
- make risk dimensions fail-closed to exactly EVENT_RISK / DATA_RISK / MODEL_RISK / COLLECTION_RISK with no extra/missing dimension;
- preserve the existing production `risk_dimensions` structure rather than inventing a second risk model;
- correct test fixtures to production-shaped risk keys;
- add negative contract tests proving unknown intelligence states, missing risk dimensions, extra risk dimensions, and `MARKET_RISK` are rejected.

## 4. B3 — Scoreline Top 3 loses explicit approved probability/sample semantics

P0 requires the existing scoreline capability to remain:

```text
seeded 10,000-simulation projection
Top 3 scorelines
unconditional probability for each scoreline
MODEL SCORELINE REFERENCE
NOT_PROVEN
```

The existing scoreline engine emits `simulations_completed = 10000`, `sample_count`, `unconditional_probability`, `conditional_probability`, and a compatibility `probability` equal to the unconditional probability.

Current P2 final schema allows any `simulations_completed >= 1`, and `WorkspaceScoreline` exposes only a generic `probability`. The adapter copies `row.probability` and drops the explicit `unconditional_probability` name. This makes the final P2 contract weaker/ambiguous compared with the approved P0 semantics.

Required closure:

- final P2 scoreline payload must expose `unconditional_probability` explicitly;
- `READY` scoreline reference must machine-bind the existing 10,000-simulation invariant;
- preserve per-score `sample_count`;
- do not expose conditional probability as the primary displayed probability;
- no second scoreline engine and no simulation on API read;
- add contract tests proving READY rejects non-10,000 samples and that the mapped probability is the source `unconditional_probability`.

## 5. What already passes and must not be reopened

Do not redesign these accepted parts:

- one `w2.dashboard-intelligence-workspace.v1` authority;
- GET `/v1/dashboard/intelligence-workspace`;
- checkpoint/read-model source boundary;
- no-call-on-read and no-write-on-read fail-closed contract;
- 0 / 1 / 2+ snapshot semantics;
- `NOT_CONNECTED`, `NOT_DEFINED`, `NOT_PROVEN` semantics;
- API-Football Prediction = explicit `NOT_AVAILABLE` / external benchmark role;
- public ROI/CLV and legacy product-authority field exclusion;
- Probability Validation / Directional / League Performance / Forward Records foundation;
- domain-specific freshness and lineup 1/13 limitation;
- Formal/Candidate/Lock/Production OFF;
- historical Step4/Post4 remains superseded;
- no old Boss L1/L2 rebuild;
- Post-R3 Path A remains unchanged background runtime.

## 6. Remediation execution contract

Use PR #498 and its existing branch. Minimal changes only to P1/P2 docs/schema/adapter/sample/tests and package-matrix counts if mechanically required.

Forbidden:

```text
P3 UI IMPLEMENTATION
PROVIDER CALLS
SCHEDULER/CADENCE CHANGE
WHITELIST CHANGE
MODEL/THRESHOLD CHANGE
MIGRATION UNLESS AN UNEXPECTED HARD REQUIREMENT IS PROVEN AND OWNER STOPS TO REVIEW
PHASE_0_5 REEXECUTION
ROUND_4
CANDIDATE/FORMAL/LOCK/PRODUCTION ENABLEMENT
LEGACY DELETION
```

Required evidence after remediation:

- exact new PR head SHA;
- P1 contracts updated for the missing approved fields;
- exact-seven-state / exact-four-risk schema tests, including negative cases;
- scoreline 10,000 + unconditional-probability contract tests;
- replay `decision_summary` schema/sample/test;
- existing 0/1/2+, forbidden-field and no-call-on-read regressions still PASS;
- focused tests + full exact-head CI / `RELEASE_REQUIRED` PASS;
- Repository Hygiene PASS;
- clean worktree.

Terminal state:

```text
OWNER_REVIEW_B = REMEDIATION_COMPLETE_READY_FOR_REREVIEW
P3 = NOT_AUTHORIZED
NEXT = OWNER_REVIEW_B_REREVIEW
```

Do not merge or start P3 automatically.