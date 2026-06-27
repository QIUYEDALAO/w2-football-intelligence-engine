# W2 August League Validation Plan

Status: planning only. This runbook does not enable live collection, production
release, FORMAL/CANDIDATE, or any provider quota upgrade.

## Scope

P2 prepares the August league validation campaign for S1/S2 shadow evaluation.
It is not a launch decision and it is not a betting or trading workflow.

Allowed scope:

- Use existing disabled top-five league profiles as planning candidates.
- Keep runtime competition whitelist unchanged until a separate approved PR.
- Keep all runtime outputs at `ANALYSIS_ONLY`, `ANALYSIS_PICK`, `WATCH`, or
  `NO_RECOMMENDATION`.
- Use read-only validation reports and dry-run artifacts.
- Record why S2 has or has not met the frozen portfolio gate.

Forbidden scope:

- No production deployment.
- No API-Football plan upgrade.
- No payment, funds, or credential changes.
- No staging seed or demo enablement.
- No true S2 backtest in this planning PR.
- No runtime `beats_market=true`.
- No FORMAL/CANDIDATE unlock.
- No runtime whitelist expansion in this PR.

## Candidate Competitions

The initial planning pool is the existing disabled top-five league profiles:

- `premier_league`
- `la_liga`
- `serie_a`
- `bundesliga`
- `ligue_1`

These profiles remain disabled. A later runtime PR may propose enabling one or
more competitions only after the checks below are satisfied.

## Readiness Checks

Before any league is enabled for collection, the operator must document:

- Provider league ID and season mapping.
- Fixture discovery coverage for the target season.
- Odds observation coverage and bookmaker depth.
- Lineups availability by phase.
- xG/statistics availability and mapping coverage.
- Historical settled AH/OU availability.
- API-Football quota impact under the 7500/day default budget.
- Reserve bucket safety under the 1500 reserve policy.
- Rollback path that disables the competition without deleting data.

## Validation Goal

The portfolio-level S2 gate remains frozen:

- Covered settled sample `>= 200`.
- Advantage over the devig market baseline is distinguishable from noise.
- Time split passes.
- Holdout replication passes.
- Forward shadow passes.

Until all checks pass, W2 remains analysis-only. A failure to clear the gate is
an acceptable outcome and should be reported as such.

## Evidence Pack

Each future league enablement PR must include:

- `GET /v1/version` and release SHA.
- `GET /v1/validation/summary`.
- `scripts/run_w2_handicap_walkforward.py --dry-run`.
- Quota policy state from `/v1/providers/status`.
- A competition mapping audit.
- A statement that FORMAL/CANDIDATE remain disabled.
- A statement that runtime `beats_market` remains false.

## Stop Conditions

Stop immediately if any step requires `.env` access, provider credential change,
payment action, production deploy, destructive migration, live quota burn for a
simulation, FORMAL/CANDIDATE unlock, or runtime `beats_market=true`.
