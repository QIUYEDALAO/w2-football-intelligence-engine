# W2 Current Task Checklist

Current mutable task authority is `origin/context/current`.

## Program status

```text
PROGRAM = W2_FOOTBALL_MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
PRODUCT = W2 Football Intelligence
ROUND_1 = PASS
ACTIVE_TASK = W2_MI_R2_FIRST_DIVISION_PROVIDER_CAPABILITY_AUDIT
ACTIVE_PHASE = R2_B_FOURTEEN_DAY_READ_ONLY_OBSERVATION
ROUND_2 = AUTHORIZED_IN_PROGRESS
ROUND_3 = NOT_STARTED
```

Round 1 final evidence: `ROUND_1_FINAL_RECEIPT.md`.

Round 2 owner authorization: `ROUND_2_OWNER_AUTHORIZATION.md`.

Round 2 execution authority: `ROUND_2_CODEX_EXECUTION.md`.

Round 2 acceptance authority: `ROUND_2_ACCEPTANCE_CRITERIA.md`.

Round 2 acceptance evidence map: `ROUND_2_ACCEPTANCE_EVIDENCE_INDEX.md`.

R2-A/Day-0 evidence: `ROUND_2_DAY0_RECEIPT.md`.

Permanent guard:

```text
MODEL_MARKET_DIVERGENCE != MARKET_OPPORTUNITY
```

---

## MI-00 — Phase 0.5

```text
STATUS = DONE
FINAL_VERDICT = NO_EDGE
H_RESULT_ACCESS = PERMANENTLY_CLOSED
```

Do not reopen or retune the failed hypothesis.

---

## MI-R1 — Product semantics and status reframe

```text
STATUS = PASS
PR = 493
FINAL_HEAD = 602665885a2cbaf87e5f6c6ceb8c73926244e471
MERGE_SHA = f7860813646ce9718931dff331c09ce2fe7a71ba
PRODUCT_SEMANTICS = INTELLIGENCE_FIRST
ACTIVE_WHITELIST = 13_UNCHANGED
```

Do not resume PR #493. Round 1 continuation authority is historical only.

---

## MI-R2 — 17-competition Provider capability audit

```text
STATUS = AUTHORIZED_IN_PROGRESS
TASK = W2_MI_R2_FIRST_DIVISION_PROVIDER_CAPABILITY_AUDIT
MODE = CONTROLLED_READ_ONLY_PROVIDER_CAPABILITY_AUDIT
DURATION = 14_DAYS
AUDIT_UNION_COUNT = 17
ACTIVE_WHITELIST_COUNT = 13
NET_NEW_AUDIT_ONLY_COUNT = 4
```

### R2.0 Audit universe hard boundary

Existing runtime whitelist — preserve exactly:

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

Audit-only candidates:

```text
belgian_pro_league
turkish_super_lig
greek_super_league
scottish_premiership
```

Required throughout Round 2:

```text
ACTIVE_WHITELIST = 13_UNCHANGED
NET_NEW_RUNTIME_STATE = AUDIT_CANDIDATE_ONLY
NET_NEW_SCHEDULER_ADDITIONS = 0
NET_NEW_DAYVIEW_ADDITIONS = 0
```

### R2-A — Audit foundation and Day-0 baseline

```text
STATUS = COMPLETE_WITH_TRUTHFUL_PLAN_RESTRICTIONS
```

Checklist:

- [x] Record exact current `origin/main` SHA; initial Round 2 main was `f7860813646ce9718931dff331c09ce2fe7a71ba`.
- [x] Audit current competition registry, Provider audit CLI, Provider hard stops, quota code and production Scheduler/Provider authorities.
- [x] Create one bounded Round 2 audit-tooling PR.
- [x] Add a non-runtime audit-only candidate descriptor authority outside runtime whitelist discovery.
- [x] Support the 13 registered + 4 audit-only union without adding the four to CompetitionRegistry runtime membership.
- [x] Implement deterministic Provider-backed identity resolution for the four net-new candidates.
- [x] No fuzzy identity, no guessed Provider league IDs, no first-result-wins.
- [x] Preserve existing `enablement`, `coverage-inventory`, `evidence-only` audit modes.
- [x] Preserve evidence-only Day-0 endpoint set: leagues/fixtures/odds.
- [x] Add/confirm cumulative Round 2 call ledger surviving multi-day resume.
- [x] Add hard quota reserve `provider daily remaining > 20` to continue.
- [x] Daily audit cap = 80; cumulative Round 2 cap = 200; request interval >= 10 seconds; automatic retry = false.
- [x] Prove audit candidate runtime reachability = 0.
- [x] Dry-run all 17: 17 unique rows, Provider calls 0, DB business writes 0.
- [x] All focused and repository-required tests pass before real Provider calls.
- [x] Provider calls during PR development/CI = 0.
- [x] Merge/accept audit tooling under normal repository governance.
- [x] Execute Day-0 `evidence-only` Provider baseline with explicit audit authorization.
- [x] First complete Day-0 theoretical max = 68 calls; actual = 17 after per-row plan hard stops.
- [x] Stop/resume on quota/plan/schema/identity blockers rather than increasing limits.
- [x] Produce sanitized Day-0 17-row capability matrix.
- [x] Record exact `ROUND2_OBSERVATION_START_UTC` at first Day-0 evidence capture.

