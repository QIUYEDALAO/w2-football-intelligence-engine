# W2 Project Ledger Index

This file is the stable GitHub startup entry for project history.

The canonical append-only execution and acceptance ledger is:

- `docs/consolidation/W2_TASK_ACCEPTANCE_LEDGER.md`

Do not duplicate or rewrite historical entries here. At the start of every task,
read `PROJECT_STATE.yaml`, this index, `NEXT_ACTION.md`, and then the canonical
ledger entries relevant to the active blocker.

Current latest entry: `V3 进展续89 · DATA-08 回滚对齐但展示隔离失败`.

Current blocking chain:

1. `DATA-08 / DATA_PIPELINE_BLOCKED`: MA-03 is paused. `main@1e444d3` displays
   approximately 44-hour-old AH/OU values for four fixtures, including a fixture
   about 197 minutes from kickoff. The values are provenance-preserving but not
   appropriate as primary current odds. Classification is `RED + BLOCKED` until
   quotes older than 30 minutes are hidden and a globally budgeted natural
   T6-to-T15 active-window refresh is deployed and accepted.
   Four-service rollback to `7ad56cd` is healthy and aligned, but it is not a
   display-safety control because existing forward captures still expose three
   expired quotes. Explicit API projection containment is now the unique next
   code action. Fixture `1523207` independently received a natural fresh quote
   at `2026-07-17T10:00:04Z`; no manual Provider refresh was used.
2. `L2-02`: Frozen L2 exact identity cannot pass until a current eligible capture
   exists.
3. Draft Policy ADR remains pending after data and evidence recovery.
4. U04 and M2 are outside the current allowed execution scope.
