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

