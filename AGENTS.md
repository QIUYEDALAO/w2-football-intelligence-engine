# W2 Repository Agent Instructions

Before changing W2, read:

- [`AI_PROJECT_CONTEXT.md`](AI_PROJECT_CONTEXT.md)
- [`PROJECT_STATE.yaml`](PROJECT_STATE.yaml)
- [`NEXT_ACTION.md`](NEXT_ACTION.md)
- [`docs/operations/W2_INDEPENDENT_FINAL_AUDIT_20260731.md`](docs/operations/W2_INDEPENDENT_FINAL_AUDIT_20260731.md)
- [`docs/operations/W2_ASSET_UNIQUENESS_AUDIT_20260731.md`](docs/operations/W2_ASSET_UNIQUENESS_AUDIT_20260731.md)
- [`docs/operations/W2_AUDIT_PERSPECTIVE_REGISTRY.md`](docs/operations/W2_AUDIT_PERSPECTIVE_REGISTRY.md)
- GitHub Issue **#454 v4**
- GitHub Issue **#455**
- GitHub Issue **#456**

## Mandatory local-sync preflight

Do not edit from chat context, a stale workspace, PR #453, or any `agent/eval-02b-c9-*` branch.

Before editing:

```bash
git remote -v
git fetch --all --prune --tags
git status --porcelain=v1
git rev-parse origin/main
git show -s --format='%H %P %an <%ae> %cn <%ce> %s' origin/main
```

Expected trusted main when this context was written:

```text
dbc8e1e8aa74a7613fd7121bf6026890c3ee06c6
```

If main moved, stop and produce a drift/provenance report before editing. Create a clean local worktree from the independently accepted main SHA.

## Quarantined evidence

```text
PR #453 = QUARANTINED / DO NOT MERGE / DO NOT REPAIR IN PLACE
```

Do not merge, rebase or cherry-pick:

```text
e875050f6bc0286aed389aadfce1e17b2063635a
any OpenAI Agent / github-actions bot remediation commit
any agent/eval-02b-c9-* branch
```

Preserve the refs for #455 until T00-GOV is accepted.

## Non-negotiable engineering rules

- Treat code, DB constraints, migrations, effective config, Git history, full Actions logs and reproducible tests as evidence. PR/status prose is not proof.
- Missing, malformed, stale, unknown or unverifiable safety input denies execution.
- After a Provider request may have reached the service, every downstream failure must be persisted, surfaced, stop later calls and forbid automatic Provider retry.
- Never treat `IntegrityError` as an idempotent no-op without verifying the expected constraint and every stored business field.
- Do not swallow persistence failures or convert required empty evidence into success.
- Do not call Provider, create a real canary authorization, start persistent scheduler, or enable Candidate, Formal, Lock or Production.
- A canary fails if any required delta is zero, lineage is broken, a non-finite value appears, or independent hash recomputation differs.
- Valid split-line behavior such as `2/2.5 -> 2.25` is intentional and tested; do not modify it without contrary Provider evidence.
- `src/w2/monitoring/readiness.py` is not a live Provider entrypoint; its known issue is status aggregation.
- Completion statements must name covered and uncovered audit perspectives.
- Same-origin tests do not replace an independent mathematical/business oracle.
- One business fact has one computation authority, or explicitly named/versioned different definitions.
- Historical identity/hash values are immutable unless an approved versioned migration/compatibility plan exists.

## R5 computation-authority rules

T00 now covers R1–R5. R5 scans duplicated canonical serialization, hashes, formulas, taxonomies, precision/rounding and misleading same-name classes.

For canonical JSON/hash work:

1. Inventory every persisted and ephemeral hash domain before changing serialization.
2. Do not choose `ensure_ascii=True` or `False` by preference.
3. Freeze a versioned contract for UTF-8, key ordering, separators, Unicode, `allow_nan=False`, numbers, Decimal, date/datetime and unsupported types.
4. Do not rewrite historical hashes in place.
5. Establish one versioned primitive under `src/w2/domain/` and migrate callers with explicit compatibility rules.
6. Use independent golden vectors/oracles for Chinese text, NaN/Infinity rejection, numeric edge cases, pair hash and bootstrap seed.
7. CI must reject a new unapproved canonical/hash serializer.

Other R5 concepts—fair odds/decimal odds, market taxonomy, Brier/ECE and read-model naming—belong to Gate C unless T00 proves they affect Gate A evidence.

## Perspective-registry growth

For every incident, anomaly, canary failure, staging/production deviation or new audit finding:

1. Identify the registered perspective that should have caught it.
2. If none reasonably applies, add a new row in the same remediation.
3. Record owner, independent reviewer, evidence, closing gate and regression test.
4. Do not close while `UNMAPPED_PERSPECTIVE > 0`.
5. Without an independent reviewer, classify the result as `SELF_REVIEWED_ONLY` or `PARTIAL`.

R5 is the first example of this self-expansion rule.

## Incident-driven emergency fixes

An emergency fix may contain the incident, but is not finally closed until an independent post-incident review covers R1–R4 and any affected extra perspectives. If the fix touches hash, identity, formula, taxonomy or precision, R5 is mandatory.

Until complete:

```text
CONTAINED_PENDING_POST_INCIDENT_REVIEW
```

## Workflow governance red line

- Never create a workflow that pushes to its own or another open business PR branch.
- Never use `contents: write` in a business-code PR to rewrite implementation.
- Never configure a bot author and run `git push` from CI to mutate the reviewed branch.
- Workflow permission changes require a separate independent governance review.
- Implementation changes must be ordinary local edits, commits, pushes and Draft PRs.

## Current execution order

```text
GitHub local sync
-> T00-GOV
-> T00-SAFE R1-R5 + asset inventory
-> versioned canonical serialization authority/migration
-> hunk review of e875050f
-> trusted-main C9 rebuild in a new Draft PR
-> remaining Gate A one-shot-canary blockers
-> fake-Provider offline rehearsal
-> context/evidence sync
-> independent second review
-> human canary authorization decision
```

Codex/agents must stop before the human authorization decision and report:

```text
REAL_PROVIDER_CALL_EXECUTED = false
REAL_CANARY_AUTHORIZATION_CREATED = false
AUTO_MERGE_EXECUTED = false
READY_FOR_INDEPENDENT_SECOND_REVIEW = true|false
```
