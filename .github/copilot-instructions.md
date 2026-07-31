# W2 GitHub Copilot Instructions

Read `/AI_PROJECT_CONTEXT.md`, `/PROJECT_STATE.yaml`, `/NEXT_ACTION.md`, `/AGENTS.md`, and `/docs/operations/W2_AUDIT_PERSPECTIVE_REGISTRY.md` before proposing or changing code. GitHub Issue #454 v3 is the execution authority; Issue #455 is the workflow-governance incident authority.

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
7. Every completion statement names covered and uncovered audit perspectives.
8. Same-origin tests do not replace an independent mathematical or business oracle.

## Audit-perspective growth

For every incident, anomaly, canary failure, staging/production deviation, or new audit finding:

- identify which registered perspective should have caught it;
- update that perspective's evidence and coverage boundary;
- if none applies, add a new perspective in the same remediation;
- record the independent reviewer and closing gate;
- do not close while `UNMAPPED_PERSPECTIVE > 0`.

Major perspective closure cannot rely only on the implementer or the same-origin specification/tests. Without an independent reviewer, classify the result as `SELF_REVIEWED_ONLY` or `PARTIAL`.

## Incident-driven emergency fixes

An emergency fix may restore service, but it is not finally closed until a post-incident review covers at least R1-R4:

```text
R1 Default allow / missing authority
R2 Silent failure / failure downgrade
R3 External side effect / local-state non-atomicity
R4 Authority split / concurrency / identity drift
```

Review any additionally affected data, time, security, recovery, or observability perspectives. Until complete, the state is:

```text
CONTAINED_PENDING_POST_INCIDENT_REVIEW
```

Record the emergency commit, omitted failure paths, registry update, independent reviewer, and regression guards.

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
