# Shadow Candidate Input Authority Convergence

```text
AUTHORITY = W2_SHADOW_CANDIDATE_INPUT_AUTHORITY_CONVERGENCE_V1
OWNER_DATE = 2026-08-11
OWNER_DECISION = AUTHORIZED
BASE_MAIN_SHA = 001b1bae8e5276597dc506e0cd3cb40dbd180fb5
BASE_RELEASE = PR_517_DEPLOYED
SHADOW_CANDIDATE_LOOP = KEEP_ACTIVE_SHADOW_ONLY
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
REAL_MONEY = OFF
ROUND_4 = NOT_STARTED
P6 = NOT_AUTHORIZED
TERMINAL_GATE = OWNER_SHADOW_CANDIDATE_INPUT_CHAIN_REREVIEW
```

## Why this authority exists

PR #517 correctly enabled the existing SHADOW/CANDIDATE write, settlement and cumulative-validation loop. The current zero-candidate result remains fail-closed and must not be overridden merely to produce output.

Owner postdeploy inspection nevertheless proves that the candidate input chain is not yet coherent enough to treat natural accumulation as evidence toward Formal approval:

1. public team names and public reason/status labels still silently fall back to raw English;
2. persisted per-market radar evidence, selected-market quote identity, match-level readiness and RecommendationDecisionV4 blockers can describe the same fixture with apparently contradictory market/odds availability;
3. the public match diagnostic can let the first failing market dominate the whole match even when another market has materially better evidence;
4. Stage14 coverage remains unaudited or partial for multiple inputs in at least some active leagues.

The profile field `enabled: false` is not accepted as an explanation for missing runtime evidence. In staging, the effective seed status is the OR of the competition profile, future-refresh policy and matchday policy. Runtime diagnosis must report the effective authority sources rather than infer from one profile file.

## Independent root-cause boundaries

The following are already established and must guide implementation:

- Round3 market radar and Model Lab are calculated per market.
- A current snapshot may make a radar market visible while bookmaker depth is still insufficient for model comparison.
- RecommendationDecisionV4 is market-candidate-specific and requires exact executable quote identity, observation lineage, model identity and five-state settlement evidence; radar medians must never be promoted into a candidate.
- The current legacy data-readiness adapter remains match-level and can derive `market_available` / `odds_available` from a selected market/recommendation object that is not the same authority as Round3 radar.
- The current UI chooses one global diagnostic relation and may surface the first non-comparable market as though it describes the whole match.

Therefore the screenshot is evidence of a public aggregation and authority-alignment defect. It does not by itself prove that the Round3 backend literally lets AH bookmaker depth invalidate the OU market object.

## Continuous execution plan

### SC18-01 — Source-bound live authority trace (P0)

Before changing semantics, produce a sanitized read-only trace for live fixture `1493049` and at least two comparison fixtures with persisted market evidence from different competitions.

For each fixture and each of `ASIAN_HANDICAP` / `TOTALS`, record:

```text
radar source status
public market status
snapshot count
latest bookmaker depth
trend evidence status
cross-sectional comparison status
Model Lab status/blockers
quote identity status/freshness
selected market candidate presence
RecommendationDecisionV4 outcome/blockers
match data-readiness field statuses
shadow candidate status
```

The trace must identify the exact first point where `market` or `odds` becomes missing. It must use persisted evidence only: Provider calls `0`, business writes `0`.

### SC18-02 — Per-market eligibility contract (P0)

Create one explicit per-market contract with separate dimensions:

```text
observation_status
trend_evidence_status
cross_sectional_comparison_status
model_diagnostic_status
candidate_quote_identity_status
candidate_model_status
candidate_eligibility_status
blockers[]
```

The match aggregate may be `READY`, `PARTIAL` or `NOT_READY`, but it must be derived from its markets and must not erase a usable market because another market is weak.

Required negative and positive cases:

