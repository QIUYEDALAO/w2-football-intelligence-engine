# W2 Free Plan Bridge — Controlled Runtime Closure Authorization

```text
TASK = W2_MI_FREE_PLAN_BRIDGE_CONTROLLED_RUNTIME_CLOSURE
OWNER_DECISION = APPROVED_EXECUTE_CONTINUOUSLY
ROUND_1 = PASS
ROUND_2 = PASS_WITH_TERMINAL_PROVIDER_PLAN_RESTRICTION
FREE_PLAN_FIXTURE_CENTRIC_VALIDATION = FREE_FIXTURE_CENTRIC_CURRENT_DATA_WORKS
ROUND_3 = NOT_STARTED
```

## Mission

Take PR #495 from a disabled proof-of-capability bridge to a production-safe **Shadow collection capability** using the existing API-Football Free account, without paid renewal and without entering Round 3.

Codex must execute continuously through all in-scope failures and bounded remediations until the acceptance authority passes. Do not stop after one failing test, PR merge, deployment step, or first shadow run to ask the owner again.

```text
FAIL_CLOSED = STOP_AT_FAILED_GATE_FIX_AND_RESUME
FAIL_CLOSED != ABANDON_TASK
```

New owner authorization is required only if the work would exceed the stop lines below.

## Required sequence

1. Re-fetch latest `origin/main`, `origin/context/current`, PR #495 and its CI.
2. Independently audit PR #495 code; do not trust PR prose.
3. Fix all in-scope defects on PR #495 before merge.
4. Re-run local focused/full required quality gates and PR Fast / required release candidate checks.
5. Merge PR #495 only after every pre-merge gate passes.
6. From updated main, implement exactly one bounded controlled-runtime integration PR if runtime ownership/wiring is not already correctly included.
7. Integrate with the existing scheduler/operational framework; do not create a second independent scheduler daemon.
8. Keep bridge runtime mode `SHADOW_ONLY`: it may collect/store evidence through existing raw/capture/identity/market contracts, but may not create recommendations, Candidate/Formal/Lock/Production actions, league promotion, or Round-3 semantics.
9. Run a controlled real Free-plan shadow acceptance using current-season fixtures from the existing 13 whitelist only.
10. Prove quota accounting, caching, refresh cadence, no-idle-polling, recovery and rollback.
11. Complete repository hygiene and final receipt.
12. Stop before Round 3.

## Mandatory quota semantics

Provider plan truth:

```text
PROVIDER_DAILY_LIMIT = 100
W2_DAILY_CALL_CEILING = 80
MIN_PROVIDER_DAILY_REMAINING = 20
AUTOMATIC_RETRY = false
```

These values mean W2 may consume at most 80 Provider requests in a UTC provider day while preserving at least 20 of the provider's 100-request allowance.

**Do not double-subtract the reserve.** PR #495 currently uses `daily_hard_cap=80` together with `reserve=20` in a helper whose semantics make the effective ceiling 60. This must be corrected before merge. The final implementation must have explicit, tested semantics for provider daily limit, W2 call ceiling and reserve.

Quota accounting must be global across all W2 API-Football traffic that shares the same account/key. A bridge-local counter that ignores other W2 calls is insufficient. If global actual usage cannot be proven, fail closed rather than assuming capacity.

Use Provider remaining/limit headers or `/status` as authoritative when available, reconcile against the local ledger, and preserve the stricter result.

## Collection efficiency contract

Free plan has already proven:

```text
fixtures?date=<date> = ACCESSIBLE
fixtures?id=<fixture_id> = ACCESSIBLE
odds?fixture=<fixture_id> = ACCESSIBLE
statistics?fixture=<fixture_id> = ACCESSIBLE
fixtures?ids=... = PLAN_RESTRICTED
```

Therefore:

- default `provider_ids_batching = false` on Free;
- do not retry or silently fall back from `ids` after a plan restriction;
- cache/dedupe equivalent request keys;
- no idle polling when no target fixture is due;
- avoid redundant fixture-detail calls when date-discovery already contains the identity fields required by the existing canonical fixture contract;
- prefer the cheapest **verified** request shape; an unverified batching assumption may not enter production.

## Target fixtures and scheduling

Only the existing 13 active-whitelist competitions are eligible. The four Round-2 audit-only leagues remain excluded.

Runtime integration must define deterministic refresh eligibility instead of polling every fixture every cycle. At minimum separate:

```text
DISCOVERY
PREMATCH_MARKET
LINEUP_WINDOW
POSTMATCH_STATISTICS
```

Reuse existing authoritative W2 checkpoints/freshness policies where they exist. Do not invent Round-3 alert thresholds. If a checkpoint is not authoritative, use a conservative operational cadence documented as a collection cadence only, not a product threshold.

On heavy matchdays, quota priority must fail closed and be deterministic. Core current-market evidence wins over optional enrichment. A lower-priority call may be skipped; reserve may not be consumed to make the batch look complete.

## Runtime ownership / persistence

Reuse existing:

```text
RawPayloadStore
endpoint capture
fixture identity
AH/OU normalization
existing Provider client/transport
existing scheduler/operational task framework
existing database/read-model contracts
```

No duplicate fixture, market, raw-payload or quota data model is authorized.

A shared call ledger must record actual Provider calls and enough sanitized evidence to reconcile:

```text
endpoint
request key / fixture id
captured_at
status
actual call index / daily count
provider remaining when observed
skip/cache reason
```

No secret-bearing headers or raw credential material may be stored.

## Real shadow validation budget

This task is authorized to use the existing Free account for bounded real acceptance after code gates pass.

```text
TASK_VALIDATION_NEW_CALL_HARD_CAP = 20
W2_DAILY_CALL_CEILING = 80
MIN_PROVIDER_DAILY_REMAINING = 20
AUTOMATIC_RETRY = false
```

Use fewer calls whenever possible. Do not spend calls merely to hit a number.

Validation must include at least one real current-season fixture from an existing active-whitelist competition and, when real availability permits, prove:

```text
discovery -> fixture identity -> odds -> AH/OU normalization -> raw/capture persistence
```

Statistics/lineup evidence should be validated only when the fixture state makes the endpoint meaningful and budget permits.

## Merge / deploy / activation authority

This authorization allows:

- bounded fixes on PR #495;
- merge of PR #495 after acceptance;
- one bounded runtime-integration PR if needed;
- normal CI/release governance for that integration;
- deployment of the accepted integration using normal immutable release procedure;
- activation of the bridge in `SHADOW_ONLY` mode for the existing 13 whitelist, subject to all quota and rollback gates.

It does **not** authorize public recommendation behavior, league expansion or Round 3.

## Permanent stop lines

```text
API_FOOTBALL_PRO_RENEWAL = NOT_AUTHORIZED_NOW
ACTIVE_WHITELIST = EXACT_EXISTING_13
AUDIT_ONLY_LEAGUE_PROMOTION = 0
NEW_PROVIDER_PURCHASE = NOT_AUTHORIZED
NEW_PROVIDER_CUTOVER = NOT_AUTHORIZED
ROUND_3 = NOT_STARTED
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
H_RESULT_ACCESS = PERMANENTLY_CLOSED
BETTING_EDGE_CLAIM = FORBIDDEN
MODEL_MARKET_DIVERGENCE_AS_OPPORTUNITY = FORBIDDEN
REAL_MONEY = NOT_AUTHORIZED
```

## Completion

Task is complete only when `FREE_PLAN_BRIDGE_CONTROLLED_RUNTIME_ACCEPTANCE.md` passes, repository hygiene passes, and a final durable receipt is written.
