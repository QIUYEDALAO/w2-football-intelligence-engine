# W2 Acceptance Runbook

This runbook defines the offline acceptance suite for the current W2 next-phase
mainline. It is a side-effect-free gate: it must not call providers, read or
write staging DB state, deploy services, restart schedulers, or write locks,
checkpoints, settlements, runtime artifacts, reports, caches, logs, env files, or
credential material.

## Current Mainline

- Decision Contract V2: `DecisionTier`, `DataStatus`, `LifecycleStatus`, and
  `DecisionCard` invariants are the decision surface.
- Data Readiness Gate: every card carries readiness status, reason, action, and
  next evaluation metadata.
- Controlled Refresh Planner: matchday ticks are planned against
  `status/fixtures/odds/lineups` only.
- `w2-matchday`: dry-run and controlled-run safety gates expose planned work
  without execution.
- Dashboard DayView: cards, counts, freshness, navigation, and degradation state
  are read from the Decision Contract surface.
- L1/L2 Dashboard: boss-view first screen and collapsed diagnostics share the
  same DayView input.
- Degradation and navigation: empty day, stale data, provider budget, and date
  replay states are explicit.
- Environment stamp: staging A and production B are visibly separated.
- Replay skeleton: local JSON replay front door verifies envelope, gaps,
  outcome tracking, and card hash status without DB access.

## Acceptance Policy

Staging A is for running the system and accumulating evidence. It may show
`ANALYSIS_PICK` cards as lock approval candidates only when `lock_eligible=true`,
and those cards must be marked `staging-only`, `分析参考`, `非稳赢`, and
`production 动作需 RECOMMEND`.

Production B is the credibility boundary. Production formal action remains
`RECOMMEND` only. `ANALYSIS_PICK` can be displayed and replayed, but it is not a
production action.

## Read-Only Commands

These commands are safe for this offline suite:

```bash
uv run --python 3.12 python scripts/check_w2_acceptance.py
uv run --python 3.12 python scripts/check_w2_acceptance.py --json
uv run --with pytest --python 3.12 python -m pytest -q tests/unit/test_w2_acceptance_checker.py
uv run --python 3.12 python scripts/check_tracked_outputs.py
uv run --python 3.12 python scripts/check_w2_all.py
uv run --python 3.12 ruff check .
uv run --python 3.12 python tests/secret_scan.py
```

The acceptance checker reads only local fixtures under
`tests/fixtures/w2_acceptance/` and calls side-effect-free builders.

## Approval-Required Actions

These actions require separate user approval and are not part of this PR:

- Provider calls or provider refresh/backfill.
- Staging DB reads or any DB writes.
- Checkpoint writes.
- Staging or production deploys.
- Scheduler restart or restart policy restore.
- Lock capture writes or settlement writes.
- Real controlled refresh execution.
- Real replay DB front door.
- Historical locked snapshot reads or rewrites.
- Environment, credential, or permission changes.

## Daily Matchday Flow

1. Run matchday dry-run to inspect fixtures, DecisionCards, lock candidates, and
   side-effect flags.
2. Run controlled-refresh plan in dry-run mode and confirm endpoint allowlist,
   tick schedule, projected calls, and skipped endpoints.
3. Inspect DayView and L1 boss-view HTML for counts, readiness, policy stamp,
   degradation, and navigation.
4. Run report/audit dry-run checks only when explicitly side-effect-free.
5. Run replay skeleton with local DayView and local outcomes to verify outcome
   tracking and card hash status.
6. Escalate any provider, DB, deploy, scheduler, lock, settlement, checkpoint,
   or real replay operation for explicit approval.

## WARN_ONLY vs BLOCKER

`WARN_ONLY` means the offline suite can still finish, but the operator should
read the warning before using the output. Examples: missing optional audit
manifest in replay skeleton, no local outcomes supplied, or no lock candidates
on a quiet day.

`BLOCKER` means the offline acceptance contract failed. Examples: provider calls
or DB writes are non-zero, a forbidden endpoint appears in the effective
allowlist, `ANALYSIS_PICK` lacks `分析参考` or `非稳赢`, raw provider payload leaks
into the boss first screen, or any Stage 16 checker appears.
