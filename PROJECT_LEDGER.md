# W2 Project Ledger Index

This file is the stable GitHub startup entry for project history.

The canonical append-only execution and acceptance ledger is:

- `docs/consolidation/W2_TASK_ACCEPTANCE_LEDGER.md`

Do not duplicate or rewrite historical entries here. At the start of every task,
read `PROJECT_STATE.yaml`, this index, `NEXT_ACTION.md`, and then the canonical
ledger entries relevant to the active blocker.

Current latest entry: `V3 进展续82 · DATA-06 旧 observation 冒充 T6 与第三次回滚`.

Current blocking chain:

1. `DATA-06 / DATA_PIPELINE_BLOCKED`: `main@d571ea1` passed CI and deployment
   alignment, but a bounded zero-provider auto run wrote four T6 records for two
   fixtures from observations captured two days earlier. Stale odds may remain
   displayable, but cannot be labelled as a current legal checkpoint. Staging was
   rolled back to `7ad56cd`; immutable records are preserved without rewrite.
2. `L2-02`: Frozen L2 exact identity cannot pass until a current eligible capture
   exists.
3. Draft Policy ADR remains pending after data and evidence recovery.
4. U04 and M2 are outside the current allowed execution scope.
