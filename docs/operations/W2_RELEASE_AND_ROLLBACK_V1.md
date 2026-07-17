# W2 Release and Rollback V1

Release governance objects:

- ModelCard
- ReleaseCandidate
- ReleaseApproval
- RollbackManifest
- ChangeFreeze
- ReleaseAudit

Rules:

- New versions require complete walk-forward, ablation, calibration, and Shadow.
- Old artifacts are immutable.
- Single-match results cannot trigger release.
- Gate 4/5/6 must be closed before production release.
- Stage 15A publishes no model.
- P2 governance documents do not authorize production release, FORMAL/CANDIDATE,
  runtime `beats_market=true`, or runtime competition whitelist expansion.
- Analysis-only is an acceptable long-term state when S2 evidence is
  insufficient.
