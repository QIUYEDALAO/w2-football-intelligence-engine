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

`ARCH-P0-01` … `ARCH-P0-04` and `ARCH-P1-01` are merged and accepted. `main` is
at `76201af8aad43976ffbcd7d2f72726bac4bc8106` with migration head
`0040_drop_empty_fk_components`; staging went from 144 tables to 66. PR #370 is
closed; its verified baseline reached `main` through PR #374.

W2_DYNAMIC_PREMATCH_V1 is `locally_verified`.
W2_DYNAMIC_PREMATCH_STAGING is authorized.

That feature phase is deployed to staging but is not being advanced during the
freeze. The real confirmed-lineup canary is now a separate ops acceptance task
and is no longer a prerequisite for any architecture task. Lineup remains
`LINEUP_ADVISORY_ONLY`; AH, totals and lambda adjustments are all exactly `0.0`.

## Next execution

Execute the P1 tasks strictly in the order recorded in the master checklist:

```text
ARCH-P1-02 -> ARCH-P1-04A -> ARCH-P1-04B -> ARCH-P1-04C -> ARCH-P1-03
  -> ARCH-P1-05 -> ARCH-P1-06 -> ARCH-P1-07 -> ARCH-P1-08
```

The next task is **ARCH-P1-02: odds table convergence**. One PR, one task,
independently revertible. Before starting it:

1. `git fetch github-w2 main` and branch from the latest `main`.
2. Write `Status: IN_PROGRESS` under that task in the master checklist, using
   the status format in section 四.
3. A task is finished only when full CI is green, staging acceptance passed,
   the PR is merged, and the checklist status is flipped to `DONE`.

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
