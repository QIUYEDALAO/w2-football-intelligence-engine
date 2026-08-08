# W2 MI Round 2 — Binding Acceptance Criteria

This file is the binding acceptance standard for:

```text
W2_MI_R2_FIRST_DIVISION_PROVIDER_CAPABILITY_AUDIT
```

Round 2 is PASS only when the required code/tooling gates, controlled Provider audit gates, 14-day observation gates and final 17-row capability matrix all satisfy this document.

A blocked/insufficient league is not a Round 2 failure if the evidence is truthful and the blocker is preserved. Round 2 fails only when the audit process, evidence integrity, safety boundaries or final classification contract fails.

## A. Source and authority

Required:

```text
ROUND_1 = PASS
ROUND_2_OWNER_AUTHORIZATION = PRESENT
ROUND_2_CODEX_EXECUTION = PRESENT
ROUND_2_INITIAL_MAIN_SHA = f7860813646ce9718931dff331c09ce2fe7a71ba
ROUND_2_EXECUTION_BASE_SHA = exact origin/main used by Codex
ROUND_3 = NOT_STARTED
```

If main advances, record both the initial and actual execution base.

## B. Audit universe — hard gate

Required union count:

```text
EXISTING_WHITELIST_COUNT = 13
NET_NEW_AUDIT_ONLY_COUNT = 4
AUDIT_UNION_COUNT = 17
```

Existing 13 must remain exactly:

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

Audit-only candidates must be exactly:

```text
belgian_pro_league
turkish_super_lig
greek_super_league
scottish_premiership
```

Hard acceptance:

```text
ACTIVE_WHITELIST_BEFORE = 13
ACTIVE_WHITELIST_AFTER = 13
ACTIVE_WHITELIST_IDENTITY_DIFF = EMPTY
NET_NEW_ACTIVE_WHITELIST_ADDITIONS = 0
NET_NEW_SCHEDULER_ADDITIONS = 0
NET_NEW_DAYVIEW_ADDITIONS = 0
```

Fail if audit-only candidates are inserted into runtime whitelist discovery merely to satisfy the audit CLI.

## C. Audit-only candidate isolation — hard gate

Automated tests must prove the four net-new descriptors are unreachable by:

```text
CompetitionRegistry runtime whitelist
future_fixture_refresh competition selection
Scheduler dispatch
DayView fixture selection
analysis-card/public product selection
```

Required:

```text
AUDIT_CANDIDATE_RUNTIME_REACHABILITY = 0
```

A descriptor path under `config/audit_candidates/` or equivalent must be explicitly non-runtime.

## D. Audit-tooling PR scope

Required one bounded Round 2 audit-tooling PR.

Allowed scope:

```text
audit CLI
audit provider adapter
audit-only candidate descriptor support
identity-resolution logic
quota/cumulative-budget guard
audit state/resume/report logic
focused tests/docs
```

Fail if the PR changes:

```text
public product recommendation/intelligence semantics
active whitelist membership
production Scheduler policy
production Provider allowlist
production retry policy
Candidate/Formal/Lock/Production
Round 3 alert formulas
```

Provider calls during PR development and CI must equal 0.

## E. Dry-run 17-union contract — hard gate

Before real Provider calls, dry-run must prove:

```text
TARGET_ROWS = 17
ACTUAL_PROVIDER_CALLS = 0
DB_BUSINESS_WRITES = 0
CHECKPOINT_WRITES = 0
```

All 13 existing + four audit-only candidates must appear exactly once.

No duplicate canonical audit ID is allowed.

## F. Net-new Provider identity resolution — hard gate

For each of the four net-new candidates, identity status must be one of:

```text
EXACT_AND_UNAMBIGUOUS
IDENTITY_REVIEW_REQUIRED
PLAN_RESTRICTED
```

`EXACT_AND_UNAMBIGUOUS` requires Provider-observed:

```text
league ID
league name
country
season coverage
```

Fail if identity is accepted from:

```text
fuzzy match
guessed ID
first result without uniqueness check
country mismatch
season assumption
```

If identity is ambiguous, deeper calls for that candidate must be 0 after the ambiguous identity result.

## G. Provider call ledger integrity — hard gate

Every actual Provider call must have exactly one sanitized ledger record containing:

```text
competition/audit candidate ID
endpoint
captured_at
status_code
response_count
provider_call_index
league_call_index or equivalent
quota_remaining when available
error/blocker code when present
```

Required:

```text
LEDGER_RECORD_COUNT = ACTUAL_PROVIDER_CALL_COUNT
DUPLICATE_CALL_INDEX_COUNT = 0
UNLEDGERED_PROVIDER_CALL_COUNT = 0
```

No credentials, secret headers or raw payload bodies may enter the ledger.

## H. Provider budget and reserve — hard gate

Binding limits:

```text
ROUND2_AUDIT_DAILY_HARD_CAP = 80
ROUND2_AUDIT_CUMULATIVE_HARD_CAP = 200
ROUND2_MIN_PROVIDER_DAILY_REMAINING = 20
REQUEST_INTERVAL_SECONDS_MIN = 10
AUTOMATIC_RETRY = false
```

Fail if any day exceeds 80 Round 2 audit calls or cumulative calls exceed 200.

Fail if a call is made after Provider daily remaining quota is observed at `<= 20`, except the call whose response first reveals that state.

A stricter repository/runtime reserve wins.

## I. Hard-stop behavior — hard gate

Required fail-closed statuses include existing repository stops such as:

```text
GLOBAL_PROVIDER_HARD_CAP_REACHED
LEAGUE_PROVIDER_HARD_CAP_REACHED
PLAN_DOES_NOT_COVER_SEASON
PROVIDER_HTTP_429
DAILY_QUOTA_EXHAUSTED
QUOTA_WARNING
ENDPOINT_NOT_AUTHORIZED
PROVIDER_RESPONSE_SCHEMA_UNSAFE
PROVIDER_KEY_INVALID
PROVIDER_PAYLOAD_ERROR
```

Tests must prove:

- no automatic retry after a stop;
- no later endpoint calls for a stopped league when fail-fast applies;
- stop evidence is preserved;
- resume does not erase prior calls or reset cumulative count.

## J. Day-0 evidence-only baseline

Day-0 first pass uses evidence-only semantics.

Expected endpoint set remains:

```text
leagues
fixtures
odds
```

The existing planned evidence-only contract is four calls per competition when all calls are applicable.

Required:

```text
DAY0_TARGET_COUNT = 17
DAY0_THEORETICAL_MAX_PROVIDER_CALLS = 68
DAY0_ACTUAL_PROVIDER_CALLS <= 68 for first complete evidence-only pass
```

A lower actual count caused by identity/plan/quota/fixture blockers is valid.

Required 17-row Day-0 matrix fields:

```text
canonical audit ID
runtime_whitelist_member
identity_status
provider_league_id if observed
provider_name/provider_country
audit season
future-fixture status
results status
odds status
AH observed
OU observed
bookmaker count
line/price presence
quote timestamp presence
schema status
plan status
actual call count
quota remaining last seen
blockers
warnings
```

No row may claim capability not supported by real evidence.

## K. Deep capability probe

Deeper probes are permitted only for rows satisfying:

```text
identity exact
plan not blocked
fixture evidence available
no active hard stop
```

Allowed endpoints only:

```text
leagues
fixtures
odds
lineups
injuries
statistics
```

Required evidence where probed:

```text
statistics availability
lineup availability
injury availability
bookmaker depth
AH/OU presence
schema safety
```

Do not invent squad-value Provider coverage; current audit squad-value capability remains local/non-Provider unless a separately authorized source exists.

## L. Bookmaker and AH/OU truth

Existing minimum bookmaker-depth contract, where used by the existing audit implementation, must remain unweakened.

Required audit distinction:

```text
AH_PRESENT
OU_PRESENT
BOTH_PRESENT
MARKET_MISSING
LINE_OR_PRICE_MISSING
BOOKMAKER_DEPTH_INSUFFICIENT
```

Do not treat one bookmaker or one market as full market completeness when the existing contract requires more.

## M. 14-day observation window — hard gate

Record exact:

```text
ROUND2_OBSERVATION_START_UTC
ROUND2_OBSERVATION_END_UTC = START + 14 calendar days
```

Do not mark R2-B complete before the end timestamp.

Temporal observation must use existing persisted W2 captures/read models and already-authorized production collection. Round 2 must not create a new persistent Provider polling scheduler for the four audit-only candidates.

Required:

```text
NEW_PERSISTENT_COLLECTION_JOBS = 0
PRODUCTION_SCHEDULER_COMPETITION_DIFF = EMPTY
```

For competitions without enough real temporal evidence, record:

```text
TEMPORAL_EVIDENCE_INSUFFICIENT
```

Do not fabricate or backfill observations solely to pass readiness.

## N. Descriptive distribution evidence for Round 3

For each league × market with real temporal samples, report available descriptive evidence including:

```text
sample count
fixture count
observation timestamp count
freshness distribution
overround descriptive distribution where computable
line-movement descriptive distribution
bookmaker depth/confirmation distribution
missingness/error rates
```

No Round 3 threshold may be frozen in Round 2.

Hard guards:

```text
HIGH_OVERROUND_AS_VALUE = FORBIDDEN
HIGH_OVERROUND_AS_INFORMATION = FORBIDDEN
OPPORTUNITY_SCORE = FORBIDDEN
```

If sample size is too small for a percentile, output insufficient evidence instead of a fake percentile.

## O. Final 17-row capability matrix — hard gate

Exactly 17 unique rows are required.

Each row must contain at least:

```text
canonical audit ID
current runtime membership
identity result
plan result
fixtures/results coverage
AH/OU coverage
bookmaker depth
lineup/injury/statistics capability
14-day temporal evidence status
Provider/schema incidents
call cost
blockers/warnings
audit outcome
current capability state if applicable
recommended future capability state
promotion_authorized = false
```

Allowed audit outcomes include:

```text
CAPABILITY_CONFIRMED
CAPABILITY_PARTIAL
IDENTITY_REVIEW_REQUIRED
PLAN_RESTRICTED
TEMPORAL_EVIDENCE_INSUFFICIENT
SCHEMA_UNSAFE
PROVIDER_QUOTA_BLOCKED
DEGRADED
```

Existing product capability state vocabulary remains:

```text
REGISTERED
COVERAGE_MONITORING
MARKET_INTELLIGENCE_READY
MODEL_DIAGNOSTICS_READY
DEGRADED
```

For the four net-new rows:

```text
current_runtime_state = AUDIT_CANDIDATE_ONLY
promotion_authorized = false
```

## P. No automatic promotion — hard gate

After Round 2:

```text
ACTIVE_WHITELIST = 13_UNCHANGED
NEW_ENABLED_LEAGUES = 0
NEW_SCHEDULED_LEAGUES = 0
NEW_DAYVIEW_LEAGUES = 0
```

No audit result may directly mutate runtime enablement.

A separate future owner authorization is required for any promotion/enablement.

## Q. Product semantic invariants

Must remain true:

```text
PRODUCT = W2 Football Intelligence
PRODUCT_SEMANTICS = INTELLIGENCE_FIRST
MODEL_MARKET_DIVERGENCE != MARKET_OPPORTUNITY
RecommendationDecisionV4 = DIAGNOSTIC_INPUT_NOT_PRODUCT_AUTHORITY
BETTING_EDGE_CLAIM = FORBIDDEN
```

Round 2 provider evidence must not be translated into betting recommendations, value opportunities or positive-EV claims.

## R. Runtime/safety invariants

Required final evidence:

```text
PROVIDER_POLICY_DIFF = EMPTY for production paths
PROVIDER_ALLOWLIST_DIFF = EMPTY for production paths
SCHEDULER_POLICY_DIFF = EMPTY for production paths
NEW_PERSISTENT_COLLECTION_JOBS = 0
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
H_RESULT_ACCESS = PERMANENTLY_CLOSED
ROUND_3 = NOT_STARTED
```

Audit-only CLI endpoint authorization may be extended only as expressly allowed in `ROUND_2_CODEX_EXECUTION.md`; it must not change the production Provider allowlist.

## S. Evidence hygiene

Forbidden in Git/context/PR/artifacts:

```text
API keys
auth headers
raw secret-bearing headers
raw Provider payload dumps
private DB dumps
credentials
```

Sanitized evidence may include IDs, names, timestamps, counts, status codes, market coverage summaries and hash/lineage data.

Secret scan must pass.

## T. Round 2 completion receipt

Required final receipt fields:

```text
ROUND2_INITIAL_MAIN_SHA
ROUND2_EXECUTION_BASE_SHA
AUDIT_TOOLING_PR_NUMBER
AUDIT_TOOLING_FINAL_HEAD_SHA
AUDIT_TOOLING_CI_RESULT
ACTIVE_WHITELIST_BEFORE
ACTIVE_WHITELIST_AFTER
ACTIVE_WHITELIST_IDENTITY_DIFF
AUDIT_UNION_COUNT
NET_NEW_AUDIT_ONLY_COUNT
DAY0_START_UTC
ROUND2_OBSERVATION_START_UTC
ROUND2_OBSERVATION_END_UTC
DAY0_PLANNED_PROVIDER_CALLS
DAY0_ACTUAL_PROVIDER_CALLS
ROUND2_CUMULATIVE_PROVIDER_CALLS
ROUND2_DAILY_MAX_OBSERVED
MIN_QUOTA_REMAINING_OBSERVED
STOP_EVENTS
DAY0_17_ROW_MATRIX
FINAL_17_ROW_CAPABILITY_MATRIX
TEMPORAL_DISTRIBUTION_EVIDENCE_SUMMARY
PROVIDER_POLICY_DIFF
PROVIDER_ALLOWLIST_DIFF
SCHEDULER_POLICY_DIFF
NEW_PERSISTENT_COLLECTION_JOBS
NEW_ENABLED_LEAGUES
NEW_SCHEDULED_LEAGUES
CANDIDATE
FORMAL
LOCK
PRODUCTION
ROUND_3
```

Expected final state:

```text
ROUND_2 = PASS
ACTIVE_WHITELIST = 13_UNCHANGED
AUDIT_UNION = 17_COMPLETE_WITH_TRUTHFUL_OUTCOMES
NET_NEW_AUDIT_CANDIDATES = 4_NOT_ENABLED
ROUND_3 = NOT_STARTED
NEXT = AWAIT_OWNER_POST_R2_CAPABILITY_DECISION
```

After PASS, stop. Do not start Round 3 or any league enablement automatically.