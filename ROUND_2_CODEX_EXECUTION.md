# W2 MI Round 2 — Codex Execution Authority

This file is the binding execution authority for:

```text
TASK = W2_MI_R2_FIRST_DIVISION_PROVIDER_CAPABILITY_AUDIT
PRODUCT = W2 Football Intelligence
PROGRAM = W2_FOOTBALL_MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
OWNER_AUTHORIZATION = ROUND_2_OWNER_AUTHORIZATION.md
ROUND_1 = PASS
ROUND_2 = AUTHORIZED_IN_PROGRESS
ROUND_3 = NOT_STARTED
```

## 0. Mission

Determine, with code/runtime/provider evidence, what W2 can **reliably observe** across the 17-competition audit universe.

Round 2 is a capability audit, not a league-expansion release and not a betting-edge experiment.

Questions to answer per competition:

1. Is Provider identity exact and unambiguous?
2. Is the current/audit season actually covered by the account plan?
3. Are future fixtures and finished results observable?
4. Are AH and OU markets observable with truthful line/price/timestamp evidence?
5. Is bookmaker depth/confirmation usable or thin/noisy?
6. Are lineups, injuries and fixture statistics/xG-capable inputs available where probed?
7. Are Provider schemas stable enough for W2 ingestion?
8. What real freshness/coverage/overround/movement evidence already exists during the 14-day window?
9. What is the observed call cost and blocker profile?
10. Which product capability state is supportable without guessing or auto-promotion?

## 1. Source authority and starting point

Before editing or calling Provider:

```bash
git fetch origin main context/current --prune
```

Initial audited main at Round 2 authorization:

```text
ROUND_2_INITIAL_MAIN_SHA = f7860813646ce9718931dff331c09ce2fe7a71ba
```

Resolve current `origin/main` again at execution time and record the exact SHA. If main has advanced, perform a bounded compatibility review; do not silently discard the Round 1 delivery baseline.

Read `origin/context/current` in this order:

1. `CURRENT_CONTEXT.md`
2. `CURRENT_STATE.yaml`
3. `CURRENT_PRODUCT_DESIGN.md`
4. `CURRENT_TASK_CHECKLIST.md`
5. `NEXT_ACTION.md`
6. `ROUND_2_OWNER_AUTHORIZATION.md`
7. `ROUND_2_CODEX_EXECUTION.md`
8. `ROUND_2_ACCEPTANCE_CRITERIA.md`
9. `ROUND_1_FINAL_RECEIPT.md`
10. `AI_PROJECT_CONTEXT.md`
11. `AI_QUANT_PROJECT_CONTEXT.md`
12. `AGENTS.md`
13. `QUANT_AGENTS.md`
14. `.github/copilot-instructions.md`

Use code/runtime/provider evidence as truth. Do not treat old PR descriptions, comments or archived status prose as current runtime truth.

## 2. Audit universe — binding

Existing active whitelist remains exactly 13:

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

Net-new audit-only candidates:

```text
belgian_pro_league
turkish_super_lig
greek_super_league
scottish_premiership
```

Audit union:

```text
13 EXISTING + 4 AUDIT_ONLY = 17
```

The four audit-only candidates must not become runtime whitelist entries merely to satisfy the current registry-based CLI.

## 3. R2-A — audit foundation PR

### 3.1 One bounded audit-tooling PR

Create one Round 2 audit-tooling PR from current trusted main.

Allowed change areas are limited to audit tooling/config/tests/docs required to support the 17-union audit, such as:

```text
scripts/run_w2_league_whitelist_audit.py
src/w2/competitions/league_whitelist_audit.py
src/w2/competitions/league_whitelist_provider_audit.py
new audit-only candidate descriptor loader/module
config/audit_candidates/*
focused tests for audit scope/identity/budget/resume/reporting
Round 2 sanitized report schema/docs
```

Do not change public API/Web product behavior in this PR unless a test-only import adjustment is unavoidable and proven non-runtime.

### 3.2 Audit-only candidate authority

Implement a candidate descriptor authority outside runtime whitelist discovery.

Recommended path:

```text
config/audit_candidates/round2_first_divisions.v1.json
```

The descriptor must include only audit metadata, for example:

```text
audit_candidate_id
display_name
country
provider
provider_query_name
provider_query_country
season_strategy
runtime_whitelist_member = false
scheduler_member = false
```

Do not hard-code guessed API-Football league IDs for the four net-new candidates.

The audit CLI must support the union of:

```text
registered existing competition entries
+
audit-only descriptors
```

without inserting audit-only candidates into `CompetitionRegistry` runtime membership.

### 3.3 Exact Provider identity resolution

For an audit-only descriptor, allow a `leagues` lookup sufficient to resolve Provider identity.

Required match contract:

```text
ONE_UNIQUE_MATCH
provider league ID observed from response
name compatible with descriptor
country exact/approved alias
season actually present
```

Forbidden:

```text
fuzzy nearest-name auto-selection
manual guessed league ID
first-result-wins
country mismatch acceptance
season assumption without evidence
```

