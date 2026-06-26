from __future__ import annotations

from datetime import UTC, datetime

from celery import Celery

from w2.config import get_settings
from w2.ingestion.future_refresh import deterministic_task_key, run_future_refresh_task
from w2.ingestion.xg_backfill import run_xg_history_backfill

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
) -> dict[str, object]:
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
    )
    return {
        "task_id": audit.task_id,
        "task_key": audit.key,
        "status": audit.status,
        "result": audit.result,
        "candidate": False,
        "formal_recommendation": False,
    }


@celery_app.task(name="w2.xg_history_backfill", bind=True)
def xg_history_backfill(
    self: object,
    queued_at_utc: str | None = None,
) -> dict[str, object]:
    result = run_xg_history_backfill()
    request = getattr(self, "request", None)
    task_id = str(getattr(request, "id", None) or "xg-history-backfill")
    return {
        "task_id": task_id,
        "queued_at_utc": queued_at_utc,
        "status": "COMPLETED",
        "result": result.as_dict(),
        "candidate": False,
        "formal_recommendation": False,
    }
