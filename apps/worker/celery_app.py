from __future__ import annotations

import logging
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, cast

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

logger = logging.getLogger(__name__)

#: Distinguishes "the caller did not choose a recorder" from "the caller chose
#: no recorder". The former builds the production one, the latter suppresses
#: recording for that call.
_UNSET: Any = object()

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


def _forward_factor_recorder() -> Any | None:
    """The write-side F1R-B recorder, or None when recording is off or unavailable.

    One per projection call, so that call's per-evaluation outcomes belong to
    that call instead of accumulating in a long-lived worker process. Never
    fatal: a worker that cannot build a recorder still evaluates, it just
    records nothing and reports that it could not.
    """
    from w2.quant_research.forward_factor_recording import (
        build_recorder,
        recording_enabled,
    )

    if not recording_enabled():
        return None
    try:
        return build_recorder()
    except Exception:  # noqa: BLE001 - recording must never take the worker down
        logger.exception(
            "forward factor recorder unavailable; this run writes no factor rows"
        )
        return None


def _project_and_record_factors(
    events: list[ProjectionSourceEvent],
    *,
    evaluations_only: bool = False,
) -> tuple[list[str], dict[str, Any]]:
    """Project events, then record each evaluation's four AH factors.

    Returns the materialized fixture ids and this run's recording report, so a
    task result can carry what was written -- and, just as importantly, what was
    not. A run whose recording was refused or unavailable must not be able to
    report itself as a clean pass.
    """
    from w2.quant_research.forward_factor_recording import (
        empty_report,
        recording_enabled,
    )

    recorder = _forward_factor_recorder()
    materialized = _materialize_shadow_projection_events(
        events,
        evaluations_only=evaluations_only,
        forward_factor_recorder=recorder,
    )
    if recorder is None:
        enabled = recording_enabled()
        return materialized, empty_report(
            enabled=enabled,
            note="RECORDER_UNAVAILABLE" if enabled else "DISABLED",
        )
    return materialized, recorder.summary()


def _recording_status(report: dict[str, Any]) -> str:
    """The recording's own verdict, for a task result to repeat verbatim."""
    return str(report.get("recording_status") or "UNAVAILABLE")


def _task_status(
    report: dict[str, Any],
    *,
    default: str = "PASS",
    ah_fact_report: dict[str, Any] | None = None,
) -> str:
    """`default` only when the factor recording did not fail.

    A task whose evaluation succeeded but whose per-factor recording did not is
    reported as such: the card is still returned, but the result says the F1R-B
    record is incomplete instead of claiming a clean PASS. A recording that was
    switched off is not a failure -- it is a stated decision -- and is reported
    through `forward_factor_recording.recording_status` instead.

    The runtime AH fact writer is the second thing a run can get wrong on its
    way to a clean pass, so it is folded in here too: a round whose facts could
    not be written, or could not be built because the results it depends on were
    not materialised, is reported as incomplete rather than as a pass.
    """
    from w2.historical.runtime_ah_settlement_materializer import (
        writer_status_is_clean,
    )
    from w2.quant_research.forward_factor_recording import (
        RECORDING_COMPLETE,
        RECORDING_DISABLED,
    )

    status = default
    if _recording_status(report) not in {RECORDING_COMPLETE, RECORDING_DISABLED}:
        status = f"{status}_WITH_RECORDING_INCOMPLETE"
    if ah_fact_report is not None and not writer_status_is_clean(ah_fact_report):
        status = f"{status}_WITH_AH_FACT_INCOMPLETE"
    return status


def _merge_recording_reports(reports: list[dict[str, Any]]) -> dict[str, Any]:
    """One recording report for a task that ran several projection calls."""
    from w2.quant_research.forward_factor_recording import merge_reports

    return merge_reports(reports)


def _recording_report_of(source: Mapping[str, object]) -> list[dict[str, Any]]:
    """The recording report a write-side branch returned, when it returned one."""
    nested = source.get("forward_factor_recording")
    return [dict(nested)] if isinstance(nested, Mapping) else []


