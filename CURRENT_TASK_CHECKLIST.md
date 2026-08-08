# W2 Current Task Checklist

```text
PROGRAM = W2_FOOTBALL_MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
PRODUCT = W2 Football Intelligence
ROUND_1 = PASS
ROUND_2 = PASS_WITH_TERMINAL_PROVIDER_PLAN_RESTRICTION
FREE_PLAN_BRIDGE_CONTROLLED_RUNTIME = PASS
ACTIVE_TASK = W2_MI_R3_MARKET_RADAR_AND_MODEL_LAB
ROUND_3 = AUTHORIZED_IN_PROGRESS
```

Binding authority:

```text
ROUND_3_OWNER_AUTHORIZATION.md
ROUND_3_CODEX_EXECUTION.md
ROUND_3_ACCEPTANCE_CRITERIA.md
```

## Continuous Round-3 closeout

- [ ] Re-fetch latest `origin/main` and `origin/context/current`; record exact SHAs.
- [ ] Independently audit real persisted-market/read-model/public paths.
- [ ] Define and test real-evidence eligibility/rejection contract.
- [ ] Build canonical same-line AH/OU market timeline.
- [ ] Build Market Radar current facts, bookmaker depth, de-vig/overround and factual movement contract.
- [ ] Record statistical anomaly calibration as `CALIBRATED` or truthful `NOT_CALIBRATED`; do not invent a threshold.
- [ ] Build Model Lab same-line >=3-bookmaker market-range diagnostic.
- [ ] Ensure `MODEL_MARKET_DISAGREEMENT` only when model probability lies outside the observed real bookmaker de-vig range after readiness gates.
- [ ] Isolate legacy EV/cashflow-edge/analysis-direction semantics from Round-3 public authority.
- [ ] Preserve seven-state precedence and four risk dimensions.
- [ ] Integrate API/read model without Provider calls on dashboard reads.
- [ ] Integrate `Market Radar` and `Model Lab` into existing public surfaces.
- [ ] Prove no N+1/provider-on-read behavior.
- [ ] Pass focused/full tests, Ruff, Mypy, Web gates, secret scan, PR Fast and required Release Candidate.
- [ ] Merge accepted Round-3 PR(s), maximum 2.
- [ ] Deploy accepted final main through immutable W2 staging release.
- [ ] Run real persisted-evidence acceptance without manufacturing market/model readiness.
- [ ] Verify non-destructive rollback.
- [ ] Execute `REPOSITORY_HYGIENE_POLICY.md` with unresolved items 0.
- [ ] Create `ROUND_3_FINAL_RECEIPT.md`.
- [ ] Update `context/current` to final Round-3 state and stop at `AWAIT_OWNER_POST_R3_PRODUCT_DECISION`.

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
