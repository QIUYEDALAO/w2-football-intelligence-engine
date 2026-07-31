# W2 Repository Agent Instructions

Before changing W2, read:

- [`AI_PROJECT_CONTEXT.md`](AI_PROJECT_CONTEXT.md)
- [`PROJECT_STATE.yaml`](PROJECT_STATE.yaml)
- [`NEXT_ACTION.md`](NEXT_ACTION.md)
- GitHub Issue **#454 v3**
- GitHub Issue **#455**

The detailed independent audit is [`docs/operations/W2_INDEPENDENT_FINAL_AUDIT_20260731.md`](docs/operations/W2_INDEPENDENT_FINAL_AUDIT_20260731.md).

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

Expected trusted main at the time this context was written:

```text
dbc8e1e8aa74a7613fd7121bf6026890c3ee06c6
```

If main moved, stop and produce a drift report before changing code. Create a clean local worktree from the independently accepted main SHA.

## Quarantined evidence

```text
PR #453 = QUARANTINED / DO NOT MERGE / DO NOT REPAIR IN PLACE
```

Do not merge, rebase, or cherry-pick:

```text
e875050f6bc0286aed389aadfce1e17b2063635a
any OpenAI Agent / github-actions bot remediation commit
any agent/eval-02b-c9-* branch
```

Preserve those refs for #455 evidence until T00-GOV is accepted.

## Non-negotiable engineering rules

- Treat code, database constraints, effective deployment configuration, Git history, full Actions logs, and reproducible tests as evidence. PR/status prose is not proof.
- Missing, malformed, stale, unknown, or unverifiable safety input denies execution.
- After a Provider request may have reached the external service, every downstream failure must be persisted, surfaced, stop further calls, and forbid automatic Provider retry.
- Never treat `IntegrityError` as an idempotent no-op without verifying the expected constraint and every stored business field.
- Do not swallow persistence failures or convert required empty evidence into success.
- Do not call Provider, create a real canary authorization, start persistent scheduler, or enable Candidate, Formal, Lock, or Production.
- A canary fails if any required delta is zero or the lineage cannot be reconciled.
- Valid split-line behavior such as `2/2.5 -> 2.25` is intentional and tested; do not modify it without real contrary Provider evidence.
- `src/w2/monitoring/readiness.py` is not a live Provider entrypoint. Its known issue is status aggregation.

## Workflow governance red line

- Never create a workflow that pushes to its own branch or another open business PR branch.
- Never use `contents: write` in a business-code PR to rewrite implementation files.
- Never configure a bot author and run `git push` from CI to mutate the reviewed branch.
- Workflow permission changes require a separate, independently reviewed governance change.
- All implementation changes must be ordinary local edits, commits, pushes, and Draft PRs.

## Current execution order

```text
GitHub local sync
-> T00-GOV
-> T00-SAFE (R1-R4)
-> hunk review of e875050f
-> trusted-main C9 rebuild in a new Draft PR
-> Gate A one-shot-canary blockers
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
