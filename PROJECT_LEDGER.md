# W2 Project Decision Ledger

This file records human decisions only. `PROJECT_STATE.yaml` remains the sole machine-readable
project-status record for the existing operational W2 track. Task order, specifications, and
merged completion receipts for the historical operational program belong in the
[v3 master checklist](docs/operations/architecture_convergence/W2_ARCHITECTURE_CONVERGENCE_MASTER_CHECKLIST.md).
The quant-research program has a separate bounded machine state and task authority in
[QUANT_PROJECT_STATE.yaml](QUANT_PROJECT_STATE.yaml) and
[W2_QUANT_PROGRAM_MASTER_CHECKLIST.md](docs/operations/W2_QUANT_PROGRAM_MASTER_CHECKLIST.md).
The AI handoff summary is [AI_PROJECT_CONTEXT.md](AI_PROJECT_CONTEXT.md). Historical evidence
remains under `docs/archive/` and in Git history.

## 2026-07-18 — Safety boundary

- Champion changes, recommendations, locks, formal output, and production activation require
  explicit later authorization.
- Read-only preparation or evaluation does not authorize those capabilities.

## 2026-07-23 — Architecture convergence

- Feature development is frozen outside the master checklist.
- Canonical database authorities replace production file and provider fallbacks; missing or
  conflicting authority fails closed.
- New destructive migrations must count protected rows and abort rather than delete non-empty
  business data.

## 2026-07-24 — Single task authority

- The v3 master checklist is the only task-order and task-specification authority for the
  historical operational program.
- Phase P2 hygiene work may run alongside Phase B but must not preempt the EVAL-01 sequence.
- Structural checklist changes require a reviewed documentation PR.

## 2026-07-29 — Status record convergence

- `PROJECT_STATE.yaml` is the sole machine-readable project-status record for the operational
  track.
- This ledger contains decisions, not task status, commit coordinates, CI receipts, or
  operational evidence.
- `NEXT_ACTION.md` is an index to the current authorities.

## 2026-07-31 — Independent final-audit operating rules

- A148 is accepted only as proof that a contradictory precondition failed closed before
  Provider execution. It is not proof that the Provider-to-pair chain works.
- Runtime safety follows three invariants:
  1. missing or unknown safety inputs deny execution;
  2. failures after a possible external Provider side effect are explicit and stop further calls;
  3. idempotency is accepted only after the expected constraint and stored business fields are
     verified.
- A real canary is an evidence-chain acceptance test. Every required Provider, ledger,
  raw-payload, endpoint-capture, lineup-event, dynamic-evaluation, five-state-snapshot, and
  exact-pair delta must be positive and belong to one reconciled lineage.
- Any required zero delta or broken lineage is `CANARY_FAILED`; it is not “no data”,
  `COMPLETED`, or “safe completion”.
- Provider, real canary, persistent scheduler, Candidate, Formal, Lock, and Production remain
  unauthorized until runtime-safety remediation is independently accepted.

## 2026-08-05 — Sporttery quant research reframe

- W2 will not be rebuilt as a separate project and the existing V4 recommendation chain will
  not be converted in place.
- A new `quant_research` bounded context will be built in the same repository and will consume
  existing operational identities and models only through explicit ports.
- Freeze A0 offline engineering is approved with Binding Errata A.
- Freeze A1 live dual-source collection remains an owner/API/licensing decision.
- The current approved next code task is `W2_QUANT_L1_OFFLINE_FOUNDATION`.
- The existing single-match system remains operational data, model and signal infrastructure;
  its Candidate, Formal, Lock and Production capabilities remain off.
- Strategy execution, Shadow orders, bankroll/risk simulation, portfolio construction, 2×1 and
  real-money execution are not authorized.
