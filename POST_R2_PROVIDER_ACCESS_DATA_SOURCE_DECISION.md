# W2 Post-R2 — Provider Access Root Cause & Data-Source Decision

```text
TASK = W2_MI_POST_R2_PROVIDER_ACCESS_AND_DATA_SOURCE_DECISION
OWNER_DECISION = APPROVED_EXECUTE_NOW
ROUND_1 = PASS
ROUND_2 = PASS_WITH_TERMINAL_PROVIDER_PLAN_RESTRICTION
ROUND_3 = NOT_STARTED
```

## Goal

Resolve the blocking question before Round 3: why did all 17 Round-2 rows stop at `PLAN_RESTRICTED`, and what data-source path should W2 use for reliable fixture/odds/lineup/statistics market intelligence?

This is a root-cause and architecture/source decision gate. It is not authorization to buy a plan, switch Provider, expand Scheduler coverage, enable leagues, or start Round 3.

## Evidence first

Use only code, config, tests, sanitized Round-2 Provider evidence, exact runtime/account metadata available without exposing secrets, and current official Provider documentation/pricing/licensing sources.

Read first:

```text
CURRENT_STATE.yaml
NEXT_ACTION.md
ROUND_2_FINAL_RECEIPT.md
ROUND_2_FINAL_CAPABILITY_MATRIX.json
ROUND_2_DAY0_RECEIPT.md
src/w2/competitions/league_whitelist_provider_audit.py
scripts/run_w2_league_whitelist_audit.py
config/audit_candidates/round2_first_divisions.v1.json
REPOSITORY_HYGIENE_POLICY.md
```

## Phase A — classify the 17/17 PLAN_RESTRICTED root cause

Determine which classification is actually supported:

```text
PLAN_ENTITLEMENT_RESTRICTION
SEASON_PARAMETER_OR_SEASON_MAPPING_DEFECT
PROVIDER_COVERAGE_GAP
ACCOUNT_OR_KEY_ENTITLEMENT_MISMATCH
REQUEST_SHAPE_OR_CLIENT_DEFECT
MULTIPLE_CAUSES
UNRESOLVED
```

Required checks:

1. inspect the exact sanitized Provider error classification and how `_provider_payload_error` / plan-restriction handling is triggered;
2. inspect the configured/audit season strategy for the 13 existing + 4 audit-only candidates;
3. verify API-Football's current season semantics and plan/endpoint entitlement from official current documentation/account evidence — do not infer from old comments or archived PR prose;
4. distinguish calendar-year leagues from cross-year European leagues;
5. verify whether querying `season=2026` is correct for each control case or whether the code is turning a season-mapping issue into a plan-restriction conclusion;
6. verify whether the same account/key has any documented accessible season/league scope.

### Controlled diagnostic Provider calls

If code + retained Round-2 evidence + official docs are insufficient to distinguish the cause, controlled read-only diagnostic calls are authorized with these hard limits:

```text
MAX_NEW_DIAGNOSTIC_PROVIDER_CALLS = 8
AUTOMATIC_RETRY = false
BUSINESS_DB_WRITES = 0
CHECKPOINT_WRITES = 0
PRODUCTION_SCHEDULER_CHANGES = 0
ACTIVE_WHITELIST_CHANGES = 0
```

Use the minimum number of control requests needed. Prefer `/leagues` identity/season/access checks on a small representative set (at least one calendar-year league and one cross-year European league). Do not repeat the 17-league batch.

Do not call fixtures/odds/lineups/injuries/statistics unless a preceding diagnostic proves the plan/access gate is open and that extra call is strictly necessary to isolate the root cause. Every actual call must be sanitized and ledgered. No secret-bearing headers/payload dumps.

## Phase B — conditional bounded internal fix

If and only if the evidence proves the blocker is an internal W2 season/request/configuration defect rather than external Provider entitlement, Codex is authorized to:

