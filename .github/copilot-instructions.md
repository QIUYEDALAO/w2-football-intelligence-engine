# W2 GitHub Copilot Instructions

Read `/AI_PROJECT_CONTEXT.md`, `/PROJECT_STATE.yaml`, `/NEXT_ACTION.md`, and `/AGENTS.md` before proposing or changing code. GitHub Issue #454 v3 is the execution authority; Issue #455 is the workflow-governance incident authority.

## Source and branch rules

- First synchronize the repository from GitHub to a local clean worktree.
- Verify `origin/main` and record its exact SHA before editing.
- Do not work from PR #453 or any `agent/eval-02b-c9-*` branch.
- Do not merge, rebase, or cherry-pick `e875050f6bc0286aed389aadfce1e17b2063635a` or any automation-authored remediation commit.
- PR #453 is quarantined evidence and must never be merged.

## Current order

```text
T00-GOV
T00-SAFE for R1-R4
trusted-main C9 rebuild in a new Draft PR
Gate A one-shot-canary remediation
offline fake-Provider rehearsal
independent second review
```

## Invariants

1. Missing, malformed, stale, unknown, or unverifiable safety inputs deny execution.
2. Failures after a possible external Provider side effect are persisted, surfaced, stop later calls, and forbid automatic Provider retry.
3. Idempotency is accepted only after the expected constraint and every stored business field are verified.
4. Required zero evidence is failure, not normal completion.
5. A canary passes only when every required delta is positive and one full lineage is reconciled.
6. Context and status documents follow verified code/GitHub evidence; they do not create authority.

## Workflow prohibition

Do not add any workflow that:

- uses `contents: write` to modify business implementation in the same PR;
- pushes to its own source branch or another open business PR branch;
- configures a bot author and executes `git push` to rewrite the reviewed branch.

All source changes must be normal local edits, commits, pushes, and Draft PRs.

## Operational stop line

Provider calls, real canary authorization, persistent scheduler, Candidate, Formal, Lock, Production, and automatic merge are not authorized. Stop after the offline evidence package and report:

```text
REAL_PROVIDER_CALL_EXECUTED = false
REAL_CANARY_AUTHORIZATION_CREATED = false
AUTO_MERGE_EXECUTED = false
READY_FOR_INDEPENDENT_SECOND_REVIEW = true|false
```

Do not modify the tested split-line mapping `2/2.5 -> 2.25` without real contrary Provider evidence. `readiness.py` is a status calculator, not a Provider live-call entrypoint.