```text
AH 1 bookmaker + OU 7 bookmakers + model READY + exact OU quote identity
=> AH depth insufficient; OU candidate path independently eligible; match PARTIAL

AH 1 bookmaker + OU 7 bookmakers + model NOT READY
=> OU market evidence remains available; OU diagnostic/candidate blocked by model, not AH depth

AH exact quote identity incomplete + OU exact quote identity complete
=> no AH candidate; OU remains independently evaluable

one market stale + one market fresh
=> stale market cannot become current comparison authority; fresh market is not downgraded by the stale market
```

No new bookmaker-depth threshold is authorized. Preserve the existing threshold and expose which market it applies to.

### SC18-03 — Radar / quote identity / readiness convergence (P0)

Align the write-side authorities without weakening RecommendationDecisionV4:

- reuse existing persisted market candidates, quote identity audits, observation IDs, capture IDs and raw payload hashes;
- do not manufacture an executable quote from radar medians or aggregate bookmaker envelopes;
- derive readiness for the selected candidate market from that market's exact quote identity and freshness;
- distinguish `MARKET_EVIDENCE_AVAILABLE` from `EXECUTABLE_CANDIDATE_QUOTE_READY`;
- prohibit an unexplained same-market contradiction where exact candidate quote evidence is complete but the readiness result says `market` / `odds` are missing;
- when no exact executable quote exists, remain `NOT_READY` with a precise market-scoped blocker.

RecommendationDecisionV4 identity, pricing recomputation, five-state settlement distribution, uncertainty and cashflow-edge checks remain unchanged.

### SC18-04 — Public partial-market semantics (P0)

Replace the single worst/first global diagnostic with a source-bound aggregate:

```text
让球：机构深度不足（1 家，低于既有门槛）
大小球：横截面证据可用（7 家）
模型：模拟未就绪
整场：PARTIAL
```

Public requirements:

- the match-level summary names each market that is usable or blocked;
- `INSUFFICIENT_BOOKMAKER_DEPTH` is never presented as a whole-match reason unless every candidate market is blocked by that condition;
- W2 diagnostic and shadow-candidate status state the selected market explicitly;
- a usable OU market is not hidden behind an AH blocker, and vice versa;
- zero candidates remains valid when the candidate model or exact quote identity is not ready.

### SC18-05 — Canonical public-label authority and measurable gaps (P1)

The frontend hand-written dictionary must no longer be the final identity authority.

Use the existing canonical-team and reviewed provider-team crosswalk infrastructure. Extend the canonical/config payload only as necessary to support a reviewed public Chinese display name; do not create or guess translations automatically.

Required behavior:

```text
canonical reviewed Chinese display name available
=> show Chinese name; raw Provider name may appear only in technical detail

canonical identity exists but Chinese display name is missing
=> show an explicit "译名待映射" state plus a stable team identity; record the gap

canonical identity unresolved
=> show "球队身份待映射"; fail closed; do not silently present raw English as if localization succeeded
```

Create a repository-bound label coverage matrix for all teams currently observed in the exact 13-league runtime scope, grouped by competition, with counts for:

```text
CHINESE_LABEL_READY
CANONICAL_IDENTITY_READY_LABEL_MISSING
IDENTITY_UNRESOLVED
AMBIGUOUS
```

Create one centralized public enum/reason label registry. CI must enumerate every public status/reason exposed by the unified workspace and fail if a main-screen label is missing. At minimum, `INSUFFICIENT_BOOKMAKER_DEPTH` must render Chinese-first. Raw codes remain in collapsed technical details.

### SC18-06 — Stage14 coverage audit for the exact runtime scope (P1)

Use the existing Stage14 scripts, migrations and whitelist work order. Audit the exact active 13 competitions without changing the whitelist or enabling unsupported inputs.

For each competition record:

```text
effective staging enable sources:
  competition profile
  future_refresh policy
  matchday policy
provider competition mapping
fixture/result/team identity
AH quote depth
OU quote depth
lineups/injuries
xG
ratings
squad value
H2H
settled AH
exact candidate quote path
model input path
```

Classify each domain as:

```text
VERIFIED
PARTIAL
NOT_AUDITED
NOT_AVAILABLE_FROM_CURRENT_PROVIDER
DATASET_MAPPING_REQUIRED
OWNER_DECISION_REQUIRED
```

