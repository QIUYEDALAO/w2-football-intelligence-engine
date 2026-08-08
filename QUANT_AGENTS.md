# W2 Market Intelligence / Quant Agent Instructions

Read `CURRENT_STATE.yaml`, `NEXT_ACTION.md`,
`ROUND_2_FINAL_RECEIPT.md` and `ROUND_2_FINAL_CAPABILITY_MATRIX.json`.

```text
ROUND_1 = PASS
ROUND_2 = PASS_WITH_TERMINAL_PROVIDER_PLAN_RESTRICTION
ACTIVE_NEXT_ACTION = AWAIT_OWNER_POST_R2_CAPABILITY_DECISION
ROUND_3 = NOT_STARTED
```

Round 2 is a completed capability audit, not an edge experiment. All 17 rows
remain Provider-plan restricted, every promotion flag is false, and the four
net-new candidates remain audit-only.

Do not restart R2-B, create collection, enable leagues or start Round 3 without
new owner authorization. Run `REPOSITORY_HYGIENE_POLICY.md` before any future
task PASS.

Hard guards:

```text
MODEL_MARKET_DIVERGENCE != MARKET_OPPORTUNITY
HIGH_OVERROUND != HIGH_VALUE
HIGH_OVERROUND != HIGH_INFORMATION
BETTING_EDGE_CLAIM = FORBIDDEN
H_RESULT_ACCESS = PERMANENTLY_CLOSED
ACTIVE_WHITELIST = 13_UNCHANGED
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
REAL_MONEY = NOT_AUTHORIZED
```