def _materialize_ah_facts_after_results(
    confirmed_fixture_ids: Sequence[str],
    *,
    result_status: str,
) -> dict[str, Any]:
    """Build the runtime AH settlement facts this round's results enable.

    F1R-C. Runs after the result materialisation that produced the fixtures, and
    only when that materialisation succeeded: the results written by that step
    are the terminal evidence a fact rests on, so a round whose results were
    refused has nothing a fact could legitimately be built from.

    Reads persisted captures, market observations and terminal evidence only.
    No Provider call is made here, and none is possible: the writer takes no
    client and has no request path.
    """
    from w2.historical.runtime_ah_settlement_materializer import (
        STATUS_FAILED,
        STATUS_NO_DUE_WORK,
        STATUS_SKIPPED,
        empty_report,
        materialize_runtime_ah_settlement_facts,
    )
    from w2.infrastructure.database import create_engine

    fixture_ids = sorted({str(item) for item in confirmed_fixture_ids if str(item)})
    if str(result_status or "") == "BLOCKED":
        return empty_report(
            STATUS_SKIPPED, error="RESULT_MATERIALIZATION_BLOCKED"
        )
    if not fixture_ids:
        return empty_report(STATUS_NO_DUE_WORK)
    try:
        return materialize_runtime_ah_settlement_facts(
            engine=create_engine(),
            fixture_ids=fixture_ids,
        )
    except Exception as exc:  # noqa: BLE001 - the writer reports, never takes the tick down
        logger.exception("runtime AH settlement fact materializer failed")
        return empty_report(
            STATUS_FAILED,
            requested_count=len(fixture_ids),
            error=f"{type(exc).__name__}:{exc}",
        )


def _ah_fact_report_of(source: Mapping[str, object]) -> list[dict[str, Any]]:
    """The AH fact report a branch returned, when it returned one."""
    nested = source.get("runtime_ah_settlement_facts")
    return [dict(nested)] if isinstance(nested, Mapping) else []


def _materialize_results_with_ah_facts(
    reports: list[dict[str, Any]],
) -> Callable[[tuple[str, ...], datetime], dict[str, object]]:
    """`materialize_results`, keeping the AH fact report it produces.

    The callback contract is the result-refresh dict, and the fact report is
    built inside it. This wrapper keeps that report in the run's own container so
    the task result can state what the natural writer wrote -- and what it
    refused -- instead of the write being invisible to the run that caused it.
    """

    def materialize(
        fixture_ids: tuple[str, ...], now: datetime
    ) -> dict[str, object]:
        result = _materialize_outcome_results(fixture_ids, now)
        reports.extend(_ah_fact_report_of(result))
        return result

    return materialize


def _merge_ah_fact_reports(reports: list[dict[str, Any]]) -> dict[str, Any]:
    """One writer report for a task that materialised facts on several branches."""
    from w2.historical.runtime_ah_settlement_materializer import (
        merge_runtime_ah_fact_reports,
    )

    return merge_runtime_ah_fact_reports(reports)


def _materialize_public_artifacts_with_recording(
    reports: list[dict[str, Any]],
) -> Callable[[list[ProjectionSourceEvent]], list[str]]:
    """`materialize_public_artifacts`, keeping the recording report it produces.

    The refresh entrypoint's callback contract is `list[str]` -- fixture ids and
    nothing else -- so a recorder built inside the callback cannot reach the task
    result, and a run that wrote four factor rows could still report
    `rows_appended=0`. This wrapper runs the same write-side projection through
    `_project_and_record_factors`, which hands the report back next to the ids,
    keeps it in the run's own container, and returns exactly what the contract
    promises. The projection itself is unchanged.
    """

    def materialize(events: list[ProjectionSourceEvent]) -> list[str]:
        materialized, report = _project_and_record_factors(events)
        reports.append(report)
        return materialized

    return materialize


