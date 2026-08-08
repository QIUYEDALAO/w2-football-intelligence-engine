# W2 Current Context

Current mutable authority is `origin/context/current`.

## Current decision

```text
PRODUCT = W2 Football Intelligence
ROUND_1 = PASS
ROUND_2 = PASS_WITH_TERMINAL_PROVIDER_PLAN_RESTRICTION
FREE_PLAN_BRIDGE_CONTROLLED_RUNTIME = PASS
ACTIVE_NEXT_ACTION = AWAIT_OWNER_ROUND_3_OR_BIG_FIVE_COLLECTION_DECISION
FREE_BRIDGE_MODE = SHADOW_ONLY
ACTIVE_WHITELIST = 13_UNCHANGED
ROUND_3 = NOT_STARTED
```

Read current authority in this order:

```text
1. CURRENT_STATE.yaml
2. NEXT_ACTION.md
3. FREE_PLAN_BRIDGE_CONTROLLED_RUNTIME_RECEIPT.md
4. FREE_PLAN_DAILY_CALL_BUDGET.md
5. REPOSITORY_HYGIENE_POLICY.md
```

## Closed runtime task

PR #495 ended at head `5d1761106d1bc1b9c55e1ef923b5603ef490c027`
and merged as `eccab2542fa68bb0ae557e6f073dfdd927297f07`. It fixed
the quota double-reserve defect and established the Free fixture-centric
planner and canonical evidence adapter.

The one authorized existing-scheduler integration was PR #496, ending at
`a55111b4955f70c84539ac44d07858a8d80e7f81` and merging as final
`main` SHA `c241b877a4168659f465163108f7a53fb8fd82a5`. All local,
PR Fast, Release Candidate, image smoke and main-promotion gates passed.

The immutable `c241b877…` release is deployed to W2 staging with bridge mode
`SHADOW_ONLY`. The code default remains `OFF`; the deployment feature flag
is the one-step rollback control.

Real acceptance used two new Provider calls: one no-season date discovery and
one single-fixture odds call for existing-whitelist fixture `1575448` in
`primeira_liga`. It produced canonical identity plus 182 AH and 240 OU
observations across 14 bookmakers, with all 464 market rows linked to endpoint
capture and raw payload evidence. Provider daily limit was 100 and remaining
was 93. A same-data rerun and the first post-restart scheduler run both used
zero Provider calls.

The rollback proof switched the bridge to `OFF`, observed zero Provider calls,
preserved all raw/capture/identity/market evidence and kept the exact 13
whitelist. The bridge was then restored to `SHADOW_ONLY`; all six services
were running. Four audit-only league IDs remain absent from runtime scope.

The completed result is documented in
`FREE_PLAN_BRIDGE_CONTROLLED_RUNTIME_RECEIPT.md`. The current state is waiting
for an owner decision; do not rerun this acceptance or begin Round 3 from the
consumed authorization.

Permanent guards remain: intelligence-first semantics; no paid renewal or new
Provider action without new authority; active whitelist exact 13; V4
diagnostic-only; no betting-edge/opportunity claim; Candidate/Formal/Lock/
Production OFF; H permanently closed; no real-money execution; Round 3 not
started.
