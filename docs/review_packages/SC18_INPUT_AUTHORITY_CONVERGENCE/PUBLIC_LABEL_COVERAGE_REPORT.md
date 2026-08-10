# SC18 Public Label Coverage Report

- Evidence time: `2026-08-10T18:32:47Z`
- Canonical team rows: `68`
- Reviewed canonical Chinese labels: `0`
- Provider calls: `0`
- Database writes: `0`

The previous frontend `TEAM_TRANSLATIONS` dictionary is not a public identity authority. The unified workspace now reads canonical identity and reviewed crosswalk state from persisted tables. A Chinese label is `CHINESE_LABEL_READY` only when a reviewed crosswalk and a canonical Chinese label both exist.

Until a reviewed Chinese label exists, the public UI uses Chinese gap text with the stable provider team id:

- `CANONICAL_IDENTITY_READY_LABEL_MISSING` -> `主队/客队（中文译名待映射）`
- `IDENTITY_UNRESOLVED` -> `主队/客队（身份待确认：provider_team_id）`
- `AMBIGUOUS` -> identity-gap text; raw provider names remain technical-only

No English provider team name is silently presented as a Chinese-ready public label, and no translation is guessed.
