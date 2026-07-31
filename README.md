# W2 Football Intelligence Engine

> Start here: [AI_PROJECT_CONTEXT.md](AI_PROJECT_CONTEXT.md)

## Current status

W2's architecture and write-side implementation have progressed substantially, but the
system is **not authorized for real Provider collection or continuous operation**.

Completed within frozen scope:

- P0/P1/P2 architecture convergence;
- Phase A implementation tasks;
- EVAL-01A/B/C and EVAL-02A;
- OPS-01 Runbook;
- EVAL-02B preregistration, Legacy 35 exclusion decision, and write-side
  Implementations 01–04.

Current boundary:

- EVAL-02B end-to-end is `BLOCKED / NOT_VALIDATED`;
- EVAL-03 is `NOT_STARTED`;
- A148 proved only `SAFE_FAIL_CLOSED_ONLY` before Provider execution;
- Provider, real canary, persistent scheduler, Candidate, Formal, Lock, and Production
  remain off.

The exact code audit and remediation list are in
[docs/operations/W2_INDEPENDENT_FINAL_AUDIT_20260731.md](docs/operations/W2_INDEPENDENT_FINAL_AUDIT_20260731.md).
Machine state is in [PROJECT_STATE.yaml](PROJECT_STATE.yaml), and task order/receipts remain
in the [master checklist](docs/operations/architecture_convergence/W2_ARCHITECTURE_CONVERGENCE_MASTER_CHECKLIST.md).

## Repository operating principles

- Missing or unknown safety inputs deny execution.
- Once a Provider request may have reached the external service, downstream failures are
  explicit and stop further Provider calls.
- Idempotency must be proven by the expected constraint and persisted business fields.
- A canary passes only when every required evidence delta is positive and one full lineage
  is reconciled. A zero required delta is failure, not “no data”.

## Quick Start

Install locked dependencies with Python 3.12:

```bash
make setup
```

Run local checks:

```bash
python3 scripts/check_w2_stage1_contracts.py
make lint
make typecheck
make test
make smoke
```

Run the historical data-model checks:

```bash
uv run python scripts/check_w2_stage3_data_model.py
```

Start local infrastructure when Docker is available:

```bash
make up
make down
```

Render Stage 1 example cards:

```bash
python3 scripts/render_ai_card_text.py examples/recommend/card.json
python3 scripts/render_ai_card_text.py examples/watch/card.json
python3 scripts/render_ai_card_text.py examples/skip/card.json
```

## Stage Boundaries

- Stage 1 Product Contract boundaries remain protected and covered by
  `scripts/check_w2_stage1_contracts.py`.
- W2 does not have real recommendation capability in production until a separately
  approved enablement connects validated models, a validated live-data chain, runtime
  controls, rollback, and operations evidence.
- Dashboard, replay, reporting, and audit code must read canonical Decision Contract and
  read-model authorities rather than reconstructing meaning from legacy fields.
- `ANALYSIS_PICK` remains analysis-only and must carry `分析参考·非稳赢`; production
  actionability is stricter.
- New competition enablement or Provider collection requires a separate approved change
  with competition/season scope, endpoint scope, call budget, persistence target, locking,
  ledger reconciliation, readiness, deployment, and rollback evidence.
- API keys must come from environment variables or a secret manager. Example values in
  `.env.example` are placeholders.
