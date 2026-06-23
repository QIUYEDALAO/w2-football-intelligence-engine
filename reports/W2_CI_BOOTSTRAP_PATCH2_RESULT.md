# W2 CI Bootstrap Patch2 Result

## Scope

- Package: W2 CI-Patch2 PostgreSQL Alembic bootstrap repair and Patch1 data-integrity correction
- Base commit: `467d5b3241098fba7c553f4e3d117c68327c9e90`
- Worktree: `/tmp/w2-ci-bootstrap-patch2`
- Staging: not contacted or deployed
- W1: not modified
- `.env`: not read, sourced, grepped, or printed

## Root Cause

Patch1 fixed the baseline Pytest failures but the new GitHub CI failed during Alembic smoke. A local PostgreSQL Alembic diagnostic confirmed that W2 revision IDs exceed Alembic's PostgreSQL default version-table width:

- Longest W2 revision ID length: `43`
- Default PostgreSQL `alembic_version.version_num`: `VARCHAR(32)`
- Required W2 width: `64`

The previous version-table kwargs approach was not sufficient for the PostgreSQL implementation path, so fresh PostgreSQL bootstrap could fail before the first long revision was fully recorded.

Patch1 also introduced committed-report fallbacks that were too permissive:

- Stage10A could synthesize fixtures from prior forward-holdout report IDs.
- Stage14A could reuse committed Stage14A audit reports when runtime Stage5B raw fixture data was absent.

Patch2 removes those fallbacks and moves clean-checkout determinism into tests.

## Fix

Files changed:

- `src/w2/infrastructure/alembic_version.py`
  - Registers a W2 PostgreSQL Alembic implementation hook.
  - Builds `alembic_version.version_num` as `String(64)` with the expected primary key.
- `migrations/env.py`
  - Imports the W2 Alembic hook.
  - Removes the old version-table kwargs configuration.
- `pyproject.toml`
  - Raises Alembic lower bound to `>=1.14,<2`.
- `uv.lock`
  - Updates the project dependency metadata while keeping Alembic at `1.18.4`.
- `src/w2/api/repository.py`
  - Removes the synthetic fixture fallback from committed forward-holdout reports.
- `src/w2/operations/leagues.py`
  - Removes the implicit old Stage14A report fallback.
- `tests/unit/test_alembic_version_table.py`
  - Verifies the W2 PostgreSQL version table width and revision ID constraints.
- `tests/unit/test_stage10a_read_api.py`
  - Uses a test-owned fixture payload instead of production fallback logic.
- `tests/unit/test_stage14a_leagues.py`
  - Uses test-owned league fixture rows and verifies no-runtime-data stays `MISSING`.
- `reports/W2_CURRENT_HANDOFF.md`
  - Updates CI-Patch1/Patch2 status without claiming unknown CI success.
- `reports/W2_CI_BOOTSTRAP_PATCH2_RESULT.md`
  - Adds this report.

No existing `migrations/versions/*` files were changed, and no new migration was created.

## Validation

Passed locally:

- `uv sync --python 3.12 --all-groups --frozen`
- Alembic PostgreSQL diagnostic: confirmed default `VARCHAR(32)` behavior before the hook
- Targeted tests:
  - `tests/unit/test_alembic_version_table.py`
  - `tests/unit/test_stage10a_read_api.py`
  - `tests/unit/test_stage14a_leagues.py`
  - `tests/regression/test_guards.py`
- `uv run --python 3.12 python scripts/check_w2_stage1_contracts.py`
- `uv run --python 3.12 ruff check .`
- `uv run --python 3.12 mypy src apps`
- `uv run --python 3.12 pytest -q` (`133 passed, 2 warnings`)
- `PYTHONPATH=.:src uv run --python 3.12 python scripts/check_w2_all.py`
- `uv run --python 3.12 python tests/secret_scan.py`
- `git diff --check`
- SQLite Alembic round trip:
  - `uv run --python 3.12 alembic upgrade head`
  - `uv run --python 3.12 alembic downgrade base`
  - `uv run --python 3.12 alembic upgrade head`

Forbidden residual check:

- No production source retains the removed synthetic fixture labels, committed-report fallback functions, or old Alembic version-table kwargs configuration.
- The only remaining exact old Alembic kwargs string is the unit-test assertion that forbids it in `migrations/env.py`.

Local validation limitations:

- `LOCAL_POSTGRES_RUNTIME_UNAVAILABLE`: this machine has no local PostgreSQL command-line runtime available.
- `LOCAL_DOCKER_CLI_UNAVAILABLE_FOR_COMPOSE_CONFIG`: this machine has no Docker-compatible CLI available.

## Boundaries

- W1 was not modified.
- Staging was not contacted or deployed.
- `.env` was not read, sourced, grepped, or printed.
- No deployment, service restart, runtime data change, or GitHub repository setting change was performed.
- DeepSeek, CANDIDATE, and RECOMMEND remain disabled.

## Remote CI Rule

After this report is committed, the containing commit must be pushed once using an atomic update to:

- `refs/heads/main`
- `refs/heads/chore/stage7i-24h-observation`

The containing commit's GitHub Actions result is the authority for whether Patch2 closes the CI blocker. If that run fails, do not make a second commit, push, rerun, or deployment under this package.

## Remaining Status Before Remote CI

- `DEFAULT_BRANCH_NOT_MAIN`: the repository default branch was previously observed as `chore/stage7i-24h-observation`.
- `STAGE7I_DIRTY_WORKTREE_PRESERVED`: the original Stage7I worktree dirty files are intentionally not part of this patch.
- Patch2 CI status: derive from the GitHub Actions result for the containing commit.
