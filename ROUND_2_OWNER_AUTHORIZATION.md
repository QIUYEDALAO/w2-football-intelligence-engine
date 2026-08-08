# W2 MI Round 2 — Owner Authorization

This file is the explicit owner authorization for Round 2. It is maintained directly on `context/current` without PR/CI/deployment.

## Binding authorization

```text
OWNER_AUTHORIZATION_ID = W2_MI_R2_PROVIDER_CAPABILITY_AUDIT_20260808
OWNER_DECISION = APPROVED
PRODUCT = W2 Football Intelligence
PROGRAM = W2_FOOTBALL_MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
TASK = W2_MI_R2_FIRST_DIVISION_PROVIDER_CAPABILITY_AUDIT
ROUND_1 = PASS
ROUND_2 = AUTHORIZED_IN_PROGRESS
ROUND_3 = NOT_STARTED
```

The owner authorizes Codex to execute the bounded Round 2 capability audit described in `ROUND_2_CODEX_EXECUTION.md` and to continue bounded remediation until the corresponding phase acceptance criteria pass.

## Audit universe

Round 2 audits the union:

```text
EXISTING_ACTIVE_WHITELIST = 13
NET_NEW_AUDIT_CANDIDATES = 4
TARGET_AUDIT_UNION = 17
```

Existing 13 identities:

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

Four net-new **audit-only** candidates:

```text
belgian_pro_league       # Belgian Pro League
 turkish_super_lig       # Turkish Super Lig
 greek_super_league      # Greek Super League
 scottish_premiership    # Scottish Premiership
```

Whitespace in the display list above is not part of canonical IDs. Canonical candidate IDs are exactly:

```text
belgian_pro_league
turkish_super_lig
greek_super_league
scottish_premiership
```

## Critical whitelist boundary

The four net-new competitions are **AUDIT_CANDIDATE_ONLY**.

```text
ACTIVE_WHITELIST_BEFORE = 13
ACTIVE_WHITELIST_DURING_R2 = 13
ACTIVE_WHITELIST_AFTER_R2 = 13
NET_NEW_ACTIVE_WHITELIST_ADDITIONS = 0
NET_NEW_SCHEDULER_ADDITIONS = 0
NET_NEW_DAYVIEW_ADDITIONS = 0
```

Do not place the four net-new audit candidates into the runtime competition whitelist merely to make the existing registry-based audit CLI accept them.

Audit-candidate metadata must live outside the runtime whitelist discovery path, for example under an audit-only config namespace such as:

```text
config/audit_candidates/
```

or an equivalent clearly non-runtime authority proven not to affect CompetitionRegistry, future-refresh, Scheduler, DayView or analysis-card selection.

## Provider-call authorization

The owner explicitly authorizes **controlled API-Football calls only through the Round 2 audit path** after the audit-tooling preflight passes.

```text
ALLOW_CONTROLLED_PROVIDER_AUDIT_CALLS = true
ALLOW_REAL_PROVIDER_AUDIT_FLAG = true
ALLOW_APPROVED_PROVIDER_CALLS_FLAG = true
ALLOW_PRODUCTION_REFRESH_CALLS_FOR_R2 = false
ALLOW_SCHEDULER_EXPANSION_FOR_R2 = false
ALLOW_AUTOMATIC_RETRY = false
```

The authorization does not allow secrets to be copied into Git, logs, chat, PR bodies, artifacts or context files.

## Provider-call budgets

Existing evidence-only audit semantics are retained as the Day-0 first probe:

```text
EVIDENCE_ONLY_ENDPOINTS = leagues,fixtures,odds
EVIDENCE_ONLY_PLANNED_CALLS_PER_COMPETITION = 4
DAY0_TARGET_COMPETITIONS = 17
DAY0_THEORETICAL_MAX_CALLS = 68
```

Round 2 hard budgets:

```text
ROUND2_AUDIT_DAILY_HARD_CAP = 80
ROUND2_AUDIT_CUMULATIVE_HARD_CAP = 200
ROUND2_MIN_PROVIDER_DAILY_REMAINING = 20
ROUND2_REQUEST_INTERVAL_SECONDS_MIN = 10
STOP_ON_FIRST_QUOTA_WARNING = true
AUTOMATIC_RETRY = false
```

The 200-call cumulative cap covers the Day-0 evidence-only baseline plus bounded deeper capability probes. It does not authorize continuous polling.

If the Provider reports remaining daily quota at or below 20, or any stricter existing repository/production reserve would be violated, stop Provider calls for that day and resume later. Never consume reserved capacity to finish an audit batch.

Existing hard stops remain binding, including HTTP 429, quota exhaustion/warning, plan restriction, unauthorized endpoint, unsafe schema, invalid key, payload error, per-league cap and global cap.

## Four net-new identity resolution

Do not guess API-Football league IDs.

For net-new audit candidates, the audit tooling may perform deterministic Provider-backed identity resolution using the approved `leagues` endpoint.

Required identity evidence before any deeper call:

```text
provider = api_football
provider_league_id = uniquely observed
provider_league_name = observed
provider_country = observed
provider_season = observed/current audit season
identity_match = EXACT_AND_UNAMBIGUOUS
```

No fuzzy name match. No manual guessed ID. Multiple plausible matches, no exact match or season ambiguity -> `IDENTITY_REVIEW_REQUIRED`, and deeper calls for that candidate stop.

## Round 2 phases

```text
R2_A = AUDIT_FOUNDATION_AND_DAY0_BASELINE
R2_B = FOURTEEN_DAY_READ_ONLY_OBSERVATION
R2_C = FINAL_CAPABILITY_DECISION
```

The 14-day window starts at the timestamp of the first successful Day-0 baseline batch and must be recorded exactly.

Round 2 does not require every competition to become ready. `INSUFFICIENT_EVIDENCE`, `DEGRADED`, `IDENTITY_REVIEW_REQUIRED`, plan restriction and unavailable coverage are valid audited outcomes.

## Bounded remediation authorization

For failures inside the approved Round 2 audit scope:

```text
FAIL_CLOSED = DO_NOT_ADVANCE_PAST_FAILED_GATE
FAIL_CLOSED != ABANDON_ROUND_2
```

Codex may make bounded fixes to the same Round 2 audit-tooling PR, rerun local tests/PR Fast/required CI, and retry an audit batch within the hard budgets without requesting another owner authorization.

A new owner authorization is required if a proposed fix would:

```text
change active whitelist membership
change production Provider allowlist/policy
change production Scheduler cadence/competition list/retry policy
add persistent collection for the four net-new candidates
start Round 3
freeze market-alert thresholds
create opportunity/value/edge/recommendation semantics
open Candidate/Formal/Lock/Production
reopen Phase 0.5/H
exceed Provider call budgets
```

## Permanent product and safety guards

```text
MODEL_MARKET_DIVERGENCE != MARKET_OPPORTUNITY
BETTING_EDGE_CLAIM = FORBIDDEN
RecommendationDecisionV4 = DIAGNOSTIC_INPUT_NOT_PRODUCT_AUTHORITY
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
REAL_MONEY = NOT_AUTHORIZED
ROUND_3 = NOT_STARTED
```

## Completion

Round 2 can be closed only when `ROUND_2_ACCEPTANCE_CRITERIA.md` is satisfied and a final 17-row capability matrix truthfully records all ready, partial, blocked and insufficient-evidence outcomes.

No competition is automatically promoted, enabled, scheduled or added to the active whitelist by Round 2 acceptance.