### R2-A deeper capability probes

- [x] Deep-probe only exact identity + plan-covered + fixture-available rows; zero rows were eligible.
- [x] Allowed endpoints only: leagues, fixtures, odds, lineups, injuries, statistics; no deeper calls were made.
- [x] Do not invent Provider squad-value coverage.
- [x] Preserve existing bookmaker-depth contract; do not weaken minimum depth.
- [x] Round 2 cumulative Provider calls remain <= 200; current cumulative count = 17.
- [x] Every actual call has exactly one sanitized ledger record.
- [x] No automatic retry after HTTP 429/quota warning/plan restriction/schema failure/payload error.

### R2-B — Fourteen-day read-only observation

```text
STATUS = ACTIVE
WINDOW_START = 2026-08-08T01:53:55.509495+00:00
WINDOW_END = 2026-08-22T01:53:55.509495+00:00
```

Checklist:

- [ ] Do not create a new persistent polling scheduler for audit-only candidates.
- [ ] Use existing persisted W2 captures/read models and already-authorized production collection.
- [ ] Inspect real freshness, AH/OU, bookmaker depth/agreement, overround, movement, missingness, Provider/schema incidents and call cost.
- [ ] If evidence is absent, record `TEMPORAL_EVIDENCE_INSUFFICIENT`; do not create data to pass.
- [ ] Do not finish R2-B before exact observation end timestamp.
- [ ] Build league × market descriptive evidence for Round 3 planning where samples exist.
- [ ] Do not freeze Round 3 alert thresholds.
- [ ] `HIGH_OVERROUND != HIGH_VALUE` and `HIGH_OVERROUND != HIGH_INFORMATION` remain hard guards.

### R2-C — Final capability decision

```text
STATUS = BLOCKED_UNTIL_R2_B_WINDOW_COMPLETE
```

Checklist:

- [ ] Produce exactly 17 unique final rows.
- [ ] Record exact identity/plan/fixtures/results/AH/OU/bookmaker/lineup/injury/statistics/temporal-evidence/schema/call-cost status.
- [ ] Preserve valid blocked outcomes: identity review, plan restricted, insufficient temporal evidence, schema unsafe, quota blocked, degraded.
- [ ] Use product capability vocabulary only where supported: REGISTERED, COVERAGE_MONITORING, MARKET_INTELLIGENCE_READY, MODEL_DIAGNOSTICS_READY, DEGRADED.
- [ ] Four net-new rows remain `current_runtime_state = AUDIT_CANDIDATE_ONLY`.
- [ ] `promotion_authorized = false` for every row.
- [ ] Active whitelist remains 13.
- [ ] New enabled/scheduled/DayView leagues = 0.
- [ ] Provider production policy/allowlist/Scheduler production policy diffs = EMPTY.
- [ ] Candidate/Formal/Lock/Production remain OFF.
- [ ] Round 3 remains NOT_STARTED.
- [ ] Produce final Round 2 receipt required by `ROUND_2_ACCEPTANCE_CRITERIA.md`.

### Round 2 continuation rule

```text
FAIL_CLOSED = DO_NOT_ADVANCE_PAST_FAILED_GATE
FAIL_CLOSED != ABANDON_ROUND_2
```

Bounded audit-tooling remediation and audit-batch resume within the authorized budgets do not require another owner authorization.

Do not bypass blockers by raising limits, enabling retries, widening production allowlists, guessing identities, changing Scheduler or adding leagues.

---

## MI-R3 — Market Radar and Model Lab

```text
STATUS = NOT_STARTED_BLOCKED_UNTIL_ROUND_2_COMPLETE_AND_OWNER_DECISION
OVERROUND_PERCENTILE = REQUIRED_ALERT_COVARIATE
```

Round 3 is not authorized by Round 2 acceptance.

---

## Permanent stop lines

```text
BETTING_EDGE_CLAIM = FORBIDDEN
MODEL_DIVERGENCE_AS_OPPORTUNITY = FORBIDDEN
SIGNAL_LEDGER_FOR_EXECUTION = NOT_AUTHORIZED
PORTFOLIO = NOT_AUTHORIZED
RISK_KELLY = NOT_AUTHORIZED
TWO_LEG_PARLAY = NOT_AUTHORIZED
REAL_MONEY = NOT_AUTHORIZED

CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
```
