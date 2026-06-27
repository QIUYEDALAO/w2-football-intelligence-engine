# CI and Release

GitHub Actions runs on Python 3.12 and uses locked dependencies through `uv`.

CI performs:

- Stage 1 contract checker
- Ruff
- mypy
- pytest
- Alembic upgrade, downgrade, upgrade smoke
- PostgreSQL and Redis service containers
- Docker Compose config validation
- secret pattern scan

CI must not call Football-API, DeepSeek, paid providers, or live betting
systems. Release remains blocked until a later gate explicitly authorizes real
data collection and recommendation behavior.

## W2 Governance PRs

Docs/template-only governance PRs do not require staging deployment when they do
not change runtime code, runtime config, public UI assets, provider behavior, or
database migrations.

Any PR touching validation, settlement, provider quota, recommendation state,
competition scope, or public copy must answer the repository PR template safety
gates. In particular:

- FORMAL/CANDIDATE must remain disabled unless a separate unlock PR is approved.
- Runtime `beats_market` must remain false unless a separate unlock PR is
  approved.
- Zero-sample validation summaries must not fabricate hit rates.
- API-Football 75000/day remains an evaluation option, not a default.
- Competition whitelist expansion requires a separate runtime PR.
