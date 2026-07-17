# W2 Project Ledger Index

This file is the stable GitHub startup entry for project history.

The canonical append-only execution and acceptance ledger is:

- `docs/consolidation/W2_TASK_ACCEPTANCE_LEDGER.md`

Do not duplicate or rewrite historical entries here. At the start of every task,
read `PROJECT_STATE.yaml`, this index, `NEXT_ACTION.md`, and then the canonical
ledger entries relevant to the active blocker.

Current latest entry: `V3 进展续84 · DATA-07 完整盘口卡超出 L1 与第四次回滚`.

Current blocking chain:

1. `DATA-07 / DATA_PIPELINE_BLOCKED`: DATA-06 was fixed and merged as
   `main@ebeea00`, but immediate DayView projection replaced four complete
   database-frozen cards with `L1_CARD_TOO_LARGE`. Their expanded candidate-line
   evidence exceeded the unchanged public L1 size limit. Staging was rolled back
   to `7ad56cd`. Only a bounded display-field projection is allowed; the payload
   limit and evidence data remain unchanged.
2. `L2-02`: Frozen L2 exact identity cannot pass until a current eligible capture
   exists.
3. Draft Policy ADR remains pending after data and evidence recovery.
4. U04 and M2 are outside the current allowed execution scope.