`enabled: false` in a competition profile must never be reported as the standalone runtime cause when another policy enables the competition.

This stage is an audit and remediation plan, not authority to add a Provider, buy a plan, change cadence, activate external intelligence, bypass identity review, invent data or weaken a candidate gate. If completion requires one of those actions, produce an Owner decision packet and continue all independent in-scope work.

### SC18-07 — Regression, merge, deployment and live rereview (P1)

Required tests include:

- fixture `1493049` or an exact real-shape fixture with AH depth `1` and OU depth `7`;
- per-market partial aggregation;
- same-market radar/quote/readiness consistency;
- no executable quote identity => no candidate;
- model not ready => market evidence remains visible but candidate remains blocked;
- no silent English team-name fallback;
- all public enums Chinese-first;
- Stage14 effective-enable source reporting;
- dashboard read Provider calls `0`, business writes `0`;
- Formal/Lock/Production/real-money remain off.

Run focused and full Python tests, Ruff, MyPy, Web typecheck/build/E2E, contract and real-shape visual tests, secret scan, tracked-output/protected-evidence gates, Repository Hygiene, exact-head Full CI and `RELEASE_REQUIRED`.

After exact-head PASS:

1. merge automatically;
2. deploy only through the Owner-local OCI relay path;
3. verify exact Web/API release identity, health, ready and release sync;
4. verify live public copy and per-market partial state;
5. verify the current zero-candidate result remains truthful unless a fixture independently satisfies the unchanged V4 contract;
6. update `CURRENT_STATE.yaml`, `NEXT_ACTION.md` and the Round4 packet exact identity only;
7. stop at `OWNER_SHADOW_CANDIDATE_INPUT_CHAIN_REREVIEW`.

## Evidence accumulation rule during remediation

The existing SHADOW/CANDIDATE scheduler loop remains active. Existing ledger records and historical evidence must not be deleted.

However, no new claim that the Formal approval threshold has been met may rely on an affected candidate/input identity until this remediation passes and the exact market-scoped authority is proven. Natural settlement and validation may continue; Formal remains off.

## Terminal classifications

```text
OWNER_SHADOW_CANDIDATE_INPUT_CHAIN_REREVIEW
SHADOW_CANDIDATE_INPUT_CHAIN_DEPLOYMENT_ROLLED_BACK
SHADOW_CANDIDATE_INPUT_CHAIN_SCOPE_BLOCKED_OWNER_DECISION_REQUIRED
```

## Frozen stop lines

```text
NEW_PROVIDER_OR_PLAN = NOT_AUTHORIZED
MANUAL_PROVIDER_PROBE = FORBIDDEN
SCHEDULER_OR_CADENCE_CHANGE = NOT_AUTHORIZED
ACTIVE_WHITELIST_CHANGE = NOT_AUTHORIZED
MODEL_FACTOR_THRESHOLD_CHANGE = NOT_AUTHORIZED
MODEL_RETRAINING = NOT_AUTHORIZED
BOOKMAKER_DEPTH_THRESHOLD_CHANGE = NOT_AUTHORIZED
MARKET_DIRECTION_BENCHMARK_DEFINITION = NOT_AUTHORIZED
EXTERNAL_INTELLIGENCE_ACTIVATION = NOT_AUTHORIZED
PHASE_0_5_REEXECUTION = FORBIDDEN
H_RESULT_ACCESS = PERMANENTLY_CLOSED
ROUND_4_START = NOT_AUTHORIZED
P6_EXECUTION = NOT_AUTHORIZED
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
REAL_MONEY = OFF
READ_PROVIDER_CALLS = 0_REQUIRED
READ_DB_BUSINESS_WRITES = 0_REQUIRED
VPS_DIRECT_GHCR_BULK_IMAGE_PULL = FORBIDDEN_AS_PRIMARY_TRANSPORT
IMAGE_TRANSPORT = LOCAL_OCI_RELAY_PRIMARY
DELETE_PROTECTED_HISTORICAL_EVIDENCE = FORBIDDEN
```