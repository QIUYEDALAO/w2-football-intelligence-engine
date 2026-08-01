# Wave 3 Gate A offline acceptance contract

This tranche implements the final Wave 1 denominator without reopening T00:
28 accepted Gate A groups, 35 exact blocker mappings, and 30 fault-injection
contracts. The machine authority is
`config/policies/gate_a_offline_contracts.v1.json`.

The only executable runtime is the direct foreground command
`scripts/run_prematch_refresh.py --execute --authorization-file ...`. It is
fail-closed by default, accepts a short-lived independently reviewed one-shot
authorization for one competition/season/exact head, requires DB persistence
and migration-head parity, and atomically fences concurrent owners with a
PostgreSQL lease epoch plus per-call reservation. A possible Provider delivery
stops automatic retry.

No authorization artifact is included in the repository. Scheduler, Celery,
Compose restart, deployment, Candidate, Formal, Lock, Production, and real
Provider execution remain outside this offline tranche.

The hard evidence validator rejects a missing serializer version, independent
pair/bootstrap mismatch, NaN/Infinity, any zero required canary delta, or raw
payload/endpoint-capture lineage mismatch. This validator validates evidence;
it does not create canary authorization.