Ambiguity -> `IDENTITY_REVIEW_REQUIRED` and stop deeper calls for that candidate.

### 3.4 Preserve existing audit modes

Do not break existing modes:

```text
enablement
coverage-inventory
evidence-only
```

Round 2 Day-0 must begin with `evidence-only` semantics.

Existing evidence-only endpoints remain:

```text
leagues
fixtures
odds
```

Existing evidence-only planned calls remain 4 per competition unless exact code evidence requires a smaller count. Do not increase the Day-0 endpoint set merely for convenience.

### 3.5 Shared quota safety

Add/confirm a Round 2 audit reserve guard:

```text
ROUND2_AUDIT_DAILY_HARD_CAP = 80
ROUND2_AUDIT_CUMULATIVE_HARD_CAP = 200
ROUND2_MIN_PROVIDER_DAILY_REMAINING = 20
REQUEST_INTERVAL_SECONDS >= 10
AUTOMATIC_RETRY = false
STOP_ON_FIRST_QUOTA_WARNING = true
```

A Provider response showing remaining daily quota `<= 20` must stop further Round 2 calls for that day.

If a stricter existing W2 quota/reserve rule applies, the stricter rule wins.

Cumulative call accounting must survive multi-day resume. Do not reset the cumulative budget merely by starting a new process.

Implement sanitized persistent Round 2 audit state outside the repository or in another explicitly non-secret/non-raw store. Do not persist credentials or raw provider payloads.

Required persistent audit metadata includes:

```text
audited competition
endpoint
captured_at
status code
response count
quota remaining when available
call index
blocker/error code
sanitized identity/market capability evidence
```

### 3.6 No retry or hidden extra calls

No automatic retry on HTTP errors, empty results, plan restriction or schema problems.

Every actual Provider request must increment the audit ledger exactly once before any subsequent request.

No fallback probing may silently exceed per-league/global/cumulative budgets.

### 3.7 R2-A local/CI acceptance before real calls

Before the first real Round 2 Provider call:

- all new audit-tool tests PASS;
- dry-run across all 17 returns 17 target rows and `actual_provider_calls=0`;
- existing 13 runtime whitelist identity set remains unchanged;
- audit-only descriptors are proven unreachable by runtime CompetitionRegistry/Scheduler/DayView;
- quota/reserve/cumulative-cap tests PASS;
- ambiguous identity tests fail closed;
- existing audit CLI regression tests remain green;
- repository lint/static/contract requirements pass.

Provider calls during PR development/CI must remain 0.

Use normal PR/CI governance. If the PR changes source under normal required checks, continue bounded remediation until the final audit-tooling head is accepted. Do not deploy product runtime solely to claim audit-tooling success.

If a secure secret-bearing execution environment requires the merged tooling to be present there, use the repository's approved secure operational path; do not copy the API key to a new location.

## 4. R2-A Day-0 controlled Provider baseline

Only after the audit foundation is accepted may Codex execute real audit calls.

### 4.1 Day-0 first pass

Run evidence-only baseline across the 17-union with explicit owner-approved flags.

Theoretical planned maximum:

```text
17 * 4 = 68 calls
```

Hard execution rules:

```text
actual calls <= 68 for the first complete Day-0 evidence-only pass
Round2 daily calls <= 80
Round2 cumulative calls <= 200
quota remaining > 20 to continue
no retry
```

If quota/plan/schema/identity stop conditions prevent finishing all 17 in one day, preserve evidence and resume later. Do not raise limits.

### 4.2 Day-0 outputs

Produce a sanitized 17-row matrix with at least:

```text
audit_candidate_id / competition_id
runtime_whitelist_member
identity_status
provider_league_id if uniquely observed
provider_name
provider_country
audit_season
league_endpoint_status
future_fixture_status
result_fixture_status
odds_endpoint_status
AH_observed
OU_observed
bookmaker_count_observed
line_and_price_observed
quote_timestamp_observed
provider_schema_status
plan_status
actual_provider_calls
quota_remaining_last_seen
blockers
warnings
```

Net-new candidate rows remain `AUDIT_CANDIDATE_ONLY` regardless of Provider success.

## 5. R2-A deeper capability probes

After Day-0 identity/fixture evidence is available, run deeper probes only where justified.

Eligibility for deeper probe:

```text
identity = EXACT_AND_UNAMBIGUOUS
plan coverage not blocked
fixture evidence available
no hard stop active
```

Use the existing controlled audit endpoints only:

```text
leagues
fixtures
odds
lineups
injuries
statistics
```

Do not add unrelated endpoints.

Deep capability evidence may include:

```text
fixture statistics availability
lineup availability
injury availability
AH/OU bookmaker depth
future/results availability
schema safety
```

Do not call `squad_value` Provider endpoints; the current audit contract treats squad value as non-Provider/local-source capability.

The theoretical full audit is 7 calls per competition, but Round 2 may not simply execute `17 * 7` if it would violate daily/cumulative/reserve guards. Split/resume and skip ineligible leagues.

Total Round 2 audit calls across Day-0 + deeper probes must remain `<= 200`.

