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

## Staging release record · 2026-07-15

- Release: `staging-3d67a769704e544fb544979c96cf3162328d090c`.
- API, Web, worker and scheduler revisions are all
  `3d67a769704e544fb544979c96cf3162328d090c`.
- Database revision: `0023_create_checkpoint_refresh_schedule (head)`; the database was already at
  the target head, so the release added no migration data writes.
- The rollback manifest is stored outside Git at
  `/opt/w2/shared/rollback-manifest-3d67a769704e544fb544979c96cf3162328d090c.json` with mode 600.
  Previous images and release metadata remain available; rollback was not performed.
- Staging operations authentication is enabled with a service credential and evidence-based Compose
  network CIDRs. Credentials and environment contents must never be copied into repository context.
- Initial cold-cache concurrency produced seven transient 504 responses. This is an open performance
  warning, not a reason to raise timeouts without evidence and not an authorization to modify decision
  thresholds.
- Production remains unchanged. `RECOMMEND`, recommendation locks, league enablement and model
  artifacts remain unchanged.
