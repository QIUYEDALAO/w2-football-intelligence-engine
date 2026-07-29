# W2 Matchday Recommendation Factor Gap Context - 2026-07-21

## User Question

What factors are still required before W2 can recommend matches?

## Current Answer

Provider credential, fixture visibility, endpoint capture, and canonical odds observation are no longer the primary blockers for the controlled Allsvenskan canary.

The remaining blockers are evidence authority and readiness gates:

- Team identity review must connect provider team IDs to W2 canonical team IDs.
- F5 canonical team-history evidence must be queryable for those canonical teams before kickoff.
- F8 reviewed as-of team-value evidence must be available for the same canonical teams.
- Market evidence must be materialized into matchday evidence manifests.
- Model evidence must be validated and calibrated for the target market scope.
- V3 readiness must return a truthful non-formal outcome until all gates pass.
- Formal recommendation and lock remain blocked until manual approval.

## GitHub Synchronization

- Repository: `QIUYEDALAO/w2-football-intelligence-engine`
- Branch: `codex/w2-matchday-live-intake-recovery`
- Pull request: `#369`
- Context-only update: yes
- CI required: no

## Final State

`MANUAL_APPROVAL_REQUIRED`
