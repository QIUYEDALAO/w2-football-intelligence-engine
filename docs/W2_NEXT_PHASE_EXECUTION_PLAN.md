# W2 Next Phase Execution Plan

## 2026-07-19 Current Local Context

This section supersedes the historical PR #142–#151 sequencing below for current
local execution.

- Local `main` and the active branch both point to
  `8e171dc05efc2fc3a512fff2c334d123d01db922`.
- The unchanged GitHub tracking baseline is `github-w2/main@a80bcca`; no GitHub
  synchronization is authorized by the current task.
- The latest accepted Dashboard implementation recorded locally is
  `01f8a75aa87cfaf58d0db3635eefc02016830d87`.
- The next implementation package is the lineup-change and multi-market decision
  plan in
  [W2_LINEUP_MULTI_MARKET_EXECUTION_PLAN_20260719.md](consolidation/W2_LINEUP_MULTI_MARKET_EXECUTION_PLAN_20260719.md).
- The current Dashboard layout is frozen. Work is limited to source-backed data,
  decision semantics and concise evidence inside the existing layout.
- `ANALYSIS_PICK` remains outcome-tracked but never lock-eligible. `RECOMMEND`,
  lock, OFFICIAL, champion and production writes remain unchanged.
- This package changes data contracts and runtime decisions; after its one staging
  canary, the three consecutive 09:00 read-only cycles restart from `0/3`.

The older strategy and PR route remain below only as historical context. Where
they conflict with this section or Decision Contract V2, this section wins.

## Status

W2 is moving from an engineering pipeline into a matchday operating system. The
Decision Contract V2 migration is the execution entry point for this phase.
Existing stage checkers remain as regression safety nets, but W2 will not add
Stage 16 or another `check_w2_stageN.py` gate.

The original basis documents are archived under `docs/consolidation/`. This
file is the execution summary and the single entry document for PR sequencing.

## Goal

Upgrade W2 from scattered pipeline outputs into a daily football operations
system that produces one DecisionCard per fixture, renders the dashboard from
that card, preserves auditability, and separates staging exploration from
production trust.

## Core Strategy

W2 uses staging A / production B.

- staging A: `ANALYSIS_PICK` may be displayed, outcome tracked, and considered
  staging `lock_eligible` after completeness gates pass. This lets staging
  exercise dashboard, lock, settlement, and replay paths while collecting
  samples.
- production B: production `lock_eligible` requires `RECOMMEND`, READY data,
  future kickoff, complete market data, and forward +EV evidence. Plain
  `ANALYSIS_PICK` is not a production actionable recommendation.

`ANALYSIS_PICK` means analysis recommendation. `RECOMMEND` means production
formal recommendation.

## DecisionCard Contract

DecisionCard is the unified card envelope for every fixture. It owns the
decision tier, data status, lifecycle status, outcome tracking flag,
recommendation id, model version, provenance, pick/non-pick details, one-line
explanation, and card hash.

`lock_eligible` is an environment policy overlay. It is not included in the
card hash, so the same core card and model version keep the same hash in staging
and production even when the environment policy produces different eligibility.

## Dashboard Rule

Dashboard only renders DecisionCard data. It must not infer a new card tier at
read time from legacy field combinations such as `formal_recommendation`,
`candidate`, `decision`, or `analysis_decision`.

During migration, legacy fallback is allowed only for historical read
compatibility. New outputs must provide `decision_tier`.

## Controlled Refresh Rule

Controlled refresh is limited to status, fixtures, odds, and lineups. W2 must
not restore a 60-second loop or broad endpoint refresh. Statistics, injuries,
H2H, history, and xG automatic refresh remain out of scope until explicitly
approved behind budget, allowlist, ledger, and deduplication controls.

## PR Route

- #142 W2-STEP0 + DC skeleton
- #143 Decision Contract full wiring
- #144 Data Readiness Gate
- #145 Controlled Refresh Matchday Ticks
- #146 w2-matchday
- #147 DashboardDayView API
- #148 Dashboard L1
- #149 Diagnostics Drawer
- #150 Replay/Audit front door
- #151 Final acceptance

## PR #142 Scope

PR #142 freezes the stage narrative, archives the consolidation documents,
adds the Decision Contract V2 skeleton, introduces staging A / production B
policy functions, adds read-only legacy shim compatibility, and changes the
dashboard recommendation reader to prefer `decision_tier`.

It does not call providers, write databases, restart scheduler, deploy
production, write locks, write settlements, delete legacy fields, delete stage
checkers, add Stage 16, or perform a full dashboard rewrite.
