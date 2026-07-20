# LIVE_INTAKE_BASELINE_V1

Status: frozen for diagnosis.

- Environment: staging
- Source baseline SHA: `037b88cd529e4c19ecf7ddc51f50106a6a996572`
- Schema revision: `0031_finalize_matchday_execution_identity`
- API `/ready`: service `READY`
- Scheduler: stopped for diagnosis
- Worker: healthy
- Provider request logs: 0
- Raw payload rows: 0
- Matchday endpoint captures: 0
- Matchday market observations: 0
- Matchday evidence manifests: 0
- Recommendations: 0
- Recommendation locks: 0

Recent allsvenskan future refresh audit rows show `fixture_count=0`, `market_snapshot_count=0`, and blocker `LiveNetworkDisabledError`.

This baseline proves service health was not equivalent to live matchday intake readiness.
