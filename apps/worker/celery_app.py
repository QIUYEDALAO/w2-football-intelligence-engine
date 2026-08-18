from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from typing import cast

from celery import Celery

from w2.config import get_settings
from w2.ingestion.future_refresh import deterministic_task_key, run_future_refresh_task
from w2.ingestion.xg_backfill import run_xg_history_backfill
from w2.prematch.read_model_projection import ProjectionSourceEvent
from w2.providers.api_football import ApiFootballClient
from w2.providers.control import (
    PROVIDER_SCHEDULER_DISABLED,
    provider_endpoint_allowlist,
    provider_scheduler_enabled,
)

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


def _materialize_shadow_projection_events(
    events: list[ProjectionSourceEvent],
    *,
    evaluations_only: bool = False,
) -> list[str]:
    """Composition-root adapter for write-side projection calculation."""
    from w2.dashboard.scorelines import scoreline_reference_from_card
    from w2.prematch.analysis_calculator import ReadModelRepository, ReadModelService
    from w2.prematch.read_model_projection import (
        ScopedAnalysisRepository,
        materialize_projection_events,
    )
    repository = ReadModelRepository()

    def calculate(
        scoped_repository: ScopedAnalysisRepository,
        fixture_id: str,
        evaluated_at: datetime,
    ) -> dict[str, object] | None:
        return ReadModelService(
            repository=cast(ReadModelRepository, scoped_repository)
        ).public_analysis_card_bounded(
            fixture_id,
            evaluation_time=evaluated_at,
            use_frozen_canary=False,
        )

    def build_scoreline_reference(card, version, quote_identity):  # type: ignore[no-untyped-def]
        return scoreline_reference_from_card(
            card,
            recommendation={
                "market": version.market,
                "selection": version.selection,
                "line": version.exact_line,
                "decision_tier": "ANALYSIS_PICK",
                "quote_identity": quote_identity,
            },
            decision_hash=version.identity_hash,
        )

    return materialize_projection_events(
        events,
        repository=cast(ScopedAnalysisRepository, repository),
        calculate_analysis_card=calculate,
        build_scoreline_reference=build_scoreline_reference,
        evaluations_only=evaluations_only,
    )


