# W2 Project Ledger Index

This file is the stable local-Git startup entry for project history.

The canonical append-only execution and acceptance ledger is:

- `docs/consolidation/W2_TASK_ACCEPTANCE_LEDGER.md`

Do not duplicate or rewrite historical entries here. At the start of every task,
read `PROJECT_STATE.yaml`, this index, `NEXT_ACTION.md`, and then the canonical
ledger entries relevant to the active blocker.

Current latest entry: `V3 进展续96 · 用户要求回退至 GPT-5.6 正式发布前版本`.

Current blocking chain:

1. `ROLLBACK-01`: Staging API/Worker/Scheduler/Frontend are aligned on
   `b5cfd6575ba7274692714c9fc814916a00c13e36`, committed at
   `2026-07-08T21:34:33+08:00`. This is the final verified W2 release before
   GPT-5.6 general availability on 2026-07-09. Application rollback is complete;
   PostgreSQL/runtime data were preserved because no pre-July-9 database
   snapshot exists. All repair and acceptance tasks are paused.
2. Superseded `DATA-08`: release `8be60bcb` hides expired odds and
   prequeues every checkpoint inside the 15-minute scan window for execution at
   its own exact due time. Four services are healthy and aligned. A natural T1
   task due at `2026-07-17T21:30:00Z` completed at `21:30:00.076Z`, proving the
   former 15-minute stale gap is closed. Market recovery remains `RED + BLOCKED`
   because W2 incorrectly counted 32 unbilled `/status` health requests against
   its internal 120-call safety budget. Football-API headers confirm the real
   billable usage is `88/7500`: fixtures=32, lineups=7 and odds=49. The directed
   correction is deployed. Natural refreshes for fixtures `1492295/1492297`
   completed without blockers at 05:55 Beijing, Football-API usage advanced
   from 88 to 94 with 7406 remaining, and fresh AH/OU is visible as PARTIAL/SKIP.
   Dashboard market access is recovered; only evidence eligibility remains open.
3. `L2-02`: Frozen L2 exact identity cannot pass until a current eligible capture
   exists.
4. Draft Policy ADR remains pending after data and evidence recovery.
5. U04 and M2 are outside the current allowed execution scope.
