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

Historical architecture completion remains recorded through `ARCH-P1-03C`.
`ARCH-P1-05` is paused behind the governance/remediation sequence below. The
master checklist owns all completion evidence and repository/staging coordinates.

W2_DYNAMIC_PREMATCH_V1 is `locally_verified`.
W2_DYNAMIC_PREMATCH_STAGING is authorized.

That feature phase is deployed to staging but is not being advanced during the
freeze. The real confirmed-lineup canary is now a separate ops acceptance task
and is no longer a prerequisite for any architecture task. Lineup remains
`LINEUP_ADVISORY_ONLY`; AH, totals and lambda adjustments are all exactly `0.0`.

## Next execution

Execute the P1 tasks strictly in the order recorded in the master checklist:

```text
ARCH-P1-03B-R1 PREFLIGHT
-> ARCH-OBS-01
-> ARCH-EVIDENCE-01
-> ARCH-DONE-REAUDIT
-> ARCH-P1-05
```

**ARCH-P1-04D** is merged and its closure records `DONE`; main POST passed at
`0cb267baa62abe547802bca27771a8fe1c26a0db`. `ARCH-P1-03` was split by external
decision into **ARCH-P1-03A** (team side, `DONE`; implementation PR #400 merged
as `bcd2c5e490a99426a0451de7f92362c1a76b2960`) and **ARCH-P1-03B** (player
side, `DONE`; implementation PR #402 merged as
`df8fc4578fb4d45e2fb7afb95f58748f459a69a8`, accepted head
`bfce636dc245ab93f9f4d92e77699bf1689f127b`). **ARCH-P1-03C** is also `DONE`;
its implementation PR #404 merged as
`4e310e87def0e6e44e0fe69fa0c07f776126a6fc`, with accepted head
`8adc8d482aefd7d31063030f0b682458c58c17a2`. **ARCH-GOVERNANCE-02** is
`DONE`; implementation PR #406 merged as
`cf5d6ea2cca600e31d4058b7d359b271d12d1f04`, with accepted head
`7607c2336fd1507d151d5291b95ae6892d16f94f`. **ARCH-P1-04D-R1** is `DONE`;
implementation PR #408 merged as
`09ece0204bed1289986e20d6a1cff842cb2f0864`, with accepted head
`47a7c823967cf4ea98221556d96e8a30a948318d`. **ARCH-GOVERNANCE-03** is
`DONE`. Its initial implementation PR #410 was accepted at
`f7043f6a5fc0e020d11e19672a70658a66cc420f` with Full CI `30237236245` and
merged as `bfdd79b3814008d9988f8f5d76d566145188e1e4`. Final remediation PR #411
was accepted at `688b4c132d719d7fd282dc7d85598a594666617e` with Full CI
`30240556366` and merged as `f891f25dac1c0b663facab94dc0e05c54b84f4eb`;
main push `CI_REQUIRED` run `30241678736` and POST run `30241678744` passed.
Generator hotfix PR #415 was accepted at
`8981cab16360d37d75a6f49becba687bbe6e3830`, passed Full CI `30258743731`,
and merged as `d69d3ccb835bb56fbe4930d361fe64c90ce6e8fa`; main
`CI_REQUIRED` run `30259420198` and POST run `30259420152` passed.
**ARCH-P1-03B-R1** remains `NOT_STARTED`; PR #414 remains Draft with its
BLOCKED baseline and must not begin production implementation. The only
permitted next step is to rebase the same read-only
`W2_PR_KIND: PREFLIGHT` that adds and validates the spec and baseline receipt
with qualifying real input and runtime/SQL evidence; production identity
repository changes are forbidden until that gate opens.
The checker enforces the full lifecycle ACL (including rename/delete),
binds baseline evidence to its frozen subject head, and makes Implementation PRE
query GitHub directly for same-head FULL CI, detached result/evidence artifacts,
and external PASS Review. The later Closure is the only PR allowed to add the
final attestation; POST cross-checks its merged implementation coordinates.
**ARCH-P1-05** remains `NOT_STARTED` and must not begin
until every inserted predecessor has completed its implementation and closure.
The checklist owns each task's PR number, status and CI evidence.

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