def _write_checkpoint_opportunities(
    checkpoints: list[dict[str, object]],
    *,
    task_id: str,
    task_key: str,
    evaluated_at: datetime,
    request_audit: list[dict[str, object]],
) -> dict[str, object]:
    """Write only opportunities explicitly bound to claimed checkpoint plans."""

    from w2.prematch.evaluation_slots import (
        CURRENT_EVALUATION_POLICY,
        is_evaluation_slot,
        require_evaluation_slot,
    )
    from w2.prematch.lifecycle import EvaluationOpportunityContext, OpportunityState
    from w2.prematch.repository import DynamicPrematchRepository
    from w2.tracking.model_forecast_ledger import ModelForecastLedgerRepository

    ledger = ModelForecastLedgerRepository()
    events: list[ProjectionSourceEvent] = []
    opportunity_count = 0
    terminal_without_attempt_count = 0
    for plan in checkpoints:
        slot = str(plan.get("checkpoint") or "")
        raw_endpoints = plan.get("endpoints")
        endpoints = raw_endpoints if isinstance(raw_endpoints, (list, tuple, set)) else ()
        if "odds" not in endpoints or not is_evaluation_slot(slot):
            continue
        slot = require_evaluation_slot(slot, policy_version=CURRENT_EVALUATION_POLICY)
        fixture_id = str(plan.get("fixture_id") or "").removeprefix("api_football:")
        plan_id = str(plan.get("id") or plan.get("plan_id") or "")
        scheduled_at = _worker_utc(plan.get("scheduled_at") or plan.get("due_at"))
        if not fixture_id or not plan_id or scheduled_at is None:
            raise RuntimeError("EVALUATION_SLOT_UNRESOLVED")
        attempted_request = next(
            (
                item
                for item in reversed(request_audit)
                if _worker_odds_request_matches(item, fixture_id=fixture_id)
            ),
            None,
        )
        tracks = ledger.opportunity_capture_seeds(fixture_id)
        if not tracks:
            continue
        request = (
            attempted_request
            if attempted_request is not None
            and str(attempted_request.get("status_code") or "") == "200"
            else None
        )
        if request is None:
            window_end = _worker_utc(plan.get("window_end"))
            state = (
                OpportunityState.MISSED_CHECKPOINT
                if window_end is not None and evaluated_at > window_end
                else OpportunityState.EVALUATION_ERROR
                if attempted_request is not None
                else None
            )
            if state is None:
                continue
            repository = DynamicPrematchRepository(ledger.engine)
            for capture_hash, model_input_hash in tracks:
                context = EvaluationOpportunityContext(
                    model_forecast_capture_identity_hash=capture_hash,
                    model_input_hash=model_input_hash,
                    evaluation_policy_version=CURRENT_EVALUATION_POLICY,
                    evaluation_slot_id=slot,
                    scheduled_checkpoint_at=scheduled_at,
                    checkpoint_plan_identity=plan_id,
                    source_event_identity=f"checkpoint-task:{task_key}:{task_id}",
                )
                for market in ("ASIAN_HANDICAP", "TOTALS"):
                    terminal_without_attempt_count += int(
                        repository.record_opportunity_without_attempt(
                            fixture_id=fixture_id,
                            market=market,
                            context=context,
                            state=state,
                            recorded_at=evaluated_at,
                            blocker=(
                                "CHECKPOINT_WINDOW_MISSED"
                                if state == OpportunityState.MISSED_CHECKPOINT
                                else "EVALUATION_REQUEST_FAILED"
                            ),
                        )
                    )
            continue
        event = ProjectionSourceEvent.create(
            fixture_id=fixture_id,
            event_type="CHECKPOINT_EVALUATION",
            event_id=(
                f"checkpoint:{plan_id}:{task_id}:"
                f"{request.get('payload_sha256') or 'provider-empty'}"
            ),
            event_at=_worker_utc(request.get("captured_at_utc")) or evaluated_at,
            payload={
                "checkpoint_plan_identity": plan_id,
                "evaluation_slot_id": slot,
                "task_key": task_key,
                "provider_request_payload_sha256": request.get("payload_sha256"),
            },
        )
        contexts = tuple(
            EvaluationOpportunityContext(
                model_forecast_capture_identity_hash=capture_hash,
                model_input_hash=model_input_hash,
                evaluation_policy_version=CURRENT_EVALUATION_POLICY,
                evaluation_slot_id=slot,
                scheduled_checkpoint_at=scheduled_at,
                checkpoint_plan_identity=plan_id,
                source_event_identity=event.event_hash,
            )
            for capture_hash, model_input_hash in tracks
        )
        events.append(replace(event, opportunity_contexts=contexts))
        opportunity_count += len(contexts) * 2
    materialized: list[str] = []
    for event in events:
        try:
            materialized.extend(
                _materialize_shadow_projection_events([event], evaluations_only=True)
            )
        except Exception as exc:
            repository = DynamicPrematchRepository(ledger.engine)
            for context in event.opportunity_contexts:
                for market in ("ASIAN_HANDICAP", "TOTALS"):
                    repository.record_opportunity_without_attempt(
                        fixture_id=event.fixture_id,
                        market=market,
                        context=context,
                        state=OpportunityState.EVALUATION_ERROR,
                        recorded_at=evaluated_at,
                        blocker=f"EVALUATION_ERROR:{exc.__class__.__name__}",
                    )
            raise
    return {
        "status": "PASS",
        "event_count": len(events),
        "fixture_count": len(set(materialized)),
        "opportunity_count": opportunity_count,
        "terminal_without_attempt_count": terminal_without_attempt_count,
    }


