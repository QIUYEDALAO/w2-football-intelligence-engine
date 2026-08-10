# SC18 Exact 13-League Stage14 Coverage Audit

This is an audit-only report over the exact 13-league whitelist. It uses persisted staging tables and committed profile/future-refresh/matchday policy files. It made zero Provider calls and zero writes.

## Result

- Top five (`premier_league`, `la_liga`, `bundesliga`, `serie_a`, `ligue_1`): `NOT_AUDITED` for the current 2026 persisted runtime evidence window.
- Active future/matchday routes (`brasileirao_serie_a`, `chinese_super_league`, `allsvenskan`, `eliteserien`): `PARTIAL`.
- Persisted evidence without an effective profile/future/matchday enable source (`argentina_primera`, `mls`, `eredivisie`, `primeira_liga`): `OWNER_DECISION_REQUIRED`; evidence is preserved, not discarded.
- `enabled:false` is never used as a standalone root cause.
- Squad value requires dataset mapping; injuries and settled AH remain not audited.
- No competition was activated, and no whitelist, scheduler, cadence, model, threshold or bookmaker-depth policy changed.

The detailed counts and classifications are in `STAGE14_COVERAGE_MATRIX.json`.