## 6. R2-B — 14-day read-only observation window

The observation window begins at the timestamp of the first successful Day-0 baseline capture:

```text
ROUND2_OBSERVATION_START_UTC = exact timestamp
ROUND2_OBSERVATION_END_UTC = START + 14 calendar days
```

Round 2 does **not** authorize a new persistent Provider polling scheduler for the four audit-only candidates.

Use existing W2 persisted runtime captures/read models and already-authorized production collection as the temporal evidence source.

Read-only observation may inspect:

```text
endpoint captures
market observations
AH/OU lines and prices
captured_at/freshness
bookmaker agreement/depth
overround
line movement
fixture identity
lineup availability
Provider errors/schema incidents
existing collection cadence/call cost
```

Do not write business facts merely to improve coverage.

If a competition has insufficient existing temporal captures during the 14-day window, record `TEMPORAL_EVIDENCE_INSUFFICIENT`. That is a valid Round 2 result and blocks readiness claims.

### 6.1 Distribution outputs for Round 3 planning

Produce descriptive evidence only; do not freeze alert thresholds.

For each league × market with enough observations, report available distributions such as:

```text
sample count
fixture count
observation-time count
freshness distribution
overround count/min/p25/p50/p75/p90/p95/max when computable
line movement descriptive distribution
bookmaker confirmation/depth distribution
missingness/schema-error rates
```

Reuse existing checkpoint/time-to-kickoff identities if already authoritative. If no authoritative buckets exist, retain continuous time-to-kickoff evidence or descriptive grouping solely for analysis; do not turn an ad hoc bucket into a Round 3 product threshold.

Permanent guard:

```text
HIGH_OVERROUND != HIGH_VALUE
HIGH_OVERROUND != HIGH_INFORMATION
```

## 7. R2-C — final capability decision

At the end of the 14-day window, build one 17-row final capability matrix.

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

Existing product capability recommendations may use only:

```text
REGISTERED
COVERAGE_MONITORING
MARKET_INTELLIGENCE_READY
MODEL_DIAGNOSTICS_READY
DEGRADED
```

For the four net-new audit-only candidates, do not output `REGISTERED` as current state; record `AUDIT_CANDIDATE_ONLY` plus a recommended future capability decision.

No product capability recommendation is an enablement action.

### 7.1 No automatic promotion

Round 2 must never directly:

```text
change enabled false -> true
add competition to active whitelist
add competition to future-refresh policy
add competition to Scheduler
add competition to DayView
open recommendation gates
```

A future enablement/promotion requires a separate owner-authorized task after Round 2.

## 8. Evidence standard

Only accept:

```text
code
runtime config
DB/schema/migrations when relevant
sanitized Provider response-derived evidence
Provider call ledger
real persisted captures
real API/read-model evidence
tests
CI logs/results
```

Do not accept PR description or code comment self-claims as proof.

Do not commit raw Provider payloads, credentials, headers containing secret material, private database contents or other sensitive data.

## 9. Fail-closed continuation semantics

For an in-scope failure:

```text
FAIL_CLOSED = STOP_AT_FAILED_GATE
FAIL_CLOSED != ABANDON_ROUND_2
```

Codex may diagnose and minimally repair the Round 2 audit tooling inside the same audit-tooling PR and continue validation without asking for owner authorization again.

Provider audit batches may resume later under the same authorization if stopped by quota/plan/time-window constraints, provided all budgets and stop lines remain intact.

Do not bypass a blocker by widening allowlists, raising budgets, adding retries, guessing identities or enabling leagues.

## 10. Final receipt

Round 2 final receipt must include:

```text
ROUND2_CODE_BASELINE_SHA
AUDIT_TOOLING_PR_NUMBER
AUDIT_TOOLING_FINAL_HEAD_SHA
CI/PR_FAST/FULL_QUALITY_RESULTS as applicable
ACTIVE_WHITELIST_BEFORE
ACTIVE_WHITELIST_AFTER
ACTIVE_WHITELIST_IDENTITY_DIFF
AUDIT_UNION_COUNT
NET_NEW_AUDIT_ONLY_COUNT
DAY0_START_UTC
OBSERVATION_END_UTC
DAY0_PLANNED_PROVIDER_CALLS
DAY0_ACTUAL_PROVIDER_CALLS
ROUND2_CUMULATIVE_PROVIDER_CALLS
ROUND2_DAILY_MAX_OBSERVED
MIN_QUOTA_REMAINING_OBSERVED
STOP_EVENTS
17_ROW_CAPABILITY_MATRIX
TEMPORAL_DISTRIBUTION_EVIDENCE_SUMMARY
PROVIDER_POLICY_DIFF
PROVIDER_ALLOWLIST_DIFF
SCHEDULER_POLICY_DIFF
NEW_PERSISTENT_COLLECTION_JOBS
CANDIDATE
FORMAL
LOCK
PRODUCTION
ROUND_3
```

Round 2 can be marked PASS only under `ROUND_2_ACCEPTANCE_CRITERIA.md`.

After Round 2 PASS, stop. Do not begin Round 3 automatically.