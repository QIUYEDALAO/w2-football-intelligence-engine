# W2 Project Ledger Index

This file is the stable GitHub startup entry for project history.

The canonical append-only execution and acceptance ledger is:

- `docs/consolidation/W2_TASK_ACCEPTANCE_LEDGER.md`

Do not duplicate or rewrite historical entries here. At the start of every task,
read `PROJECT_STATE.yaml`, this index, `NEXT_ACTION.md`, and then the canonical
ledger entries relevant to the active blocker.

Current latest entry: `V3 进展续78 · MA-03 四服务部署完成与自然三周期待验收`.

Current blocking chain:

1. `DATA-02 / DATA_PIPELINE_BLOCKED`: `main@7ad56cd` is deployed to all four
   staging services; three consecutive naturally due cycles beginning at or
   after `2026-07-17T10:00:00Z` must prove current provenance-valid evidence.
2. `L2-02`: Frozen L2 exact identity cannot pass until a current eligible capture
   exists.
3. Draft Policy ADR remains pending after data and evidence recovery.
4. U04 and M2 are outside the current allowed execution scope.
