# W2 Project Decision Ledger

This file records human decisions only. Machine-readable current state belongs in
[PROJECT_STATE.yaml](PROJECT_STATE.yaml); task order, specifications, and merged completion
receipts belong in the
[v3 master checklist](docs/operations/architecture_convergence/W2_ARCHITECTURE_CONVERGENCE_MASTER_CHECKLIST.md).
The AI handoff summary is [AI_PROJECT_CONTEXT.md](AI_PROJECT_CONTEXT.md). It summarizes
the authorities but does not replace them. Historical evidence remains under `docs/archive/`
and in Git history.

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
- `NEXT_ACTION.md` is an index to the current authorities.

## 2026-07-31 — Independent final-audit operating rules

- A148 is accepted only as proof that a contradictory precondition failed closed before
  Provider execution. It is not proof that the Provider-to-pair chain works.
- Runtime safety follows three invariants:
  1. missing or unknown safety inputs deny execution;
  2. failures after a possible external Provider side effect are explicit and stop further calls;
  3. idempotency is accepted only after the expected constraint and stored business fields
     are verified.
- A real canary is an evidence-chain acceptance test. Every required Provider, ledger,
  raw-payload, endpoint-capture, lineup-event, dynamic-evaluation, five-state-snapshot,
  and exact-pair delta must be positive and belong to one reconciled lineage.
- Any required zero delta or broken lineage is `CANARY_FAILED`; it is not “no data”,
  `COMPLETED`, or “safe completion”.
- Provider, real canary, persistent scheduler, Candidate, Formal, Lock, and Production
  remain unauthorized until the runtime-safety remediation is independently accepted.
