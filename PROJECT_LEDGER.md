# W2 Project Ledger Index

This file is the stable GitHub startup entry for project history.

The canonical append-only execution and acceptance ledger is:

- `docs/consolidation/W2_TASK_ACCEPTANCE_LEDGER.md`

Do not duplicate or rewrite historical entries here. At the start of every task,
read `PROJECT_STATE.yaml`, this index, `NEXT_ACTION.md`, and then the canonical
ledger entries relevant to the active blocker.

Current latest entry: `V3 进展续80 · 首次 stale-market 部署回滚与显示优先级定位`.

Current blocking chain:

1. `DATA-04 / IMPLEMENTATION_IN_PROGRESS`: PR #336 is merged, but the first
   staging attempt was rolled back because an older empty forward capture
   overrode a database-frozen card containing real AH/OU. The correction is
   limited to display precedence and remains fail-closed.
2. `L2-02`: Frozen L2 exact identity cannot pass until a current eligible capture
   exists.
3. Draft Policy ADR remains pending after data and evidence recovery.
4. U04 and M2 are outside the current allowed execution scope.
