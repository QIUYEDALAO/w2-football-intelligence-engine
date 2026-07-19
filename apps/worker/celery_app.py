from __future__ import annotations

from datetime import UTC, datetime

from celery import Celery

from w2.config import get_settings
from w2.ingestion.future_refresh import deterministic_task_key, run_future_refresh_task
from w2.ingestion.market_timeline_refresh import run_market_timeline_refresh
from w2.ingestion.xg_backfill import run_xg_history_backfill
from w2.providers.control import PROVIDER_SCHEDULER_DISABLED, provider_scheduler_enabled

settings = get_settings()

broker_url = (
    settings.celery_broker_url.get_secret_value()
    if settings.celery_broker_url is not None
    else "memory://"
)
result_backend = (
    settings.celery_result_backend.get_secret_value()
    if settings.celery_result_backend is not None
    else "cache+memory://"
)

celery_app = Celery("w2", broker=broker_url, backend=result_backend)
celery_app.conf.update(task_always_eager=False, task_ignore_result=False)


@celery_app.task(name="w2.ping")
def ping() -> str:
    return "pong"


@celery_app.task(name="w2.future_fixture_refresh", bind=True)
def future_fixture_refresh(
    self: object,
    competition_id: str = "world_cup_2026",
    task_key: str | None = None,
    queued_at_utc: str | None = None,
    requested_interval_seconds: int | None = None,
    effective_interval_seconds: int | None = None,
    provider_refresh_min_interval_seconds: int | None = None,
    checkpoint_fixture_ids: list[str] | None = None,
    refresh_checkpoints: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    if not provider_scheduler_enabled():
        return {
            "task_id": task_key or "future-refresh",
            "task_key": task_key,
            "status": PROVIDER_SCHEDULER_DISABLED,
            "requested_interval_seconds": requested_interval_seconds,
            "effective_interval_seconds": effective_interval_seconds,
            "provider_refresh_min_interval_seconds": provider_refresh_min_interval_seconds,
            "result": {
                "blockers": [PROVIDER_SCHEDULER_DISABLED],
                "provider_calls": 0,
                "candidate": False,
                "formal_recommendation": False,
                "checkpoint_fixture_ids": checkpoint_fixture_ids or [],
                "refresh_checkpoints": refresh_checkpoints or [],
            },
            "candidate": False,
            "formal_recommendation": False,
        }
    now = datetime.now(UTC)
    key = task_key or deterministic_task_key(
        competition_id=competition_id,
        season="2026",
        now=now,
        interval_seconds=900,
    )
    queued_at = (
        datetime.fromisoformat(queued_at_utc.replace("Z", "+00:00")).astimezone(UTC)
        if queued_at_utc
        else now
    )
    request = getattr(self, "request", None)
    task_id = str(getattr(request, "id", None) or key)
    audit = run_future_refresh_task(
        task_id=task_id,
        key=key,
        queued_at=queued_at,
        competition_id=competition_id,
        now=now,
        requested_interval_seconds=requested_interval_seconds,
        effective_interval_seconds=effective_interval_seconds,
        provider_refresh_min_interval_seconds=provider_refresh_min_interval_seconds,
        checkpoint_fixture_ids=tuple(checkpoint_fixture_ids or ()),
        refresh_checkpoints=tuple(refresh_checkpoints or ()),
    )
    return {
        "task_id": audit.task_id,
        "task_key": audit.key,
        "status": audit.status,
        "requested_interval_seconds": requested_interval_seconds,
        "effective_interval_seconds": effective_interval_seconds,
        "provider_refresh_min_interval_seconds": provider_refresh_min_interval_seconds,
        "checkpoint_fixture_ids": checkpoint_fixture_ids or [],
        "refresh_checkpoints": refresh_checkpoints or [],
        "result": audit.result,
        "candidate": False,
        "formal_recommendation": False,
    }


@celery_app.task(name="w2.xg_history_backfill", bind=True)
def xg_history_backfill(
    self: object,
    queued_at_utc: str | None = None,
) -> dict[str, object]:
    request = getattr(self, "request", None)
    task_id = str(getattr(request, "id", None) or "xg-history-backfill")
    if not provider_scheduler_enabled():
        return {
            "task_id": task_id,
            "queued_at_utc": queued_at_utc,
            "status": PROVIDER_SCHEDULER_DISABLED,
            "result": {
                "blockers": [PROVIDER_SCHEDULER_DISABLED],
                "provider_calls": 0,
                "candidate": False,
                "formal_recommendation": False,
            },
            "candidate": False,
            "formal_recommendation": False,
        }
    result = run_xg_history_backfill()
    return {
        "task_id": task_id,
        "queued_at_utc": queued_at_utc,
        "status": "COMPLETED",
        "result": result.as_dict(),
        "candidate": False,
        "formal_recommendation": False,
    }


@celery_app.task(name="w2.market_timeline_refresh", bind=True)
def market_timeline_refresh(
    self: object,
    queued_at_utc: str | None = None,
    window: str = "next36",
    checkpoint: str = "auto",
    max_fixtures: int | None = 10,
    capture_forward_ledger: bool = False,
) -> dict[str, object]:
    request = getattr(self, "request", None)
    task_id = str(getattr(request, "id", None) or "market-timeline-refresh")
    result = run_market_timeline_refresh(
        window=window,
        checkpoint=checkpoint,
        dry_run=False,
        write_artifacts=True,
        max_fixtures=max_fixtures,
    )
    forward_ledger_result: dict[str, object] | None = None
    if capture_forward_ledger:
        forward_ledger_result = _run_forward_outcome_ledger(window=window)
    return {
        "task_id": task_id,
        "queued_at_utc": queued_at_utc,
        "status": result["status"],
        "result": result,
        "forward_outcome_ledger": forward_ledger_result,
        "candidate": False,
        "formal_recommendation": False,
        "beats_market": False,
    }


@celery_app.task(name="w2.forward_outcome_ledger", bind=True)
def forward_outcome_ledger(
    self: object,
    queued_at_utc: str | None = None,
    window: str = "next36",
) -> dict[str, object]:
    request = getattr(self, "request", None)
    task_id = str(getattr(request, "id", None) or "forward-outcome-ledger")
    result = _run_forward_outcome_ledger(window=window)
    return {
        "task_id": task_id,
        "queued_at_utc": queued_at_utc,
        "status": result["status"],
        "result": result,
        "candidate": False,
        "formal_recommendation": False,
        "provider_calls": 0,
        "db_writes": 0,
        "lock_capture_write": False,
        "settlement_write": False,
    }


@celery_app.task(name="w2.forward_outcome_backfill", bind=True)
def forward_outcome_backfill(
    self: object,
    queued_at_utc: str | None = None,
    window: str = "next36",
    max_fixtures: int = 20,
) -> dict[str, object]:
    request = getattr(self, "request", None)
    task_id = str(getattr(request, "id", None) or "forward-outcome-backfill")
    if not provider_scheduler_enabled():
        return {
            "task_id": task_id,
            "queued_at_utc": queued_at_utc,
            "status": PROVIDER_SCHEDULER_DISABLED,
            "result": {"provider_calls": 0, "db_writes": 0},
            "candidate": False,
            "formal_recommendation": False,
        }
    result = _run_forward_outcome_backfill(window=window, max_fixtures=max_fixtures)
    return {
        "task_id": task_id,
        "queued_at_utc": queued_at_utc,
        "status": result["status"],
        "result": result,
        "candidate": False,
        "formal_recommendation": False,
        "provider_calls": 0,
        "db_writes": 0,
        "lock_capture_write": False,
        "settlement_write": False,
    }


def _run_forward_outcome_ledger(*, window: str) -> dict[str, object]:
    from w2.api.repository import ReadModelService
    from w2.dashboard.day_view import build_dashboard_day_view
    from w2.tracking.forward_outcome_ledger import run_forward_outcome_ledger

    service = ReadModelService()
    dashboard = service.dashboard(window=window, include_debug=False)
    day_view = build_dashboard_day_view(
        dashboard,
        environment=get_settings().environment.value,
    )
    return run_forward_outcome_ledger(
        day_view,
        dry_run=False,
        write_artifacts=True,
    )


def _run_forward_outcome_backfill(
    *, window: str, max_fixtures: int = 20
) -> dict[str, object]:
    del window  # retained for task compatibility; pending ledger is the authority.
    from w2.tracking.outcome_result_refresh import (
        run_outcome_result_refresh,
        runtime_root_from_env,
    )

    return run_outcome_result_refresh(
        runtime_root=runtime_root_from_env(),
        dry_run=False,
        write_artifacts=True,
        max_fixtures=max_fixtures,
    )
