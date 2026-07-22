# W2 Analysis Recommendation Closure Task Context - 2026-07-21

## User Instruction

Run `W2 ANALYSIS-RECOMMENDATION-CLOSURE`.

## Scope

This is not a fixture intake, provider, or deployment-first task. It must use already captured staging data by default and must keep provider calls at zero unless existing observations cannot be read.

Required closure work:

- Freeze actual Git and staging baselines.
- Create a new worktree at `/Users/liudehua/.hermes/workspace/w2-analysis-recommendation-closure`.
- Use branch `codex/w2-analysis-recommendation-closure`.
- Rebuild non-empty Allsvenskan team crosswalk review package.
- Generate fixture-scoped factor readiness for fixtures `1494224` and `1494218`.
- Bind real fixture identities and odds observations into the canonical analysis path.
- Freeze model probability, market devig probability, delta, EV, uncertainty, quote identity, evidence manifests, and V3 outcomes.
- Keep public canonical output separate from diagnostic-only analysis output.
- Keep recommendations, locks, OFFICIAL settlement, and cohort writes at zero.

## Runtime Safety

- Scheduler must remain stopped.
- `W2_PROVIDER_SCHEDULER_ENABLED=false`.
- `W2_FUTURE_FIXTURE_REFRESH_ENABLED=false`.
- `W2_PROVIDER_CALLS_DISABLED=true`.
- Default provider calls for this task: `0`.

## Final Allowed States

- `ANALYSIS_RECOMMENDATION_CHAIN_VALIDATED`
- `ANALYSIS_CHAIN_TEAM_IDENTITY_REVIEW_REQUIRED`
- `ANALYSIS_CHAIN_MODEL_INPUT_REMEDIATION_REQUIRED`

Always retained:

- `FORMAL_DISABLED`
- `LOCK_DISABLED`
- `PRODUCTION_DISABLED`
- `MANUAL_APPROVAL_REQUIRED`

## GitHub Synchronization

- Repository: `QIUYEDALAO/w2-football-intelligence-engine`
- Current PR: `#369`
- Context-only update: yes
- CI required: no
