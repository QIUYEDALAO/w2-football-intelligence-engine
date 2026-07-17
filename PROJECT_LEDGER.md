# W2 Project Ledger Index

This file is the stable local-Git startup entry for project history.

The canonical append-only execution and acceptance ledger is:

- `docs/consolidation/W2_TASK_ACCEPTANCE_LEDGER.md`

Do not duplicate or rewrite historical entries here. At the start of every task,
read `PROJECT_STATE.yaml`, this index, `NEXT_ACTION.md`, and then the canonical
ledger entries relevant to the active blocker.

Current latest entry: `V3 进展续94 · Football-API 88/7500 与内部 120 误计数定位`.

Current blocking chain:

1. `DATA-08 / DATA_PIPELINE_BLOCKED`: release `0f359149` hides expired odds and
   prequeues every checkpoint inside the 15-minute scan window for execution at
   its own exact due time. Four services are healthy and aligned. A natural T1
   task due at `2026-07-17T21:30:00Z` completed at `21:30:00.076Z`, proving the
   former 15-minute stale gap is closed. Market recovery remains `RED + BLOCKED`
   because W2 incorrectly counted 32 unbilled `/status` health requests against
   its internal 120-call safety budget. Football-API headers confirm the real
   billable usage is `88/7500`: fixtures=32, lineups=7 and odds=49. The directed
   correction is locally validated and must be deployed before natural-cycle
   acceptance resumes; the 120-call project safety budget itself is unchanged.
2. `L2-02`: Frozen L2 exact identity cannot pass until a current eligible capture
   exists.
3. Draft Policy ADR remains pending after data and evidence recovery.
4. U04 and M2 are outside the current allowed execution scope.
