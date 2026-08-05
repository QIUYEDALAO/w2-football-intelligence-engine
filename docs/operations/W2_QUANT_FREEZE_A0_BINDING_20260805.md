# W2 Quant Freeze A0 Binding — 2026-08-05

## Decision

```text
PROTOCOL_VERSION = v2.3.1
TARGET_PRODUCT = W2_SPORTTERY_QUANT_RESEARCH_PLATFORM
CURRENT_W2_ROLE = FOOTBALL_DATA_MODEL_AND_SIGNAL_INFRASTRUCTURE
ARCHITECTURE = SAME_REPOSITORY_INDEPENDENT_BOUNDED_CONTEXT
EXISTING_V4_RECOMMENDATION_CHAIN = PRESERVED_AND_UNMODIFIED

FREEZE_A0_OFFLINE_ENGINEERING = APPROVED_WITH_BINDING_ERRATA_A
FREEZE_A1_LIVE_COLLECTION = DEFERRED_OWNER_API_AND_LICENSE
TRACK1_FORWARD_CLOCK = NOT_STARTED

L2_STRATEGY_ENGINE = NOT_AUTHORIZED
L3_SHADOW_LEDGER = NOT_AUTHORIZED
L4_BANKROLL_RISK = NOT_AUTHORIZED
PHASE_A = NOT_AUTHORIZED
PHASE_B = NOT_AUTHORIZED
PORTFOLIO = NOT_AUTHORIZED
TWO_LEG_PARLAY = NOT_AUTHORIZED
REAL_MONEY = NOT_AUTHORIZED

CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
```

This binding is the reviewed override for conflicting statements in
`docs/architecture/W2_SPORTTERY_QUANT_RESEARCH_PROTOCOL_V2_3_1.md`.
The protocol remains the research specification; this file is the engineering and authority
binding for Freeze A0.

## Binding Errata A

### E1 — Scheduler fact correction

The statement `SCHEDULER_NEVER_DEPLOYED` is withdrawn.

```text
CURRENT_SCHEDULER = STANDALONE_SCHEDULER_PROCESS_DEPLOYED_AND_CONTROLLED
CELERY_BEAT = NOT_USED_BY_DESIGN
```

The quant subsystem still requires an independent collector because of domain, quota,
identity and permission isolation—not because the operational scheduler is absent.

### E2 — Canonical serialization authority

The quant subsystem must directly reuse:

```text
src/w2/domain/canonical_serialization.py
serializer_version = w2.canonical-json.v2
```

Quant-specific `HashDomain` values may be added later. A second serializer, a local
`canonical_json`, or direct `json.dumps + hashlib.sha256` identity writer is forbidden.

### E3 — API-Football client fact correction

```text
API_FOOTBALL_LEGACY_FETCH = RETIRED_FAIL_CLOSED
API_FOOTBALL_REQUEST_LIVE = CURRENT_WIRED_NETWORK_PATH
```

Freeze A0 performs no network calls. Freeze A1 may add a quant-specific adapter/consumer,
but must not duplicate the existing HTTP transport, request ledger, metrics or header
sanitisation.

### E4 — Infrastructure reuse inventory

The summary `ONLY_3_COMPONENTS_WIRED` is withdrawn as a current repository fact. At the
start of `QUANT-L1-A0`, the implementer must recompute a path-aware reuse matrix against the
then-current `main`. Historical compatibility profiles are not evidence that the current
v2 serializer authority is degraded.

### E5 — Cross-source identity mapping

Odds fingerprints are auxiliary evidence only. They cannot independently approve a
permanent fixture, team or league mapping.

Required evidence includes:

- kickoff UTC within a frozen tolerance;
- normalised home and away teams with orientation preserved;
- competition, season and date compatibility;
- Pinnacle HOME/DRAW/AWAY fingerprint;
- repeated observation or official-result confirmation.

Mapping states are:

```text
CANDIDATE
APPROVED
CONFLICT
SUPERSEDED
```

Only an `APPROVED` fixture mapping may derive team or league mappings. Every mapping must
retain provenance, source capture identities and a canonical identity hash.

### E6 — Q14 acquisition accounting

The observed API-Football page count is per date capture, not a complete daily budget.

```text
Q14_CALLS_PER_CAPTURE = MEASURED
Q14_CAPTURE_TIMES_PER_DAY = NOT_FROZEN
Q14_CALLS_PER_DAY = NOT_EVALUATED
Q14_COST = MARGINAL_ZERO_WITHIN_CURRENT_PLAN
```

These values are measured and frozen only in Freeze A1.

### E7 — Freeze A split

Freeze A0 is approved for offline engineering only:

- `src/w2/quant_research/` bounded context and Provider ports;
- domain objects and offline repositories;
- a separate `quant_research` schema, tables, constraints and views;
- append-only capture and signal ledgers;
- revision and supersession chains;
- `AS_OF_SIGNAL_VIEW` and `POST_EVENT_ENRICHMENT` separation;
- local JSON and historical Excel adapters;
- deterministic offline replay;
- Track 1 data-quality engine and read-only research queries.

Freeze A0 invariants:

```text
REAL_PROVIDER_CALLS = 0
LIVE_CAPTURE_ENABLED = false
TRACK1_FORWARD_CLOCK = NOT_STARTED
PRODUCTION_DB_MODIFIED = false
DEPLOYMENT_EXECUTED = false
```

Freeze A1 is deferred and includes all live adapters, credentials, collector activation,
capture schedule activation, live mapping bootstrap, shared quota governance and the Track 1
forward clock.

```text
Q0_LICENSE_AND_API = PENDING_OWNER_ACTION
Q0_BLOCKS_FREEZE_A1 = true
Q0_BLOCKS_FREEZE_A0 = false
```

### E8 — Database-role administration

Application Alembic migrations may create the `quant_research` schema, tables, indexes,
constraints and views. They must not assume `CREATEROLE`.

A separate DBA bootstrap owns creation and grants for:

```text
quant_ingest_role
quant_asof_reader_role
quant_postevent_role
```

PostgreSQL integration tests must verify that these roles enforce their intended boundaries.
The existing W2 service role receives no quant write permission by default.

## Delivery and runtime boundary

This context decision is documentation-only. It does not authorise runtime code, migrations,
external API calls, image builds, deployment or production configuration changes.

```text
CURRENT_NEXT_ACTION = W2_QUANT_L1_OFFLINE_FOUNDATION
RUNTIME_CODE_CHANGED = false
DATABASE_MIGRATION_CREATED = false
PROVIDER_CALLS = 0
IMAGES_BUILT = 0
DEPLOYMENT_EXECUTED = false
```