1. create one bounded fix PR from latest `origin/main`;
2. make the smallest correction to season/request/audit logic;
3. keep active whitelist exact 13 and four new leagues audit-only;
4. run focused/full required tests, PR Fast and required release-quality checks;
5. use only the remaining portion of the 8-call diagnostic budget for exact post-fix validation;
6. apply `REPOSITORY_HYGIENE_POLICY.md` before declaring the fix complete.

Do not change Provider plan, production Provider allowlist, production Scheduler cadence, league enablement, Candidate/Formal/Lock/Production or Round-3 logic.

If the blocker is external entitlement/coverage, do not create a fake code fix.

## Phase C — current data-source decision matrix

Using current official primary-source information, compare at minimum:

```text
OPTION_A = current API-Football account/plan path
OPTION_B = API-Football plan upgrade path if applicable
OPTION_C = alternate full football-data Provider
OPTION_D = dedicated odds/market Provider plus existing football Provider
OPTION_E = hybrid multi-source architecture
```

For each viable option record:

```text
fixture coverage for target 17
AH coverage
OU coverage
historical odds availability
pre-match odds timestamps / snapshots
bookmaker depth
lineups
injuries
statistics / xG-capable inputs
rate limits / quota model
required subscription tier / current price from official source
commercial/licensing restrictions relevant to W2
expected monthly recurring cost
implementation effort
identity/mapping migration cost
schema/normalization work
operational reliability risk
vendor-lock-in risk
whether it can support Market Radar evidence
whether it can support Model Diagnostics evidence
```

Do not treat marketing claims as proven capability. Separate `DOCUMENTED`, `VERIFIED_BY_CALL`, and `NOT_VERIFIED`.

## Decision output

Create/update durable context evidence:

```text
POST_R2_PROVIDER_ACCESS_ROOT_CAUSE.md
POST_R2_DATA_SOURCE_DECISION_MATRIX.md
```

The final result must contain:

```text
ROOT_CAUSE_CLASSIFICATION
ROOT_CAUSE_CONFIDENCE
NEW_DIAGNOSTIC_PROVIDER_CALLS
INTERNAL_FIX_REQUIRED
INTERNAL_FIX_PR if any
CURRENT_API_FOOTBALL_PATH_VIABLE
RECOMMENDED_PRIMARY_DATA_SOURCE_PATH
RECOMMENDED_FALLBACK_PATH
ESTIMATED_MONTHLY_DATA_COST
EXPECTED_ENGINEERING_EFFORT
BLOCKERS_REQUIRING_OWNER_SPEND_OR_ACCOUNT_CHANGE
ROUND_3_DATA_PREREQUISITES
```

Give one preferred recommendation and one fallback. Do not dump five equal options without a decision.

## Stop line

No purchase/subscription change, credential replacement, Provider cutover, production deployment, Scheduler expansion, league promotion, persistent collection expansion, or Round 3 implementation is authorized by this task.

Permanent guards remain:

```text
ACTIVE_WHITELIST = 13_UNCHANGED
AUDIT_ONLY_CANDIDATES = 4_NOT_ENABLED
MODEL_MARKET_DIVERGENCE != MARKET_OPPORTUNITY
BETTING_EDGE_CLAIM = FORBIDDEN
H_RESULT_ACCESS = PERMANENTLY_CLOSED
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
ROUND_3 = NOT_STARTED
REAL_MONEY = NOT_AUTHORIZED
```

## Completion and hygiene

Before PASS, execute `REPOSITORY_HYGIENE_POLICY.md`. Remove provably dead diagnostic scratch code/files/assets and stale references; retain reusable validated audit tooling and required receipts/evidence.

Expected completion state:

```text
POST_R2_ACCESS_DECISION = PASS
ROUND_3 = NOT_STARTED
NEXT = AWAIT_OWNER_DATA_SOURCE_OR_PROVIDER_SPEND_DECISION
```

If a bounded internal W2 fix fully removes the access blocker without any spend/source/account change, the next state may instead be:

```text
POST_R2_ACCESS_DECISION = PASS_INTERNAL_FIX_VERIFIED
ROUND_3 = NOT_STARTED
NEXT = AWAIT_OWNER_ROUND_3_AUTHORIZATION
```
