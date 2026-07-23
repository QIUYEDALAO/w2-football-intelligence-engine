# W2 Next Action

## Authority

The single authority for architecture-convergence status, task order and
acceptance is:

`docs/operations/architecture_convergence/W2_ARCHITECTURE_CONVERGENCE_MASTER_CHECKLIST.md`

This file only points at the current task. It must not restate SHAs, CI runs or
task status that the checklist already owns.

## Current gate

Feature development is frozen. The only work in flight is the architecture
convergence programme.

Architecture convergence is complete through `ARCH-P1-02`. The master
checklist owns all completion evidence and repository/staging coordinates.

W2_DYNAMIC_PREMATCH_V1 is `locally_verified`.
W2_DYNAMIC_PREMATCH_STAGING is authorized.

That feature phase is deployed to staging but is not being advanced during the
freeze. The real confirmed-lineup canary is now a separate ops acceptance task
and is no longer a prerequisite for any architecture task. Lineup remains
`LINEUP_ADVISORY_ONLY`; AH, totals and lambda adjustments are all exactly `0.0`.

## Next execution

Execute the P1 tasks strictly in the order recorded in the master checklist:

```text
ARCH-HYGIENE-01 -> ARCH-HYGIENE-02
  -> ARCH-P1-04A -> ARCH-P1-04B -> ARCH-P1-04C -> ARCH-P1-03
  -> ARCH-P1-05 -> ARCH-P1-06 -> ARCH-P1-07 -> ARCH-P1-08
```

The current and next task is **ARCH-HYGIENE-01: generated audit artifacts exit
Git**. Its prerequisite checklist-revision PR is merged and implementation is
in progress. Until its PR is externally reviewed and merged:

1. Limit the task to its checklist contract: classify generated versus
   human-maintained audit files, move generator defaults out of Git-tracked
   paths, record `audit_generator_sha` as the generator-code version, derive
   `source_review_sha` as the audited-tree version dynamically from the current
   Git HEAD and verify it matches the generation HEAD, remove compatibility
   aliases and stale placeholders, and add both ignore and static guards.
2. A task is finished only when its acceptance counters are zero, generator
   runs leave Git clean, full CI is green, the PR is merged, and the checklist
   status is flipped to `DONE`.
3. Do not begin `ARCH-HYGIENE-02`, modify production behavior, change database
   state, or alter any safety switch.

`ARCH-P1-05` carries a pre-approved conditional bring-forward: if the
`ARCH-P1-04` series' staging acceptance keeps failing because of on-server
image builds, it may be executed before `ARCH-P1-04A` without asking again,
provided the trigger reason is recorded in the checklist.

## Deferred ops work (not part of the freeze)

1. In a real official-lineup window, run one bounded `lineups` +
   post-confirmation `odds` canary for one fixture, proving
   `LINEUP_CONFIRMED → LINEUP_READY_MARKET_REFRESH_PENDING → fresh exact quote
   → re-evaluation`, including `SUPERSEDED` evidence.
2. After that canary, restore provider calls, scheduler and future-fixture
   refresh to disabled and record the zero-delta evidence.
3. Materialize reviewed team crosswalks, provider/player identities and as-of
   Transfermarkt valuations, then recompute league-level coverage before
   claiming any real replacement-value feature coverage.
4. Run leakage-safe rolling-origin ablation and forward shadow validation for
   lineup adjustments. Do not enable numerical AH/OU/lambda adjustment without
   the predeclared evidence and explicit manual approval.

Formal recommendation, recommendation lock, OFFICIAL capture, champion switch
and Production remain unauthorized. Manual approval is required for any of
those transitions.