def _worker_utc(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _worker_odds_request_matches(
    request: Mapping[str, object],
    *,
    fixture_id: str,
) -> bool:
    params = request.get("params")
    return (
        request.get("endpoint") == "odds"
        and isinstance(params, Mapping)
        and str(params.get("fixture") or "") == fixture_id
    )


def _refresh_model_forecast_analysis_cards(
    dashboard: Mapping[str, object],
    *,
    evaluated_at: datetime,
) -> dict[str, object]:
    """Refresh only not-ready shadow projections before ModelForecast capture."""
    from w2.prematch.read_model_projection import MAX_PUBLIC_FIXTURES
    from w2.tracking.model_forecast_ledger import ModelForecastLedgerRepository

    rows = dashboard.get("all")
    fixture_ids = tuple(
        dict.fromkeys(
            str(row.get("fixture_id") or "")
            for row in rows
            if isinstance(rows, list) and isinstance(row, Mapping)
            and row.get("fixture_id")
        )
    ) if isinstance(rows, list) else ()
    if len(fixture_ids) > MAX_PUBLIC_FIXTURES:
        raise RuntimeError(f"MODEL_FORECAST_PROJECTION_SCOPE_EXCEEDED:{len(fixture_ids)}")
    cards = [row for row in rows if isinstance(row, Mapping)] if isinstance(rows, list) else []
    xg_ready = set(ModelForecastLedgerRepository().xg_ready_fixture_ids(cards))

    targets = [
        str(row["fixture_id"])
        for row in cards
        if row.get("fixture_id")
        and str(row["fixture_id"]) in xg_ready
        and (
            not isinstance((simulation := row.get("simulation")), Mapping)
            or simulation.get("status") != "READY"
        )
    ] if isinstance(rows, list) else []
    events = [
        ProjectionSourceEvent.create(
            fixture_id=fixture_id,
            event_type="XG_CHANGED",
            event_id=f"xg-refresh:{evaluated_at.isoformat()}",
            event_at=evaluated_at,
            payload={"fixture_id": fixture_id, "reason": "MODEL_FORECAST_CAPTURE"},
        )
        for fixture_id in targets
    ]
    materialized = _materialize_shadow_projection_events(events)
    return {
        "status": "PASS",
        "provider_calls": 0,
        "db_writes": len(materialized),
        "scanned_fixture_count": len(fixture_ids),
        "xg_ready_fixture_count": len(xg_ready),
        "targeted_fixture_count": len(targets),
        "materialized_fixture_count": len(materialized),
    }


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
    discovery_date: str | None = None,
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
        discovery_date=discovery_date,
        materialize_public_artifacts=_materialize_shadow_projection_events,
        materialize_results=_materialize_outcome_results,
        client=ApiFootballClient(
            allow_live=True,
            allowed_live_endpoints=provider_endpoint_allowlist(),
        ),
    )
    opportunity_write = _write_checkpoint_opportunities(
        list(refresh_checkpoints or ()),
        task_id=audit.task_id,
        task_key=audit.key,
        evaluated_at=_worker_utc(getattr(audit, "finished_at", None)) or now,
        request_audit=[
            dict(item)
            for item in audit.result.get("requests", [])
            if isinstance(item, Mapping)
        ],
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
        "discovery_date": discovery_date,
        "result": audit.result,
        "opportunity_write": opportunity_write,
        "candidate": False,
        "formal_recommendation": False,
    }


