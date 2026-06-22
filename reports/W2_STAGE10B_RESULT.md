# W2 Stage10B Result

## Status

STAGE_10B=LOCAL_CODE_COMPLETE

No staging deployment was performed. No server process, container, systemd unit, Stage7I observer, or
matchday one-shot was restarted.

## Diagnosis

- `/v1/fixtures`: empty read model.
- `/ops/league-onboarding`: empty read model.
- `/ops/world-cup-readiness`: route failed when local fixture read-model inputs were absent.
- Web root called API paths without the required web-origin `/api` proxy, causing the dashboard to
look like a shell from the web port.

## Changes

- Added nginx same-origin `/api/` proxy for the web container.
- Updated the React console to call `/api/v1/...` and `/api/ops/...`.
- Added explicit LOADING, SUCCESS, EMPTY, ERROR, and STALE states with retry and request_id/error
  display.
- Added `MatchdaySnapshotProjector` and `scripts/project_stage10b_live_snapshot.py`.
- Reused `read_model_checkpoint` for dashboard read models instead of adding new tables.
- Wired fixture, provider, data health, forward status, market probability, and independent model
  probability endpoints to dashboard read-model checkpoints.

## Safety

- No `/recommendations`, `/candidates`, or `/deepseek` routes were added.
- Projected decisions remain WATCH/SKIP only.
- `formal_recommendation=false` and display-only research semantics are preserved.
- Frontend does not hardcode server IP, `127.0.0.1:18000`, or `api:8000`.

## Deployment

Deployment is paused pending explicit approval. Required deployment actions would be limited to web
image/API image rollout, optional local/staging migration smoke, and one controlled projector run
against the approved snapshot root.

## Validation

- `make verify`: PASS
- `uv run python scripts/check_w2_stage10b.py`: PASS
- `npm --prefix apps/web run typecheck`: PASS
- `npm --prefix apps/web run build`: PASS
- `uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head`: PASS
- `git diff --check`: PASS
- `uv run python tests/secret_scan.py`: PASS

PUSH_BLOCKED_NO_ORIGIN
