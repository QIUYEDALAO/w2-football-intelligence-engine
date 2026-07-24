# W2 Next Action

## Authority

The single authority for architecture-convergence status, task order and
acceptance is:

`docs/operations/architecture_convergence/W2_ARCHITECTURE_CONVERGENCE_MASTER_CHECKLIST.md`

Before any GitHub secondary review, the mandatory first read is:

`docs/operations/architecture_convergence/W2_GITHUB_SECONDARY_REVIEW_PROTOCOL.md`

Read that protocol from the PR exact head when a PR is under review, then follow
`PROJECT_STATE.yaml.context_read_order`. A review may not start from a Codex
receipt or handoff summary alone.

This file only points at the current task. It must not restate SHAs, CI runs or
task status that the checklist already owns.

## Current gate

Feature development is frozen. The only work in flight is the architecture
convergence programme.

Architecture convergence is complete through `ARCH-HYGIENE-02`. The master
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
ARCH-P1-04A -> ARCH-P1-04B -> ARCH-P1-04C -> ARCH-P1-03 -> ARCH-P1-05
  -> ARCH-P1-06 -> ARCH-P1-07 -> ARCH-P1-08
```

The current and next task is **ARCH-P1-04A: evaluation persistence and the
write-side projection pipeline**. ARCH-HYGIENE-02 has passed external review
and is merged. Until ARCH-P1-04A is externally reviewed and merged:

1. Persist event-driven prematch evaluations and write the shadow
   `read_model_checkpoint` projection without switching any read path.
2. Keep worker/ingestion free of new `w2.api` dependencies and move write-side
   projection logic out of the API package.
3. Do not begin `ARCH-P1-04B`, change the database schema, add a fallback, or
   alter any safety switch.

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
