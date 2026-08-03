# NEXT ACTION

当前唯一动作：`POST_RECOVERY_OBSERVATION_AND_DYNAMIC_EVALUATION_READINESS`。
生产 Dashboard 与真实未来比赛已经恢复；后续只观察受控采集、恢复 production dynamic
evaluation readiness，并证明 cold-pull SLO。EVAL-03 尚未开始。

```text
TOP_LEVEL_TASK = EVAL-02B
ACTIVE_NEXT_ACTION = POST_RECOVERY_OBSERVATION_AND_DYNAMIC_EVALUATION_READINESS
ACTIVE_CONTEXT_PR = NONE
CURRENT_WORKSTREAM = POST_RECOVERY_OBSERVATION_AND_DYNAMIC_EVALUATION_READINESS
CURRENT_PHASE = PRODUCTION_RECOVERY_CONTEXT_CLOSURE_COMPLETE
AUDIT_BASELINE_SHA = dbc8e1e8aa74a7613fd7121bf6026890c3ee06c6
CURRENT_MAIN_SHA = 3b38e283959394459671e441132c1e1cb9d1f019
DEPLOYED_SHA = 3b38e283959394459671e441132c1e1cb9d1f019

DASHBOARD_REAL_DATA_RECOVERY = PASS
PUBLIC_DASHBOARD_CARDS = 51
PRODUCTION_FUTURE_FIXTURES = 51
PROVIDER_REQUEST_DELTA = 58
ENDPOINT_CAPTURE_DELTA = 58
PROVIDER_ERRORS = 0

COLLECTION_READY_COMPETITIONS = brasileirao_serie_a,chinese_super_league,allsvenskan,eliteserien
PROVIDER = ON_CONTROLLED
REAL_PROVIDER = ON_CONTROLLED
PERSISTENT_SCHEDULER = ON_CONTROLLED
SCHEDULER_CONCURRENCY = 1
PROVIDER_ATTEMPTS = 1
DAILY_HARD_CAP = 120
TICK_HARD_CAP = 30

DYNAMIC_EVALUATION_V2 = 0
EXPLICIT_NOT_READY_CARDS = 51
DYNAMIC_EVALUATION_PRODUCTION_RECOVERY = PENDING
EVAL-03 = NOT STARTED
COLD_PULL_SLO = NOT_PROVEN
T00_RERUN = FORBIDDEN_UNLESS_NEW_APPROVED_EVIDENCE
NEXT_CODE_ACTION = NONE_AUTHORIZED

CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
AUTO_MERGE = FORBIDDEN
```

## Missing collection policy coverage

以下已注册联赛不得从白名单删除；它们尚未同时接入 future-refresh 与 matchday policy：

- `argentina_primera`
- `bundesliga`
- `eredivisie`
- `la_liga`
- `ligue_1`
- `mls`
- `premier_league`
- `primeira_liga`
- `serie_a`

## Boundaries

- 现有 scheduler 只允许四个 collection-ready 联赛，保持 concurrency=1、attempts=1、
  daily hard cap=120、tick hard cap=30、ledger 与 Redis/DB dedupe。
- 不扩大 scheduler allowlist，不调用 Provider，不重启 scheduler，不重新部署。
- Candidate、Formal、Lock、Production 继续关闭。
- `DYNAMIC_EVALUATION_V2 = 0` 不能声明 production dynamic evaluation 已恢复；当前 51 张
  公网卡片均为显式 `NOT_READY`。
- cold-pull 已发生超时回滚，只有 warm switch 成功，因此 cold-pull SLO 仍为 `NOT_PROVEN`。

- Machine-readable status: [PROJECT_STATE.yaml](PROJECT_STATE.yaml)
- Production recovery receipt: [W2 Production Recovery Receipt](docs/operations/W2_PRODUCTION_RECOVERY_RECEIPT_20260803.md)
- Historical task specifications and receipts: [W2 architecture convergence master checklist](docs/operations/architecture_convergence/W2_ARCHITECTURE_CONVERGENCE_MASTER_CHECKLIST.md)

## Historical receipt / 历史回执

Wave 1–4、A148、PR #450 与旧 VPS postdeploy 事实继续保留为历史证据；它们不得覆盖
上述 production recovery 当前状态。

## Context-only stop line

```text
CONTEXT_CLOSURE_PROVIDER_CALL_DELTA = 0
SCHEDULER_RESTARTED_IN_CONTEXT_CLOSURE = false
DEPLOYMENT_EXECUTED_IN_CONTEXT_CLOSURE = false
AUTO_MERGE_EXECUTED = false
```
