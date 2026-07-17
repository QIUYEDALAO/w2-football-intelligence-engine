from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

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
    competition_id: str = "brasileirao_serie_a",
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
    materialization: dict[str, object] = {
        "status": "NOT_REQUESTED",
        "materialized_count": 0,
        "provider_calls": 0,
    }
    target_fixture_ids = list(dict.fromkeys(checkpoint_fixture_ids or []))
    if audit.status == "COMPLETED" and target_fixture_ids:
        from w2.api.repository import ReadModelService

        materialization = ReadModelService().materialize_frozen_analysis_cards(target_fixture_ids)
    task_status = "BLOCKED" if materialization.get("status") == "BLOCKED" else audit.status
    result = {**audit.result, "analysis_materialization": materialization}
    raw_materialization_blockers = materialization.get("blockers")
    materialization_blockers = (
        raw_materialization_blockers if isinstance(raw_materialization_blockers, list) else []
    )
    if task_status == "BLOCKED" and materialization_blockers:
        result["blockers"] = list(
            dict.fromkeys(
                [
                    *[str(item) for item in audit.result.get("blockers", [])],
                    *[str(item) for item in materialization_blockers],
                ]
            )
        )
    return {
        "task_id": audit.task_id,
        "task_key": audit.key,
        "status": task_status,
        "requested_interval_seconds": requested_interval_seconds,
        "effective_interval_seconds": effective_interval_seconds,
        "provider_refresh_min_interval_seconds": provider_refresh_min_interval_seconds,
        "checkpoint_fixture_ids": checkpoint_fixture_ids or [],
        "refresh_checkpoints": refresh_checkpoints or [],
        "result": result,
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
    from w2.api.repository import ReadModelService

    reconcile = ReadModelService().reconcile_frozen_analysis_cards(
        [str(item) for item in result.get("selected_fixtures", [])],
        max_fixtures=min(max(max_fixtures or 10, 0), 10),
    )
    result["analysis_reconcile"] = reconcile
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
        "provider_calls": 0,
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
    window: str = "all",
) -> dict[str, object]:
    request = getattr(self, "request", None)
    task_id = str(getattr(request, "id", None) or "forward-outcome-backfill")
    result = _run_forward_outcome_backfill(window=window)
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


def _run_forward_outcome_backfill(*, window: str) -> dict[str, object]:
    from w2.api.repository import ReadModelService, future_refresh_db_repository
    from w2.tracking.forward_outcome_ledger import backfill_outcomes, ledger_fixture_ids

    runtime_root = _forward_runtime_root()
    fixture_ids = ledger_fixture_ids(runtime_root)
    persisted_results: list[dict[str, object]] = []
    repository = future_refresh_db_repository()
    if repository is not None:
        persisted_results = repository.result_events_for_fixture_ids(fixture_ids)
    service = ReadModelService()
    dashboard = service.dashboard(window=window, include_debug=False)
    dashboard_results = dashboard.get("results")
    existing_results = dashboard_results if isinstance(dashboard_results, list) else []
    result_source = {**dashboard, "results": [*existing_results, *persisted_results]}
    return backfill_outcomes(
        runtime_root,
        result_source,
        dry_run=False,
        write_artifacts=True,
    )


def _forward_runtime_root() -> Path:
    return get_settings().resolved_runtime_root
