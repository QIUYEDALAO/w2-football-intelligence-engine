# W2 Project Ledger Index

This file is the stable GitHub startup entry for project history.

The canonical append-only execution and acceptance ledger is:

- `docs/consolidation/W2_TASK_ACCEPTANCE_LEDGER.md`

Do not duplicate or rewrite historical entries here. At the start of every task,
read `PROJECT_STATE.yaml`, this index, `NEXT_ACTION.md`, and then the canonical
ledger entries relevant to the active blocker.

Current latest entry: `V3 进展续86 · Dashboard STALE 即时展示通过、等待自然周期`.

Current blocking chain:

1. `MA-03 / STAGING_OBSERVATION_IN_PROGRESS`: `main@1e444d3` is deployed with
   four-service alignment. Four materialized fixtures display AH/OU as STALE with
   provider source, capture time and source hash; all remain NOT_READY with
   WATCH/RECOMMEND/lock=0. Reconcile-only wrote no timeline artifacts and made no
   Provider calls. Immediate status is `YELLOW + NOT_READY`; wait only for
   naturally due T1/T15 cycles from 2026-07-17T10:00:00Z.
2. `L2-02`: Frozen L2 exact identity cannot pass until a current eligible capture
   exists.
3. Draft Policy ADR remains pending after data and evidence recovery.
4. U04 and M2 are outside the current allowed execution scope.
