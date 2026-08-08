# W2 Current Task Checklist

```text
PROGRAM = W2_FOOTBALL_MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
PRODUCT = W2 Football Intelligence
ROUND_1 = PASS
ROUND_2 = PASS_WITH_TERMINAL_PROVIDER_PLAN_RESTRICTION
FREE_PLAN_BRIDGE_CONTROLLED_RUNTIME = PASS
ACTIVE_TASK = AWAIT_OWNER_POST_R3_PRODUCT_DECISION
ROUND_3 = PASS_MARKET_RADAR_MODEL_LAB
```

Binding authority:

```text
ROUND_3_OWNER_AUTHORIZATION.md
ROUND_3_CODEX_EXECUTION.md
ROUND_3_ACCEPTANCE_CRITERIA.md
```

## Continuous Round-3 closeout

- [x] Re-fetch latest `origin/main` and `origin/context/current`; record exact SHAs.
- [x] Independently audit real persisted-market/read-model/public paths.
- [x] Define and test real-evidence eligibility/rejection contract.
- [x] Build canonical same-line AH/OU market timeline.
- [x] Build Market Radar current facts, bookmaker depth, de-vig/overround and factual movement contract.
- [x] Record truthful `NOT_CALIBRATED`; no anomaly threshold was invented.
- [x] Build Model Lab same-line >=3-bookmaker market-range diagnostic.
- [x] Gate disagreement on model readiness, same-line evidence, depth and freshness.
- [x] Isolate legacy edge semantics from Round-3 authority.
- [x] Preserve seven-state precedence and four risk dimensions.
- [x] Integrate the existing frozen checkpoint API/read model with zero Provider calls on reads.
- [x] Integrate `Market Radar` and `Model Lab` into existing public surfaces.
- [x] Prove no read-time N+1 market query or Provider-on-read behavior.
- [x] Pass focused/full tests, Ruff, Mypy, Web, Playwright, secret, PR Fast and Release Candidate gates.
- [x] Merge PR #497, the only Round-3 PR.
- [x] Deploy accepted final main through immutable W2 staging release.
- [x] Run real persisted-evidence acceptance without manufacturing readiness.
- [x] Verify non-destructive old-image rollback and Round-3 restore.
- [x] Execute `REPOSITORY_HYGIENE_POLICY.md` with unresolved items 0.
- [x] Create `ROUND_3_FINAL_RECEIPT.md`.
- [x] Update `context/current` and stop at `AWAIT_OWNER_POST_R3_PRODUCT_DECISION`.

## Runtime invariants

```text
FREE_BRIDGE_MODE = SHADOW_ONLY
API_FOOTBALL_PLAN = FREE
PROVIDER_DAILY_LIMIT = 100
W2_DAILY_CALL_CEILING = 80
MIN_PROVIDER_DAILY_REMAINING = 20
AUTOMATIC_RETRY = false
ACTIVE_WHITELIST = EXACT_EXISTING_13
AUDIT_ONLY_RUNTIME_REACHABILITY = 0
```

## Permanent stop lines

```text
API_FOOTBALL_PRO_RENEWAL = NOT_AUTHORIZED_NOW
NEW_PROVIDER_PURCHASE = NOT_AUTHORIZED
NEW_PROVIDER_CUTOVER = NOT_AUTHORIZED
ACTIVE_WHITELIST_CHANGE = false
AUDIT_ONLY_PROMOTION = false
BETTING_EDGE_CLAIM = FORBIDDEN
MODEL_MARKET_DIVERGENCE_AS_OPPORTUNITY = FORBIDDEN
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
H_RESULT_ACCESS = PERMANENTLY_CLOSED
REAL_MONEY = NOT_AUTHORIZED
```
