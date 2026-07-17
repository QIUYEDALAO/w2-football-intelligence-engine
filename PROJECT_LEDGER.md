# W2 Project Ledger Index

This file is the stable local-Git startup entry for project history.

The canonical append-only execution and acceptance ledger is:

- `docs/consolidation/W2_TASK_ACCEPTANCE_LEDGER.md`

Do not duplicate or rewrite historical entries here. At the start of every task,
read `PROJECT_STATE.yaml`, this index, `NEXT_ACTION.md`, and then the canonical
ledger entries relevant to the active blocker.

Current latest entry: `V3 进展续93 · DATA-08 精确到期调度通过、Provider 日上限阻塞`.

Current blocking chain:

1. `DATA-08 / DATA_PIPELINE_BLOCKED`: release `0f359149` hides expired odds and
   prequeues every checkpoint inside the 15-minute scan window for execution at
   its own exact due time. Four services are healthy and aligned. A natural T1
   task due at `2026-07-17T21:30:00Z` completed at `21:30:00.076Z`, proving the
   former 15-minute stale gap is closed. Market recovery remains `RED + BLOCKED`
   because the UTC-day Provider ledger is exactly `120/120`; all 120 calls
   succeeded and the new tasks used 0 calls under `DAILY_PROVIDER_HARD_CAP_EXCEEDED`.
   Wait for the natural UTC-day reset at `2026-07-18T00:00:00Z`; do not force a
   request or weaken the cap.
2. `L2-02`: Frozen L2 exact identity cannot pass until a current eligible capture
   exists.
3. Draft Policy ADR remains pending after data and evidence recovery.
4. U04 and M2 are outside the current allowed execution scope.
