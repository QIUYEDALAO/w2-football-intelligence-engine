# W2 GitHub Context

> This is the short GitHub-maintained context entrypoint for Web Sol and Codex.
> Use this as the single human-facing entrypoint. Follow linked evidence files
> only when a review question needs the detail.

## Purpose

This file exists so project context is maintained in GitHub, not only in chat
memory. It records the current collaboration protocol, active review sources,
and hard boundaries that new Sol/Codex sessions must preserve.

## Human Review Entry

For Web Sol, this file is the first and only required context file.

Do not start by reading the older long context files. They remain in the
repository as internal evidence and CI-tested project records.

When more detail is required, use this order:

1. Relevant PR description or stage report.
2. `reports/W2_CURRENT_HANDOFF.md` for runtime state and blockers.
3. `reports/W2_ROADMAP_STATUS.json` for machine-readable gate progress.
4. `docs/W2_MASTER_ROADMAP.md` for original long-term product scope.
5. Chat history only as supplemental context.

## Current Collaboration Protocol

The user-approved workflow is:

1. Web Sol creates the stage plan, product boundaries, and acceptance criteria.
2. Codex implements continuously inside the approved stage, fixes bugs, runs
   tests, validates staging when authorized, and writes evidence reports.
3. Web Sol reviews by stage, not after every small code change.
4. Codex applies Sol review feedback with minimal scoped changes.
5. Web Sol gives final confirmation.
6. Codex then commits, pushes, opens or updates PRs, and records the result.

## Fixed Boundaries

- Do not change Dashboard UI, layout, CSS, routing, or information architecture
  unless the user explicitly approves that stage.
- Keep AH formal recommendation, OU formal recommendation, LMM numeric
  adjustment, order locking, and production recommendation disabled unless the
  user explicitly approves activation.
- Do not add new factors or change model thresholds/directions without a Sol
  stage plan and explicit user approval.
- Do not treat retrospective evidence as forward evidence.
- Do not use GitHub as a stream of half-finished small fixes unless the user asks
  to sync; prefer stage-level commits and PRs.

## Active GitHub References

- Main context branch currently used by the local primary workspace:
  `chore/stage7i-24h-observation`
- Current evidence-chain draft PR:
  `https://github.com/QIUYEDALAO/w2-football-intelligence-engine/pull/353`
- PR #353 branch:
  `codex/w2-offline-shadow-evidence`

## How Sol Should Review

When Web Sol reviews the project, ask it to:

1. Read this file first.
2. Inspect the relevant PR or stage report.
3. Open older context files only if this file or the PR explicitly points to
   them for evidence.
4. Return a bounded stage instruction for Codex with:
   - allowed files or modules,
   - explicit non-goals,
   - required tests,
   - staging/deploy permission,
   - stop conditions.

## Last Updated

- Date: 2026-07-20
- Reason: user requested GitHub-maintained context for Sol review and Codex
  instruction handoff.
