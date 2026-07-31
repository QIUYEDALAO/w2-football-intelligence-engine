# NEXT ACTION

- AI handoff: [AI_PROJECT_CONTEXT.md](AI_PROJECT_CONTEXT.md)
- Machine state: [PROJECT_STATE.yaml](PROJECT_STATE.yaml)
- Independent final audit: [W2_INDEPENDENT_FINAL_AUDIT_20260731.md](docs/operations/W2_INDEPENDENT_FINAL_AUDIT_20260731.md)
- Asset uniqueness audit: [W2_ASSET_UNIQUENESS_AUDIT_20260731.md](docs/operations/W2_ASSET_UNIQUENESS_AUDIT_20260731.md)
- Audit-perspective registry: [W2_AUDIT_PERSPECTIVE_REGISTRY.md](docs/operations/W2_AUDIT_PERSPECTIVE_REGISTRY.md)
- Codex execution authority: GitHub Issue **#454 v4**
- Workflow-governance incident: GitHub Issue **#455**
- Computation-authority issue: GitHub Issue **#456**
- Quarantined evidence: PR **#453 — DO NOT MERGE / DO NOT REPAIR IN PLACE**

## Current verified state

```text
trusted main = dbc8e1e8aa74a7613fd7121bf6026890c3ee06c6
main contamination = false
storage deletion residuals = no current evidence
computation authority R5 = open
canonical serialization = Critical Gate A blocker
PR #453 = quarantined evidence only
EVAL-02B end-to-end = BLOCKED / NOT_VALIDATED
Provider = OFF
real canary = NOT_AUTHORIZED
persistent scheduler = OFF
Candidate / Formal / Lock / Production = OFF
auto merge = FORBIDDEN
```

## Next action code

```text
T00_GOV_THEN_T00_SAFE_R1_R5_THEN_CANONICAL_SERIALIZATION_THEN_TRUSTED_C9_REBUILD
```

## Required order

1. **Synchronize GitHub to a local clean worktree.** Verify `origin`, fetch all refs/tags, record exact main and affected branch heads, and stop on unexplained drift.
2. **T00-GOV (#455).** Reproduce every agent workflow/run/commit/push and reduce all unclassified governance counts to zero.
3. **T00-SAFE R1–R5 and asset inventory (#454/#456).** Run an exact-SHA-bound reproducible scan for:
   - R1 default allow/missing authority;
   - R2 silent failure/failure downgrade;
   - R3 external-side-effect/local-state non-atomicity;
   - R4 authority/concurrency/identity drift;
   - R5 computation-authority split.
   Reproduce the storage inventory, enumerate every canonical/hash writer and computation authority, and reduce all unclassified findings to zero.
4. **Close the canonical-serialization Gate A blocker (#456).** Before changing callers, inventory persisted hash domains and approve a versioned serialization/migration contract. Do **not** choose `ensure_ascii=True` or `False` by preference and do not overwrite historical hashes in place. Establish one versioned primitive under `src/w2/domain/`, complete the EVAL-02B pair-identity serialization contract, add independent golden vectors/oracle, and add a CI guard.
5. **Review `e875050f` hunk by hunk.** Classify each hunk as `RETAIN_REIMPLEMENT`, `REJECT`, or `REQUIRES_NEW_DESIGN`.
6. **Rebuild C9 from trusted main in a new Draft PR.** Do not copy or cherry-pick workflow-authored remediation code. Implement against the approved canonical serializer authority.
7. **Close the remaining Gate A one-shot-canary blockers.** Complete C1–C11, authorization, reservation/quota, paid-side-effect accounting, schema/empty-data contracts, preflight, failure injection, strict validator and fake-Provider rehearsal.
8. **Synchronize verified context/evidence.** Update this file, AI context, machine state, registry and Issues #454/#455/#456 only after code/GitHub evidence changes.
9. **Stop for independent second review.** Codex must not create a real authorization, call the Provider, merge a PR, start scheduler, or enable product gates.

## Canonical serialization acceptance

```text
CANONICAL_SERIALIZER_AUTHORITY_COUNT = 1
UNVERSIONED_HASH_WRITERS = 0
PAIR_IDENTITY_CONTRACT_COMPLETE = true
UNICODE_GOLDEN_VECTOR_PASS = true
NAN_INFINITY_REJECTED = true
HISTORICAL_HASH_MIGRATION_PROVEN = true
INDEPENDENT_RECOMPUTATION_MATCH = true
```

`ensure_ascii`, Unicode, numeric, Decimal and datetime behavior remain **PENDING CONTRACT/MIGRATION DECISION** until the persisted-hash inventory is complete.

## Canary acceptance

A future human-supervised canary passes only if all required deltas are positive, one lineage including `serializer_version` is reconciled, and an independent implementation reproduces the pair hash/seed. Any zero delta, broken lineage, non-finite value or hash mismatch is `CANARY_FAILED`.

A148 remains `SAFE_FAIL_CLOSED_ONLY`; it proved the barrier, not chain usability.

## Codex mandatory final flags

```text
REAL_PROVIDER_CALL_EXECUTED = false
REAL_CANARY_AUTHORIZATION_CREATED = false
AUTO_MERGE_EXECUTED = false
READY_FOR_INDEPENDENT_SECOND_REVIEW = true|false
```
