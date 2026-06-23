from __future__ import annotations

from celery import Celery

from w2.config import get_settings
from w2.ingestion.future_refresh import run_future_fixture_refresh

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


@celery_app.task(name="w2.future_fixture_refresh")
def future_fixture_refresh() -> dict[str, object]:
    result = run_future_fixture_refresh()
    return {
        "generated_at_utc": result.generated_at_utc.isoformat().replace("+00:00", "Z"),
        "fixture_count": result.fixture_count,
        "mapping_count": result.mapping_count,
        "market_snapshot_count": result.market_snapshot_count,
        "request_count": result.request_count,
        "remaining_quota": result.remaining_quota,
        "selected_market_fixture_ids": result.selected_market_fixture_ids,
        "blockers": result.blockers,
        "candidate": False,
        "formal_recommendation": False,
    }
