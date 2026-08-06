# W2 Quant Research AI Context

> Read this file together with `QUANT_PROJECT_STATE.yaml`, the Freeze A0 binding and the quant
> master checklist before changing the quant-research bounded context. The existing
> `AI_PROJECT_CONTEXT.md` and `PROJECT_STATE.yaml` remain the operational W2 history and runtime
> authorities.

## Current program

```text
TOP_LEVEL_PROGRAM = W2_SPORTTERY_QUANT_RESEARCH_PLATFORM
ACTIVE_NEXT_ACTION = W2_QUANT_L1_OFFLINE_FOUNDATION
CURRENT_PHASE = QUANT_CONTEXT_CLOSURE
PROTOCOL_VERSION = v2.3.1
FREEZE_A0 = APPROVED_WITH_BINDING_ERRATA_A
FREEZE_A1 = DEFERRED_OWNER_API_AND_LICENSE
TRACK1_FORWARD_CLOCK = NOT_STARTED
```

Authorities:

- `QUANT_PROJECT_STATE.yaml`
- `docs/operations/W2_QUANT_PROGRAM_MASTER_CHECKLIST.md`
- `docs/architecture/W2_SPORTTERY_QUANT_RESEARCH_PROTOCOL_V2_3_1.md`
- `docs/operations/W2_QUANT_FREEZE_A0_BINDING_20260805.md`

## Product and architecture decision

W2 is not being rebuilt in a separate repository and the existing V4 recommendation chain is
not being converted in place. The new system is a same-repository, independent
`src/w2/quant_research/` bounded context with explicit ports to operational identities and
models.

```text
EXISTING_V4_RECOMMENDATION_CHAIN = PRESERVED_AND_UNMODIFIED
QUANT_L1 = OFFLINE_FOUNDATION_ONLY
LIVE_CAPTURE_ENABLED = false
```

## Freeze A0 allowed scope

- quant domain objects and Provider ports;
- separate `quant_research` schema, tables, constraints and views;
- append-only capture/signal ledgers and revision chains;
- AS-OF and post-event physical access separation;
- local JSON and historical Excel adapters;
- deterministic offline replay;
- Track 1 data-quality engine;
- read-only research queries and tests.

## Freeze A0 prohibited scope

- FiroApi or API-Football network calls;
- live collector, credentials or capture schedule activation;
- cross-source live mapping bootstrap;
- strategy registry or selection logic;
- Shadow orders, Kelly, bankroll, risk, portfolio or 2×1;
- changes to prematch, strategy, V4, existing future-refresh, Scheduler or Dashboard;
- production DB mutation or VPS deployment.

## Binding facts

- Current scheduler is a deployed standalone scheduler process; Celery Beat is not used by
  design.
- Quant identity must reuse `src/w2/domain/canonical_serialization.py` and
  `w2.canonical-json.v2`.
- `ApiFootballClient.request_live()` is the current wired transport path; Freeze A0 must not use
  it.
- Odds fingerprints are only auxiliary cross-source mapping evidence.
- Q14 daily calls and cost remain not evaluated until Freeze A1.
- DB roles are created by a separate DBA bootstrap, not assumed in application Alembic.

## Existing operational track

The deployed W2 operational system continues independently:

```text
BASE_MAIN_SHA = 75159bfd71bb7492eece86da29cdb32e6f25d9c6
DEPLOYED_SOURCE_SHA = f1718ec4d74e3038fd6240429df6efca42d0a520
PERSISTENT_SCHEDULER = ON_CONTROLLED
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
```

Historical Wave, Canary, V4, replay and deployment receipts remain valid and are not rewritten
by the quant program.

## Next-task stop line

`W2_QUANT_L1_OFFLINE_FOUNDATION` must finish with:

```text
REAL_PROVIDER_CALLS = 0
LIVE_CAPTURE_ENABLED = false
TRACK1_FORWARD_CLOCK = NOT_STARTED
PRODUCTION_DB_MODIFIED = false
DEPLOYMENT_EXECUTED = false
```
