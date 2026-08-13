# SC21 Stage14 Factor Coverage and Model Input Convergence

```text
AUTHORITY = W2_SC21_STAGE14_FACTOR_COVERAGE_AND_MODEL_INPUT_CONVERGENCE_V1
OWNER_DATE = 2026-08-14
OWNER_DECISION = AUTHORIZED
BASE_MAIN_SHA = 3b7f87db2f0cb49d75582313ca593d30262c0d3d
DEPLOYED_SOURCE_SHA = VERIFY_AND_RECONCILE_FIRST
PR_532 = MERGED_RETAIN_EXACT_13_T168_T72_T48_COLLECTION
PR_533 = MERGED_RETAIN_DIRECT_FIXTURE_CHECKPOINT_EXECUTION
SHADOW_CANDIDATE = KEEP_ACTIVE_SHADOW_ONLY
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
REAL_MONEY = OFF
ROUND_4 = NOT_STARTED
P6 = NOT_AUTHORIZED
TERMINAL_GATE = OWNER_SC21_FACTOR_INPUT_CHAIN_POSTDEPLOY_REREVIEW
```

## Owner decision

The current bottleneck is no longer primarily AH/OU presence. The next workstream must establish the exact factor/input truth for the active 13-league runtime and then repair only the highest-value, evidence-backed input chains.

The current Codex/VPS snapshot is accepted as a provisional observation that must be reproduced into repository-bound evidence before implementation claims are made:

```text
future fixtures reviewed = 19
persisted AH/OU evidence = 19/19, freshness and candidate eligibility mixed
usable four-field xG = 3/19
model unavailable because xG/input chain = 16/19
lineups = 0/19 future fixtures, currently before T-60/T-45/T-30 windows
matching ratings = 0/19
team_value_asof_artifacts = 0 despite persisted player valuations
shadow candidates = 0/19
```

Do not treat these counts as a permanent contract until SC21-01 reproduces them with exact fixture IDs, source timestamps, row counts and hashes.

## Independent corrections that bind this plan

1. **xG is a simulation hard gate, not a universal DataReadiness hard gate.** The current simulation returns `INSUFFICIENT_INPUTS` unless all four home/away xG-for/xG-against values exist. The general data-readiness policy still treats xG, ratings, team value and lineups as advisory unless an explicit policy says otherwise.
2. **Ratings, squad value and lineup inputs are current-model enhancements.** They may affect calibrated lambdas or factor diagnostics when eligible, but their absence must not be misreported as the same blocker as missing four-field xG.
3. **Persisted market evidence is not automatically candidate-ready.** Presence, current freshness, bookmaker depth, exact executable quote identity, model readiness and RecommendationDecisionV4 eligibility remain separate gates.
4. **Statistics is currently disabled in the matchday policy.** SC21 may consume and materialize already-persisted statistics evidence, but it may not silently enable a new statistics collection path or change endpoint/cadence policy.
5. **Lineups not yet due are not collection failures.** Existing T-60/T-45/T-30 behavior remains unchanged; audit `NOT_YET_DUE`, `DUE_NO_CAPTURE`, `CAPTURED`, and `PROVIDER_EMPTY` separately.
6. **The existing SC18 Stage14 matrix is historical baseline evidence only.** It predates the exact-13 runtime activation and PR #533 checkpoint correction and must not be copied forward as the current truth.
7. **No factor remediation may manufacture candidates.** A truthful zero-candidate result remains acceptable until the unchanged exact quote, model and Decision V4 contracts are independently satisfied.

## Execution model

Execute continuously across separate, reviewable PRs by authority boundary. No Owner relay is required between ordinary in-scope steps.

```text
SC21-A = exact identity + read-only audit artifacts
SC21-B = persisted-evidence xG convergence
SC21-C = no-Provider rating and team-value materialization
SC21-D = public factor semantics + candidate-chain acceptance
SC21-E = final CI, controlled materialization, local OCI deployment, live rereview
```

