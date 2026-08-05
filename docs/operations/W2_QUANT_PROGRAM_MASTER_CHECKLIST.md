# W2 Sporttery Quant Research Program — Master Checklist

> This file is the task-order and scope authority for the quant-research program only.
> The existing architecture-convergence checklist remains the historical and operational W2
> authority. Quant work must not rewrite completed EVAL/Wave receipts or the deployed V4 chain.

## Program boundary

```text
TARGET_PRODUCT = W2_SPORTTERY_QUANT_RESEARCH_PLATFORM
ARCHITECTURE = SAME_REPOSITORY_INDEPENDENT_BOUNDED_CONTEXT
BOUNDED_CONTEXT_PATH = src/w2/quant_research/
EXISTING_V4_RECOMMENDATION_CHAIN = PRESERVED_AND_UNMODIFIED
```

Permanent boundaries:

- no quant implementation in `src/w2/prematch/`, `src/w2/strategy/`,
  `RecommendationDecisionV4`, or the existing future-refresh business chain;
- Candidate, Formal, Lock and Production stay off;
- no real-money execution is authorised;
- external API collection is not authorised before Freeze A1;
- every business fact has one versioned authority;
- new quant identity hashes must reuse `w2.domain.canonical_serialization` v2;
- historical facts and completed operational receipts are preserved.

## Task order

### QUANT-CTX-00 — Context and Freeze A0 binding

```text
STATUS = IN_PROGRESS
SCOPE = CONTEXT_ONLY
```

Deliverables:

- protocol reference and binding decision;
- Binding Errata A;
- quant machine-readable state;
- current action index;
- semantic context guards;
- no runtime code, migration, Provider calls, images or deployment.

Completion criteria:

```text
FREEZE_A0_OFFLINE_ENGINEERING = APPROVED_WITH_BINDING_ERRATA_A
FREEZE_A1_LIVE_COLLECTION = DEFERRED_OWNER_API_AND_LICENSE
ACTIVE_NEXT_ACTION = W2_QUANT_L1_OFFLINE_FOUNDATION
```

### QUANT-L1-A0 — Offline research foundation

```text
STATUS = AUTHORIZED_AFTER_QUANT_CTX_00_MERGE
NEXT = true
```

Allowed scope:

- `src/w2/quant_research/` domain and ports;
- separate `quant_research` schema, append-only tables, constraints and views;
- local JSON and historical Excel adapters;
- revision/supersession authority;
- AS-OF and post-event separation;
- deterministic PostgreSQL offline replay;
- Track 1 data-quality engine and read-only research queries;
- tests and context guards.

Required invariants:

```text
REAL_PROVIDER_CALLS = 0
LIVE_CAPTURE_ENABLED = false
TRACK1_FORWARD_CLOCK = NOT_STARTED
PRODUCTION_DB_MODIFIED = false
DEPLOYMENT_EXECUTED = false
```

Not allowed:

- live adapters or credentials;
- collector activation;
- strategy registration;
- Shadow orders;
- Kelly, bankroll or portfolio logic;
- Dashboard changes;
- any change to V4, operational scheduler or Provider allowlist.

### QUANT-L1-A1 — Live dual-source adapters and collector

```text
STATUS = BLOCKED_OWNER_API_AND_LICENSE
```

Requires a later owner decision covering supplier terms, credentials, capture schedule,
per-consumer quota governance, live mapping bootstrap and deployment boundaries.

### QUANT-TRACK1 — Forward data-quality observation

```text
STATUS = NOT_STARTED
```

Starts only after QUANT-L1-A1 acceptance. It records forward data quality for 14–30 days and
produces no strategy or profitability conclusion.

### QUANT-FREEZE-B — Strategy-research freeze

```text
STATUS = NOT_AUTHORIZED
```

May be considered only after Track 1 data-quality acceptance and parameter freezing.

### QUANT-L2 — Strategy registry

```text
STATUS = NOT_AUTHORIZED
```

### QUANT-L3 — Measurement and Shadow ledger

```text
STATUS = NOT_AUTHORIZED
```

### QUANT-L4 — Bankroll and risk simulation

```text
STATUS = NOT_AUTHORIZED
```

### QUANT-PORTFOLIO — Portfolio and 2×1 construction

```text
STATUS = NOT_AUTHORIZED
```

### QUANT-REAL-MONEY — Any real-money workflow

```text
STATUS = NOT_AUTHORIZED
```

## Current action

```text
ACTIVE_TASK = QUANT-CTX-00
NEXT_CODE_TASK = QUANT-L1-A0
```
