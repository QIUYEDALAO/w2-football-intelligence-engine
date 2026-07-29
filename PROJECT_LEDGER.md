# W2 Project Decision Ledger

This file records human decisions only. Machine-readable state belongs in
[PROJECT_STATE.yaml](PROJECT_STATE.yaml); task order, specifications, and completion
receipts belong in the
[v3 master checklist](docs/operations/architecture_convergence/W2_ARCHITECTURE_CONVERGENCE_MASTER_CHECKLIST.md).
Historical execution evidence remains available under `docs/archive/` and in Git history.

## 2026-07-18 — Safety boundary

- Champion changes, recommendations, locks, formal output, and production activation
  require explicit later authorization.
- Read-only preparation or evaluation does not authorize those capabilities.

## 2026-07-23 — Architecture convergence

- Feature development is frozen outside the master checklist.
- Canonical database authorities replace production file and provider fallbacks;
  missing or conflicting authority fails closed.
- New destructive migrations must count protected rows and abort rather than delete
  non-empty business data.

## 2026-07-24 — Single task authority

- The v3 master checklist is the only task-order and task-specification authority.
- Phase P2 hygiene work may run alongside Phase B but must not preempt the EVAL-01
  sequence.
- Structural checklist changes require a reviewed documentation PR.

## 2026-07-29 — Status record convergence

- `PROJECT_STATE.yaml` is the sole machine-readable project-status record.
- This ledger contains decisions, not task status, commit coordinates, CI receipts, or
  operational evidence.
- `NEXT_ACTION.md` is only an index to the two current authorities.