Do not combine all data, model, UI and deployment changes into one unreviewable PR. Exact-head gates apply to every implementation PR; only the final accepted release is deployed.

## SC21-00 — Exact release/context reconciliation (P0)

Before factor conclusions:

1. fresh-sync `origin/main` and `origin/context/current`;
2. confirm `origin/main` is exactly `3b7f87db2f0cb49d75582313ca593d30262c0d3d` or record the newer exact main if it legitimately advanced;
3. measure VPS API/Web/worker/scheduler source identities;
4. confirm PR #532 exact-13 checkpoint policy and PR #533 direct-fixture worker are the running authorities;
5. if merged main is not deployed, deploy the exact accepted main via Owner-local OCI relay before taking the factor audit snapshot;
6. update current context identity before further claims.

No model, threshold, endpoint, whitelist or cadence change is authorized by this identity reconciliation.

## SC21-01 — Stage14 Factor Coverage Truth Matrix V2 (P0, read-only)

Audit the exact active 13 competitions and the exact persisted future-fixture window used by the current Dashboard/candidate loop. At minimum include the reported 19 fixtures and all fixtures currently inside the persisted T+7 inventory.

For every fixture, team and factor, bind the following dimensions:

```text
fixture_id / competition_id / kickoff_utc
canonical home/away team identity
factor_id / public factor name
source authority and source table/artifact
raw evidence count
materialized artifact count
latest source event / captured_at / as_of
freshness boundary and current age
identity/mapping status
model-consumer path
candidate-consumer path
runtime endpoint/policy status
estimated Provider request cost if raw evidence is absent
```

Classify role at each layer independently:

```text
MARKET_EVIDENCE_GATE
SIMULATION_HARD_GATE
CANDIDATE_HARD_GATE
MODEL_ENHANCEMENT
EXPLANATION_OR_DIAGNOSTIC
POLICY_DISABLED
NOT_CONSUMED
```

Classify the actual reason for every non-ready cell:

```text
NOT_YET_DUE
DUE_NOT_COLLECTED
RAW_EVIDENCE_ABSENT
RAW_PRESENT_NOT_MATERIALIZED
IDENTITY_NOT_MAPPED
UNDER_SAMPLED
STALE
CONFLICTED
PROVIDER_NOT_AVAILABLE
POLICY_DISABLED
OWNER_DECISION_REQUIRED
READY
```

Required separate factor surfaces:

```text
AH observation presence / freshness / bookmaker depth / exact candidate quote
OU observation presence / freshness / bookmaker depth / exact candidate quote
four-field xG
rating/Elo
team value as-of
lineups
injuries
statistics/raw xG source
H2H
historical settled AH
model output
RecommendationDecisionV4 candidate eligibility
```

Mandatory outputs:

```text
docs/review_packages/SC21_FACTOR_INPUT_CONVERGENCE/STAGE14_FACTOR_COVERAGE_MATRIX_V2.json
docs/review_packages/SC21_FACTOR_INPUT_CONVERGENCE/STAGE14_FACTOR_COVERAGE_REPORT_V2.md
docs/review_packages/SC21_FACTOR_INPUT_CONVERGENCE/FUTURE_FIXTURE_FACTOR_TRACE.json
docs/review_packages/SC21_FACTOR_INPUT_CONVERGENCE/FACTOR_ROLE_AUTHORITY_MATRIX.json
```

The matrix must include exact source row counts, evidence timestamps, generated-at time, source hashes and fixture-list hash. Provider calls `0`; business writes `0`.

## SC21-02 — Persisted-evidence xG convergence (P0)

This is the first remediation branch because four-field xG is the direct simulation gate.

Required order:

