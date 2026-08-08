# W2 AI Project Context

Current authority is `origin/context/current`.

```text
PRODUCT = W2 Football Intelligence
ROUND_1 = PASS
ROUND_2 = AUTHORIZED_R2_C_NOW
ACTIVE_NEXT_ACTION = W2_MI_R2_C_FINAL_CAPABILITY_DECISION_NOW
WAIT_14_DAYS = false
ROUND_3 = NOT_STARTED
```

Read current task authority from:

```text
ROUND_2_TERMINAL_CLOSURE_AUTHORIZATION.md
CURRENT_STATE.yaml
NEXT_ACTION.md
ROUND_2_ACCEPTANCE_CRITERIA.md
REPOSITORY_HYGIENE_POLICY.md
```

Current Round 2 evidence:

```text
AUDIT_UNION = 17
PLAN_RESTRICTED_ROWS = 17
ACTIVE_WHITELIST = 13_UNCHANGED
```

Execute R2-C now; do not wait for elapsed time. Missing temporal evidence is `TEMPORAL_EVIDENCE_INSUFFICIENT`.

Permanent engineering closeout rule:

```text
TASK_PASS_REQUIRES_REPOSITORY_HYGIENE_PASS = true
```

Before every future task/round may be declared complete, execute `REPOSITORY_HYGIENE_POLICY.md`: delete provably dead/obsolete task assets, remove stale references, rerun required tests, and record cleanup evidence. Preserve reusable tooling and required audit/history evidence.

Permanent product guards:

```text
MODEL_MARKET_DIVERGENCE != MARKET_OPPORTUNITY
RecommendationDecisionV4 = DIAGNOSTIC_INPUT_NOT_PRODUCT_AUTHORITY
BETTING_EDGE_CLAIM = FORBIDDEN
ACTIVE_WHITELIST = 13_UNCHANGED
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
H_RESULT_ACCESS = PERMANENTLY_CLOSED
ROUND_3 = NOT_STARTED
```
