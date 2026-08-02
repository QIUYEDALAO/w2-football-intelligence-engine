# Wave 3 Gate A offline acceptance contract

This tranche implements the final Wave 1 denominator without reopening T00:
28 accepted Gate A groups, 35 exact blocker mappings, and 30 fault-injection
contracts. The machine authority is
`config/policies/gate_a_offline_contracts.v1.json`.

The only executable runtime is the direct foreground command
`scripts/run_prematch_refresh.py --execute --authorization-file ...`. It is
fail-closed by default, accepts a short-lived independently reviewed one-shot
authorization for one competition/season/exact runtime artifact, requires DB persistence
and migration-head parity, and atomically fences concurrent owners with a
PostgreSQL lease epoch plus per-call reservation. A possible Provider delivery
stops automatic retry.

Admission binds either an immutable image digest or a disposable complete-clean
checkout manifest. Checkout mode rejects every tracked/untracked change and any
ignored executable/importable content; `--untracked-files=no` is not accepted as
cleanliness evidence. The repository contains only a disabled, retired public
key record with its SHA-256 fingerprint. An authorization-capable key must be
supplied by an independent signer with `INDEPENDENT_SIGNER_CONFIRMED` custody;
Codex neither owns nor creates that private key.

No authorization artifact is included in the repository. Scheduler, Celery,
Compose restart, deployment, Candidate, Formal, Lock, Production, and real
Provider execution remain outside this offline tranche.

`scripts/validate_gate_a_offline_evidence.py` is the sole admission command. It
loads and verifies the signed authorization, connects to the target DB, calls
the unique `produce_gate_a_evidence()` authority, validates that in-memory
result, and only then atomically archives it. An optional existing evidence
file is canonical-byte compared with the DB recomputation and is never a source
of lineage or counts.

The producer selects one COMPLETED task audit by exact authorization ID and
lease epoch, never by a timestamp window. The audit keeps planning/bucket time
separate from actual execution start. Reservation, audit, and provider calls
must share the lease; provider counts reconcile with both reservation usage and
the audit result, ordinals are contiguous, endpoints stay in signed scope, and
the call cap is enforced. Raw-payload evidence counts only rows whose DB
`inserted_at` proves first persistence after reservation, so a new capture of a
pre-existing SHA yields a zero delta and fails admission.

The command requires exact dynamic-v2 and five-state content (finite,
nonnegative, exact keys, sum tolerance `1e-9`) and full exact-pair identity and
capture lineage. Production pair hashes and bootstrap seed are compared with
the existing Claude-authored Oracle in a `python -I` subprocess whose source
path/hash is bound in evidence; neither Oracle file imports `w2`. Any zero delta
or mismatch is a hard `FAILED` result. The command creates no authorization.