1. inventory persisted `statistics` raw payloads, canonical fixture identities, `team_xg_match` rows and rolling xG snapshots;
2. run the existing saved-raw xG materialization path in dry-run/read-only mode;
3. distinguish raw-data absence from parser, identity, as-of, sample-count, rolling-window or projection defects;
4. repair deterministic persisted-evidence defects without Provider calls;
5. reject post-kickoff leakage, conflicting duplicate evidence, unresolved team identity and under-sampled rolling windows fail-closed;
6. produce before/after fixture-level xG readiness evidence and exact artifact hashes.

Acceptance:

```text
existing sufficient saved evidence => all four xG inputs materialize and project
insufficient saved evidence => remains unavailable with exact cause
xG absent => simulation remains INSUFFICIENT_INPUTS
xG ready => simulation may run under unchanged model/threshold policy
no raw statistics evidence => no invented proxy xG
```

If additional live `statistics` collection is truly required, do **not** enable it in this workstream. Create:

```text
XG_STATISTICS_COLLECTION_OWNER_DECISION_PACKET.md
```

The decision packet must state per competition: Provider support, historical fixture requirements, expected one-time and ongoing request cost, quota impact, scheduler/cadence implications, retention, identity coverage, expected xG readiness gain and alternatives. Continue every independent no-Provider branch before stopping for that decision.

## SC21-03 — Rating/Elo materialization from existing evidence (P1)

Audit and materialize ratings only from persisted, canonical, pre-match evidence.

Requirements:

- canonical team IDs and as-of cutoff are mandatory;
- disclose the actual source and competitions represented by the existing rating rows;
- do not treat `rolling_xg_proxy` or `PROXY_ONLY` Elo as eligible current-model rating evidence;
- no post-kickoff leakage;
- no Provider calls;
- missing rating remains `MODEL_ENHANCEMENT_NOT_READY`, not the four-field-xG blocker;
- do not change rating weights or calibration parameters.

Produce coverage before/after by competition, fixture and team plus deterministic materialization hashes.

## SC21-04 — Team-value as-of materialization from existing valuation data (P1)

Use the existing `materialize_team_value_asof.py` / canonical identity path rather than creating a second ingestion authority.

Required sequence:

1. dry-run against persisted player valuation source and exact future fixtures;
2. prove player identity, player-to-team membership, competition/season identity, validity interval, currency/unit and as-of cutoffs;
3. report unmapped, ambiguous, duplicated and stale valuations;
4. require exact eligible count and artifact-set hash before any write;
5. materialize team-level as-of artifacts through the existing repository writer;
6. verify read-side/model projection consumes only the generated canonical artifact.

No Provider calls and no invented player/team mapping. Missing team value remains an enhancement gap under current simulation policy.

## SC21-05 — Lineup timing and deferred-domain truth (P1)

Preserve the existing T-60/T-45/T-30 lineup ladder. Do not pull lineups early merely to make the matrix green.

Add evidence and regression coverage for:

```text
before first lineup checkpoint => NOT_YET_DUE
checkpoint due but no attempt => DUE_NOT_COLLECTED
attempt with empty Provider response => PROVIDER_EMPTY
valid capture => CAPTURED
lineup evidence unavailable for a competition => PROVIDER_NOT_AVAILABLE or POLICY_DISABLED
```

Injuries remain `POLICY_DISABLED/NOT_AUDITED` and H2H remains diagnostic unless a separate evidence/cost decision is approved. Matchday `statistics` remains disabled except for any later separately approved xG collection decision.

## SC21-06 — Public factor/input semantics (P1)

The Dashboard and API must use the already accepted single public presentation authority. Do not create a new factor-status page model.

Required Chinese-first distinctions:

```text
xG missing or stale => 模型核心输入未就绪
lineup before T-60 => 尚未到首发采集时间
lineup due but absent => 首发采集尚未形成证据
rating missing => 评级增强输入未就绪
team value missing => 球队身价增强输入未就绪
injuries/statistics disabled => 当前策略未启用 / 仅作审计
H2H insufficient => 诊断样本不足
market evidence present but stale => 历史盘口可见，当前候选比较暂停
aggregate market evidence without exact quote => 市场证据可见，精确候选报价未就绪
```

