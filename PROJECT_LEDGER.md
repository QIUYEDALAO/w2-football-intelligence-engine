# W2 Project Ledger Index

This file is the stable GitHub startup entry for project history.

The canonical append-only execution and acceptance ledger is:

- `docs/consolidation/W2_TASK_ACCEPTANCE_LEDGER.md`

Do not duplicate or rewrite historical entries here. At the start of every task,
read `PROJECT_STATE.yaml`, this index, `NEXT_ACTION.md`, and then the canonical
ledger entries relevant to the active blocker.

Current latest entry: `V3 进展续81 · STALE 展示恢复、WATCH 安全门回滚`.

Current blocking chain:

1. `DATA-05 / IMPLEMENTATION_IN_PROGRESS`: PR #337 restored STALE odds display,
   but the second staging attempt was rolled back because STALE forward captures
   remained WATCH. Every STALE source must be forced to NOT_READY and excluded
   from worth-watching/recommendation regions.
2. `L2-02`: Frozen L2 exact identity cannot pass until a current eligible capture
   exists.
3. Draft Policy ADR remains pending after data and evidence recovery.
4. U04 and M2 are outside the current allowed execution scope.