@celery_app.task(name="w2.xg_history_backfill", bind=True)
def xg_history_backfill(
    self: object,
    queued_at_utc: str | None = None,
    competition_id: str | None = None,
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
    result = run_xg_history_backfill(competition_id=competition_id)
    return {
        "task_id": task_id,
        "queued_at_utc": queued_at_utc,
        "status": "COMPLETED",
        "result": result.as_dict(),
        "candidate": False,
        "formal_recommendation": False,
    }


@celery_app.task(name="w2.forward_outcome_ledger", bind=True)
def forward_outcome_ledger(
    self: object,
    queued_at_utc: str | None = None,
    window: str = "next7",
) -> dict[str, object]:
    request = getattr(self, "request", None)
    task_id = str(getattr(request, "id", None) or "forward-outcome-ledger")
    result = _run_forward_outcome_ledger(window=window)
    return {
        "task_id": task_id,
        "queued_at_utc": queued_at_utc,
        "status": result["status"],
        "result": result,
        "candidate": result.get("candidate") is True,
        "formal_recommendation": False,
        "provider_calls": 0,
        "db_writes": result.get("db_writes", 0),
        "lock_capture_write": False,
        "settlement_write": False,
    }


@celery_app.task(name="w2.result_materialize", bind=True)
def result_materialize(
    self: object,
    queued_at_utc: str | None = None,
    fixture_ids: list[str] | None = None,
) -> dict[str, object]:
    request = getattr(self, "request", None)
    task_id = str(getattr(request, "id", None) or "result-materialize")
    result = _run_result_materialize(fixture_ids=fixture_ids)
    return {
        "task_id": task_id,
        "queued_at_utc": queued_at_utc,
        "status": result["status"],
        "result": result,
        "candidate": False,
        "formal_recommendation": False,
        "provider_calls": 0,
        "db_writes": result.get("db_writes", 0),
        "scoring_projection_status": result.get("scoring_projection_status", "NO_DUE_WORK"),
        "scoring_projection_db_writes": result.get("scoring_projection_db_writes", 0),
        "lock_capture_write": False,
        "settlement_write": False,
    }


def _run_forward_outcome_ledger(*, window: str) -> dict[str, object]:
    from w2.api.repository import ReadModelService
    from w2.dashboard.day_view import build_dashboard_day_view
    from w2.tracking.forward_outcome_ledger import (
        backfill_outcomes,
        run_forward_outcome_ledger,
    )
    from w2.tracking.model_forecast_ledger import (
        ModelForecastLedgerRepository,
        run_model_forecast_capture,
    )
    from w2.tracking.outcome_ledger_repository import OutcomeLedgerRepository
    from w2.tracking.outcome_result_refresh import run_outcome_result_refresh

    service = ReadModelService()
    repository = OutcomeLedgerRepository()
    evaluated_at = datetime.now(UTC)
    initial_dashboard = service.dashboard(window=window, include_debug=False)
    analysis_refresh = _refresh_model_forecast_analysis_cards(
        initial_dashboard,
        evaluated_at=evaluated_at,
    )
    analysis_refresh_writes = analysis_refresh["db_writes"]
    if not isinstance(analysis_refresh_writes, int):
        raise RuntimeError("MODEL_FORECAST_PROJECTION_WRITE_COUNT_INVALID")
    dashboard = ReadModelService().dashboard(window=window, include_debug=False)
    day_view = build_dashboard_day_view(
        dashboard,
        environment=get_settings().environment.value,
    )
    model_forecast_repository = ModelForecastLedgerRepository(repository.engine)
    model_forecast_capture = run_model_forecast_capture(
        day_view,
        repository=model_forecast_repository,
        dry_run=False,
        write_db=True,
    )
    capture = run_forward_outcome_ledger(
        day_view,
        repository=repository,
        dry_run=False,
        write_db=True,
    )
    materialization = run_outcome_result_refresh(
        repository=repository,
        dry_run=False,
        write_db=True,
    )
    settlement = backfill_outcomes(
        repository=repository,
        dry_run=False,
        write_db=True,
    )
    return {
        **capture,
        "status": ("BLOCKED" if materialization["status"] == "BLOCKED" else capture["status"]),
        "candidate": os.environ.get("W2_CANDIDATE_ENABLED", "false").lower() == "true",
        "formal_recommendation": False,
        "lock": False,
        "production": False,
        "real_money": False,
        "db_writes": analysis_refresh_writes + sum(
            int(item.get("db_writes", 0))
            for item in (model_forecast_capture, capture, materialization, settlement)
        ),
        "model_forecast_capture": model_forecast_capture,
        "model_forecast_analysis_refresh": analysis_refresh,
        "result_materialization": materialization,
        "outcome_settlement": settlement,
    }


def _materialize_outcome_results(
    fixture_ids: tuple[str, ...],
    now: datetime,
) -> dict[str, object]:
    return _run_result_materialize(fixture_ids=list(fixture_ids), now=now)


def _run_result_materialize(
    *,
    fixture_ids: list[str] | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    from w2.tracking.outcome_result_refresh import run_outcome_result_refresh

    return run_outcome_result_refresh(
        fixture_ids=fixture_ids,
        dry_run=False,
        write_db=True,
        now=now,
    )