Do not collapse these into `必需输入缺失`, and do not let technical factor registries directly decide public tone or copy.

## SC21-07 — Shadow-candidate chain acceptance (P0)

Use the unchanged RecommendationDecisionV4 authority. Validate the complete chain per market and fixture:

```text
current AH/OU evidence
bookmaker-depth requirement for that market
exact executable quote identity and freshness
four-field xG and model output
candidate model identity/calibration identity
five-state settlement evidence and uncertainty
Decision V4 outcome
forward-ledger write identity
postmatch settlement identity
```

Required cases:

```text
market evidence ready + xG unavailable => no candidate, model-input blocker
xG ready + exact quote unavailable => no candidate, quote-identity blocker
one market eligible + other market weak => independently evaluate eligible market
all unchanged V4 gates pass => shadow candidate may be written and tracked
no fixture passes => zero candidates is a valid terminal observation
```

Do not lower thresholds, alter market selection rules, promote Radar medians to executable quotes, or enable Formal/Lock/Production.

## SC21-08 — Verification, controlled materialization, merge and deployment (P1)

For every implementation PR:

```text
focused tests
full Python tests
Ruff
MyPy
Web typecheck/build/E2E when public contract changes
secret scan
tracked-output/protected-evidence gates
Repository Hygiene
exact-head CI
RELEASE_REQUIRED
```

After all no-Provider remediation branches pass:

1. merge automatically;
2. deploy exact release through Owner-local OCI relay only;
3. on VPS, run each write-producing materializer as `dry-run -> exact count/hash guard -> controlled apply`;
4. reproject/read through the normal existing pipeline; do not patch Dashboard payloads manually;
5. verify API/Web/worker/scheduler exact release identity, health, ready and release sync;
6. reproduce the factor coverage matrix postdeploy;
7. verify read path `provider_calls=0`, `db_writes=0`, `no_call_on_read=true`;
8. verify natural Scheduler/candidate/settlement loop remains active on the unchanged cadence;
9. refresh the Round4 packet exact release identity only;
10. stop at `OWNER_SC21_FACTOR_INPUT_CHAIN_POSTDEPLOY_REREVIEW`.

## Stop/decision rules

Continue automatically through ordinary audit, parser, identity, materialization, projection, UI, test, CI and deployment-preparation failures:

```text
fix -> revalidate -> continue
```

Stop only the affected branch and create an Owner decision packet if completion requires:

```text
new Provider or paid plan
new live endpoint or statistics activation
scheduler/cadence change
active whitelist change
new external dataset authority
model factor/weight/threshold change
model retraining
bookmaker-depth threshold change
manual identity invention
```

Continue all independent branches before stopping at the terminal Owner gate.

## Frozen stop lines

```text
NEW_PROVIDER_OR_PLAN = NOT_AUTHORIZED
MANUAL_PROVIDER_PROBE = FORBIDDEN
NEW_LIVE_STATISTICS_COLLECTION = NOT_AUTHORIZED_WITHOUT_DECISION_PACKET
SCHEDULER_OR_CADENCE_CHANGE = NOT_AUTHORIZED
ACTIVE_WHITELIST_CHANGE = NOT_AUTHORIZED
MODEL_FACTOR_WEIGHT_THRESHOLD_CHANGE = NOT_AUTHORIZED
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
IMAGE_TRANSPORT = LOCAL_OCI_RELAY_PRIMARY
DELETE_PROTECTED_HISTORICAL_EVIDENCE = FORBIDDEN
RADAR_MEDIAN_AS_EXECUTABLE_QUOTE = FORBIDDEN
PROXY_XG_AS_TRUE_XG = FORBIDDEN
POST_KICKOFF_FACTOR_LEAKAGE = FORBIDDEN
```