def _materialize_shadow_projection_events(
    events: list[ProjectionSourceEvent],
    *,
    evaluations_only: bool = False,
    forward_factor_recorder: Any = _UNSET,
) -> list[str]:
    """Composition-root adapter for write-side projection calculation.

    `forward_factor_recorder` is the F1R-B per-factor sink. Only this write-side
    path takes one -- the read-only API and dashboard build their cards through
    `public_analysis_card_bounded` directly, never through here, so reading a
    card writes no factor rows. Passing None disables recording for the call.
    """
    from w2.dashboard.scorelines import scoreline_reference_from_card
    from w2.prematch.analysis_calculator import ReadModelRepository, ReadModelService
    from w2.prematch.read_model_projection import (
        ScopedAnalysisRepository,
        materialize_projection_events,
    )
    repository = ReadModelRepository()
    recorder = _forward_factor_recorder() if forward_factor_recorder is _UNSET else (
        forward_factor_recorder
    )

    def calculate(
        scoped_repository: ScopedAnalysisRepository,
        fixture_id: str,
        evaluated_at: datetime,
    ) -> dict[str, object] | None:
        return ReadModelService(
            repository=cast(ReadModelRepository, scoped_repository),
            forward_factor_recorder=recorder,
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
    recording_reports: list[dict[str, Any]] = []
    for event in events:
        try:
            event_materialized, recording_report = _project_and_record_factors(
                [event], evaluations_only=True
            )
            materialized.extend(event_materialized)
            recording_reports.append(recording_report)
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
    recording_report = _merge_recording_reports(recording_reports)
    return {
        "status": _task_status(recording_report),
        "event_count": len(events),
        "fixture_count": len(set(materialized)),
        "opportunity_count": opportunity_count,
        "terminal_without_attempt_count": terminal_without_attempt_count,
        "forward_factor_recording": recording_report,
    }


def _freeze_t30_checkpoint_captures(
    checkpoints: list[dict[str, object]], *, evaluated_at: datetime
) -> dict[str, object]:
    """Recompute the bounded card and bind it to the canonical T-30 AH quote."""
    from w2.ingestion.market_timeline import (
        T30_VALIDATION_CHECKPOINT,
    )
    from w2.prematch.analysis_calculator import ReadModelRepository, ReadModelService
    from w2.tracking.model_forecast_ledger import (
        freeze_t30_capture,
        select_t30_market_reference,
    )

    if os.environ.get("W2_TASK3_T30_CAPTURE_ENABLED") != "1":
        return {"status": "DISABLED", "provider_calls": 0, "db_writes": 0}
    t30 = [
        item for item in checkpoints
        if str(item.get("checkpoint") or "") == T30_VALIDATION_CHECKPOINT
    ]
    if not t30:
        return {"status": "NOT_DUE", "provider_calls": 0, "db_writes": 0}
    repository = ReadModelRepository()
    service = ReadModelService(repository=repository)
    cards: list[dict[str, object]] = []
    quotes: dict[str, dict[str, object]] = {}
    blockers: list[dict[str, str]] = []
    observations = repository.future_market_observations_for_fixtures(
        [str(item.get("fixture_id") or "") for item in t30]
    )
    for item in t30:
        fixture_id = str(item.get("fixture_id") or "").removeprefix("api_football:")
        card = service.public_analysis_card_bounded(
            fixture_id, evaluation_time=evaluated_at, use_frozen_canary=False
        )
        kickoff_raw = (card or {}).get("kickoff_utc") if card else None
        if not isinstance(card, dict) or not kickoff_raw:
            blockers.append({"fixture_id": fixture_id, "blocker": "MODEL_CARD_UNAVAILABLE"})
            continue
        if card.get("competition_id") not in {
            "premier_league", "la_liga", "serie_a", "bundesliga", "ligue_1",
            "eredivisie", "primeira_liga",
        }:
            blockers.append({"fixture_id": fixture_id, "blocker": "OUTSIDE_TASK3_SCOPE"})
            continue
        kickoff = datetime.fromisoformat(str(kickoff_raw).replace("Z", "+00:00"))
        selected = select_t30_market_reference(
            observations,
            fixture_id=fixture_id,
            kickoff=kickoff,
            captured_at=evaluated_at,
        )
        if selected is None:
            blockers.append({"fixture_id": fixture_id, "blocker": "T30_QUOTE_UNAVAILABLE"})
            continue
        simulation = card.get("simulation") or {}
        cards.append({**card, "simulation": {
            "status": simulation.get("status"), "simulation": simulation,
        }})
        quotes[fixture_id] = selected
    result = freeze_t30_capture(
        {"cards": cards},
        market_snapshots=quotes,
        captured_at=evaluated_at,
        dry_run=False,
        write_db=True,
    )
    return {
        "status": "PASS" if result.get("db_writes") else "NO_CAPTURE",
        "provider_calls": 0,
        "db_writes": int(result.get("db_writes") or 0),
        "blockers": blockers,
        "capture_result": result,
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
    materialized, recording_report = _project_and_record_factors(events)
    return {
        "status": _task_status(recording_report),
        "provider_calls": 0,
        "db_writes": len(materialized),
        "scanned_fixture_count": len(fixture_ids),
        "xg_ready_fixture_count": len(xg_ready),
        "targeted_fixture_count": len(targets),
        "materialized_fixture_count": len(materialized),
        "forward_factor_recording": recording_report,
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
            # Nothing was evaluated, so nothing was recorded and nothing failed.
            # `status` stays the provider-scheduler verdict: this run is not a
            # pass and the recording report must not turn it into one.
            "forward_factor_recording": _merge_recording_reports([]),
            "runtime_ah_settlement_facts": _merge_ah_fact_reports([]),
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
    #: This run's own container. The projection callback below is where factor
    #: rows are written on this path, so the report it produces is the one the
    #: task result has to carry -- before this, it was built and dropped.
    recording_reports: list[dict[str, Any]] = []
    #: The result materialisation writes runtime AH settlement facts, and those
    #: writes belong to this run too. Same container rule, different writer.
    ah_fact_reports: list[dict[str, Any]] = []
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
        materialize_public_artifacts=_materialize_public_artifacts_with_recording(
            recording_reports
        ),
        materialize_results=_materialize_results_with_ah_facts(ah_fact_reports),
        client=ApiFootballClient(
            allow_live=True,
            allowed_live_endpoints=provider_endpoint_allowlist(),
        ),
    )
    opportunity_write = _write_checkpoint_opportunities(
        [
            dict(item)
            for item in audit.result.get("refresh_checkpoints", [])
            if isinstance(item, Mapping)
        ],
        task_id=audit.task_id,
        task_key=audit.key,
        evaluated_at=_worker_utc(getattr(audit, "finished_at", None)) or now,
        request_audit=[
            dict(item)
            for item in audit.result.get("requests", [])
            if isinstance(item, Mapping)
        ],
    )
    t30_capture = _freeze_t30_checkpoint_captures(
        [
            dict(item)
            for item in audit.result.get("refresh_checkpoints", [])
            if isinstance(item, Mapping)
        ],
        evaluated_at=datetime.now(UTC),
    )
    # Every write-side branch that actually ran a recorder reports here: the
    # projection callback above and the opportunity writer below. Merging is the
    # recording module's own, so a single worst-status rule applies everywhere.
    recording_report = _merge_recording_reports(
        [*recording_reports, *_recording_report_of(opportunity_write)]
    )
    ah_fact_report = _merge_ah_fact_reports(ah_fact_reports)
    return {
        "task_id": audit.task_id,
        "task_key": audit.key,
        "status": _task_status(recording_report, ah_fact_report=ah_fact_report),
        # The refresh audit's own verdict, kept under its own name: `status` above
        # now answers "did this run pass, including its factor recording?".
        "audit_status": audit.status,
        "requested_interval_seconds": requested_interval_seconds,
        "effective_interval_seconds": effective_interval_seconds,
        "provider_refresh_min_interval_seconds": provider_refresh_min_interval_seconds,
        "checkpoint_fixture_ids": checkpoint_fixture_ids or [],
        "refresh_checkpoints": refresh_checkpoints or [],
        "discovery_date": discovery_date,
        "result": audit.result,
        "opportunity_write": opportunity_write,
        "t30_capture": t30_capture,
        "forward_factor_recording": recording_report,
        "runtime_ah_settlement_facts": ah_fact_report,
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
    from w2.tracking.outcome_ledger_runtime import OutcomeLedgerRuntimeRepository

    runtime = OutcomeLedgerRuntimeRepository()
    if not runtime.mark_running(task_id=task_id, now=datetime.now(UTC)):
        return {
            "task_id": task_id,
            "queued_at_utc": queued_at_utc,
            "status": "ACTIVE_OR_RESERVED",
            "candidate": False,
            "formal_recommendation": False,
            "provider_calls": 0,
            "db_writes": 0,
            "lock_capture_write": False,
            "settlement_write": False,
        }
    try:
        result = _run_forward_outcome_ledger(window=window)
    except Exception as exc:
        runtime.mark_failed(
            task_id=task_id,
            error=f"{exc.__class__.__name__}:{exc}"[:512],
            now=datetime.now(UTC),
        )
        raise
    cursor_value = result.pop("source_cursor", {})
    pending_value = result.get("pending_settlement_count", 0)
    runtime.mark_succeeded(
        task_id=task_id,
        now=datetime.now(UTC),
        source_cursor=(
            {str(key): value for key, value in cursor_value.items()}
            if isinstance(cursor_value, Mapping)
            else {}
        ),
        pending_settlement_count=(
            pending_value if isinstance(pending_value, int) and not isinstance(pending_value, bool)
            else 0
        ),
    )
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
    from w2.dashboard.date_window import default_football_day
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
    from w2.tracking.outcome_ledger_runtime import OutcomeLedgerRuntimeRepository
    from w2.tracking.outcome_result_refresh import run_outcome_result_refresh

    repository = OutcomeLedgerRepository()
    evaluated_at = datetime.now(UTC)
    work = OutcomeLedgerRuntimeRepository(repository.engine).incremental_work(now=evaluated_at)
    football_day = default_football_day(evaluated_at).isoformat()
    cards = ReadModelService().dashboard_cards_for_fixtures(
        work.analysis_fixture_ids,
        generated_at=evaluated_at,
    )
    dashboard = {
        "generated_at": evaluated_at.isoformat().replace("+00:00", "Z"),
        "date": football_day,
        "selected_football_day": football_day,
        "timezone": "Asia/Shanghai",
        "window": window,
        "all": cards,
    }
    day_view = build_dashboard_day_view(dashboard, environment=get_settings().environment.value)
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
    materialization = (
        run_outcome_result_refresh(
            repository=repository,
            fixture_ids=list(work.result_fixture_ids),
            dry_run=False,
            write_db=True,
        )
        if work.result_fixture_ids
        else {
            "status": "NO_DUE_WORK",
            "db_writes": 0,
            "provider_calls": 0,
            "confirmed_fixture_ids": [],
        }
    )
    settlement = (
        backfill_outcomes(
            repository=repository,
            dry_run=False,
            write_db=True,
            fixture_ids=list(work.result_fixture_ids),
        )
        if work.result_fixture_ids
        else {
            "status": "NO_DUE_WORK",
            "db_writes": 0,
            "unresolved_count": 0,
            "unresolved_fixture_ids": [],
        }
    )
    # F1R-C: the same natural writer, on the other natural result-materialisation
    # path. Materialsing results without materialising the facts they prove would
    # leave this branch with fewer facts than the refresh branch, for no reason a
    # reader could see.
    confirmed = materialization.get("confirmed_fixture_ids")
    ah_fact_report = _materialize_ah_facts_after_results(
        [str(item) for item in confirmed] if isinstance(confirmed, list) else [],
        result_status=str(materialization.get("status") or ""),
    )
    pending_count = settlement["unresolved_count"]
    if not isinstance(pending_count, int) or isinstance(pending_count, bool):
        raise RuntimeError("OUTCOME_LEDGER_PENDING_COUNT_INVALID")
    unresolved_fixture_ids = settlement["unresolved_fixture_ids"]
    if not isinstance(unresolved_fixture_ids, list):
        raise RuntimeError("OUTCOME_LEDGER_PENDING_FIXTURES_INVALID")
    source_cursor = {
        **work.source_cursor,
        "pending_result_fixture_ids": [str(item) for item in unresolved_fixture_ids],
    }
    db_writes = 0
    for item in (
        model_forecast_capture,
        capture,
        materialization,
        settlement,
        ah_fact_report,
    ):
        value = item.get("db_writes", 0)
        if isinstance(value, int) and not isinstance(value, bool):
            db_writes += value
    from w2.historical.runtime_ah_settlement_materializer import (
        writer_status_is_clean,
    )

    status = "BLOCKED" if materialization["status"] == "BLOCKED" else capture["status"]
    if not writer_status_is_clean(ah_fact_report):
        status = f"{status}_WITH_AH_FACT_INCOMPLETE"
    return {
        **capture,
        "status": status,
        "candidate": os.environ.get("W2_CANDIDATE_ENABLED", "false").lower() == "true",
        "formal_recommendation": False,
        "lock": False,
        "production": False,
        "real_money": False,
        "db_writes": db_writes,
        "incremental_analysis_card_count": len(work.analysis_fixture_ids),
        "incremental_result_fixture_count": len(work.result_fixture_ids),
        "pending_settlement_count": pending_count,
        "source_cursor": source_cursor,
        "model_forecast_capture": model_forecast_capture,
        "model_forecast_analysis_refresh": {
            "status": "INCREMENTAL_CURSOR",
            "provider_calls": 0,
            "db_writes": 0,
            "scanned_fixture_count": len(work.analysis_fixture_ids),
            "targeted_fixture_count": len(work.analysis_fixture_ids),
            "materialized_fixture_count": 0,
        },
        "result_materialization": materialization,
        "outcome_settlement": settlement,
        "runtime_ah_settlement_facts": ah_fact_report,
    }


def _materialize_outcome_results(
    fixture_ids: tuple[str, ...],
    now: datetime,
) -> dict[str, object]:
    """Materialise this round's results, then the AH facts they enable.

    F1R-C. The fact writer lives here -- after the result materialisation and
    inside the branch that produced it -- because a runtime AH fact's only
    legitimate terminal evidence is a result this step has just persisted. The
    report travels back with the result so the task that caused the write can
    state it.
    """
    result = _run_result_materialize(fixture_ids=list(fixture_ids), now=now)
    confirmed = result.get("confirmed_fixture_ids")
    ah_fact_report = _materialize_ah_facts_after_results(
        [str(item) for item in confirmed] if isinstance(confirmed, list) else [],
        result_status=str(result.get("status") or ""),
    )
    return {**result, "runtime_ah_settlement_facts": ah_fact_report}


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
