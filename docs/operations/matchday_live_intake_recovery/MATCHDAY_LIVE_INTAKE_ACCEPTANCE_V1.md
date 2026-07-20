# MATCHDAY_LIVE_INTAKE_ACCEPTANCE_V1

Final status: `MATCHDAY_LIVE_INTAKE_REMEDIATION_REQUIRED`.

Required answers:

1. LiveNetworkDisabledError reason code: `LIVE_GATE_API_KEY_NOT_VISIBLE`
2. Function/process: worker -> `w2.providers.api_football.ApiFootballClient.request_live`
3. Runtime misused `ApiFootballClient.fetch()`: no
4. Worker can see API key: no
5. Provider calls disabled: no
6. Scheduler enabled: yes
7. Future fixture refresh enabled: yes
8. Competition IDs include allsvenskan: yes
9. Fixtures endpoint returned: not called, credential missing
10. Canonical fixtures written: 0
11. Provider team identities written: 0
12. Odds endpoint called fixtures: 0
13. Canonical market observations written: 0
14. Complete markets: AH 0, OU 0, 1X2 0
15. Exact quote identity formed: no
16. Team crosswalk READY/REVIEW/CONFLICT: 0/0/0
17. F5/F8 status: not evaluated because no fixture was captured
18. Model evidence blocker: `NO_EXACT_QUOTE_IDENTITY`
19. V3 outputs: none
20. Formal/lock/OFFICIAL/cohort unchanged: yes

Safety state:

- `FORMAL_DISABLED`
- `LOCK_DISABLED`
- `PRODUCTION_DISABLED`
- `MANUAL_APPROVAL_REQUIRED`
- `EXPERT_REVIEW_REQUIRED`
