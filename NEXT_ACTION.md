# NEXT ACTION

- AI handoff summary: [AI_PROJECT_CONTEXT.md](AI_PROJECT_CONTEXT.md)
- Machine-readable state: [PROJECT_STATE.yaml](PROJECT_STATE.yaml)
- Independent audit: [W2 current main independent final audit](docs/operations/W2_INDEPENDENT_FINAL_AUDIT_20260731.md)
- Frozen Codex execution manifest: GitHub Issue **#454 v3**
- Self-modifying workflow governance incident: GitHub Issue **#455**
- Quarantined evidence PR: **#453 — DO NOT MERGE / DO NOT REPAIR IN PLACE**

## Current verified state

```text
trusted main = dbc8e1e8aa74a7613fd7121bf6026890c3ee06c6
main contamination = false
PR #453 = quarantined evidence only
EVAL-02B end-to-end = BLOCKED / NOT_VALIDATED
real Provider = OFF
real canary = NOT_AUTHORIZED
persistent scheduler = OFF
Candidate / Formal / Lock / Production = OFF
```

The known bot implementation commit is:

```text
e875050f6bc0286aed389aadfce1e17b2063635a
```

It is not a main ancestor and must not be cherry-picked. The deleted dynamic-distribution workflow is tied to:

```text
d041ae2a95a5dbb012c5109846270d2691a3f373
```

## Next action code

```text
T00_GOV_THEN_T00_SAFE_THEN_TRUSTED_C9_REBUILD
```

## Required order

1. **Synchronize GitHub to a local clean repository/worktree.** Verify `origin`, fetch all refs/tags, verify exact main SHA, record all affected agent branch heads, and stop on any unexplained drift.
2. **T00-GOV (#455).** Reproduce the complete workflow/run/commit/push provenance and reduce all unclassified governance counts to zero.
3. **T00-SAFE (#454).** Run a reproducible exact-SHA-bound scan for R1 default allow, R2 silent failure, R3 external-side-effect non-atomicity, and R4 authority/concurrency drift. Unclassified findings must be zero.
4. **Review `e875050f` hunk by hunk.** Classify each hunk as `RETAIN_REIMPLEMENT`, `REJECT`, or `REQUIRES_NEW_DESIGN`.
5. **Rebuild C9 from trusted main in a new local branch and new Draft PR.** Do not merge/rebase/cherry-pick any bot/workflow remediation commit.
6. **Close every Gate A one-shot-canary blocker** in #454: C1–C11 as applicable to the direct foreground path, reservation/quota, request side-effect accounting, schema/empty-data contracts, preflight, strict validator, canary-path fault injection, and fake-Provider offline rehearsal.
7. **Synchronize all GitHub context** only after verified evidence changes: `AI_PROJECT_CONTEXT.md`, `PROJECT_STATE.yaml`, this file, agent instructions, PR #450, #454 and #455.
8. **Stop for independent second review.** Codex must not create a real authorization, call the real Provider, merge a PR, start scheduler, or enable product gates.

## Codex mandatory final flags

```text
REAL_PROVIDER_CALL_EXECUTED = false
REAL_CANARY_AUTHORIZATION_CREATED = false
AUTO_MERGE_EXECUTED = false
READY_FOR_INDEPENDENT_SECOND_REVIEW = true|false
```

## Canary acceptance remains unchanged

A future human-supervised canary is a failure if any required delta is zero or if the single lineage cannot be reconciled. A preflight scope that cannot produce the full evidence chain must stop before external calls and business writes. A148 remains `SAFE_FAIL_CLOSED_ONLY`; it is not evidence that the chain is usable.
