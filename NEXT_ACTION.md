# NEXT ACTION

```text
ACTIVE_NEXT_ACTION = CODEX_EXECUTE_SC18_00_FT_RETENTION
CURRENT_GATE = SC18_00_FT_RETENTION_EXECUTION
AUTHORITY = OWNER_SC18_00_FT_RETENTION_REMEDIATION.md
EXACT_MAIN_BASE = e9cbaf26701704645da00c2ff4733bda3aa34a79
EXACT_CONTEXT_BASE = ba7e3346a4319c76b604e14951e0a0d8061410bf
PR = UPDATE_OR_CREATE_NORMAL_PR
SHADOW_CANDIDATE = KEEP_ACTIVE_SHADOW_ONLY
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
ROUND_4 = NOT_STARTED
P6 = NOT_AUTHORIZED
TERMINAL_GATE = OWNER_SC18_00_FT_RETENTION_REREVIEW
```

## Execute only SC18-00

1. Reproduce the FT disappearance using persisted/read-only evidence for
   fixtures `1493049`, `1575453`, and `1494239`.
2. Make the smallest root-cause fix so the discovery date follows the active
   Asia/Shanghai 12:00-to-12:00 football day and an in-window card is not
   removed merely because kickoff passed or status became terminal.
3. Reuse the existing persisted result materialization, forward ledger,
   replay front door, Provider endpoint, Scheduler cadence, quota gates, and
   exact 13-competition whitelist.
4. Add regression coverage for pre-kickoff to FT retention, active-football-day
   discovery, replay-card retention, 12:00 boundary, and no-call-on-read.
5. Run focused regression, full CI, `RELEASE_REQUIRED`, repository hygiene,
   merge, local OCI relay redeploy, and live read-only acceptance.
6. Stop at `OWNER_SC18_00_FT_RETENTION_REREVIEW`.

No manual Provider probe is authorized. Do not add a Provider, change cadence,
change whitelist/model/thresholds, start Round 4/P6, or enable Formal, Lock,
Production, or real money.

## Frozen stop lines

```text
NEXT_DEVELOPMENT_ACTION = NONE_WITHOUT_OWNER_AUTHORITY
NEW_PROVIDER_OR_PLAN = NOT_AUTHORIZED
MANUAL_PROVIDER_PROBE = FORBIDDEN
SCHEDULER_OR_CADENCE_CHANGE = NOT_AUTHORIZED
ACTIVE_WHITELIST_CHANGE = NOT_AUTHORIZED
MODEL_FACTOR_THRESHOLD_CHANGE = NOT_AUTHORIZED
MODEL_RETRAINING = NOT_AUTHORIZED
BOOKMAKER_DEPTH_THRESHOLD_CHANGE = NOT_AUTHORIZED
MARKET_DIRECTION_BENCHMARK_DEFINITION = NOT_AUTHORIZED
EXTERNAL_INTELLIGENCE_ACTIVATION = NOT_AUTHORIZED
PHASE_0_5_REEXECUTION = FORBIDDEN
H_RESULT_ACCESS = PERMANENTLY_CLOSED
ROUND_4_START = NOT_AUTHORIZED
P6_EXECUTION = NOT_AUTHORIZED
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
REAL_MONEY = OFF
READ_PROVIDER_CALLS = 0_REQUIRED
READ_DB_BUSINESS_WRITES = 0_REQUIRED
VPS_DIRECT_GHCR_BULK_IMAGE_PULL = FORBIDDEN_AS_PRIMARY_TRANSPORT
IMAGE_TRANSPORT = LOCAL_OCI_RELAY_PRIMARY
DELETE_PROTECTED_HISTORICAL_EVIDENCE = FORBIDDEN
```
