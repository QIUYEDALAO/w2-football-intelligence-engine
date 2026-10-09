from __future__ import annotations

import logging
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, cast

from celery import Celery

from w2.config import get_settings
from w2.ingestion.future_refresh import run_future_refresh_task
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

#: A committed ATTEMPTING stage whose ``updated_at`` has not advanced for this
#: many seconds is a stale claim (worker died before the terminal audit ran).
#: Re-entry then fails closed by flipping it to SIDE_EFFECT_UNCERTAIN instead of
#: leaving it stuck ATTEMPTING forever. Matches the read-only monitor's
#: STALE_ATTEMPTING 30-minute threshold.
FENCE_ATTEMPTING_STALE_SECONDS = 30 * 60


def _fence_stage(
    task_id: str,
    stage: str,
    state: str,
    error: str | None = None,
    *,
    owner_token: str | None = None,
    stored_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Atomically claim or CAS a stage. A state is never ownership."""
    from pathlib import Path
    from uuid import uuid4

    from alembic.config import Config as AlembicConfig
    from alembic.script import ScriptDirectory
    from sqlalchemy import text, update
    from sqlalchemy.engine.url import make_url
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.orm import Session

    from w2.infrastructure.database import create_engine
    from w2.infrastructure.persistence.provider_side_effect_fence_models import (
        ProviderSideEffectFenceModel as Fence,
    )
    database_url = get_settings().database_url.get_secret_value()
    if make_url(database_url).get_backend_name() != "postgresql":
        raise RuntimeError("PROVIDER_PERSISTENT_PG_REQUIRED")
    engine = create_engine()
    # A partially migrated PostgreSQL database is not a durable owner fence.
    # Compare the database's recorded revision with the packaged migration head
    # before allowing the first automatic external request.
    config_path = Path(__file__).resolve().parents[2] / "alembic.ini"
    expected_head = ScriptDirectory.from_config(
        AlembicConfig(str(config_path))
    ).get_current_head()
    with Session(engine) as revision_session:
        applied = revision_session.scalars(text("SELECT version_num FROM alembic_version")).all()
    if applied != [expected_head]:
        raise RuntimeError("PROVIDER_PG_MIGRATION_HEAD_REQUIRED")
    def observed(row: Fence | None) -> dict[str, Any]:
        if row is None:
            return {"status": "BLOCKED", "reason": "CLAIM_NOT_FOUND"}
        if row.state == "DONE":
            return {"status": "DONE", "stored_result": row.stored_result}
        if row.state == "ATTEMPTING":
            return {"status": "ALREADY_ATTEMPTING", "reason": "DELIVERY_UNKNOWN"}
        reason = row.state if row.state in {"BLOCKED", "SIDE_EFFECT_UNCERTAIN"} else "UNKNOWN_STATE"
        return {"status": "BLOCKED", "reason": reason}
    with Session(engine) as session:
        if state == "ATTEMPTING":
            existing = session.get(Fence, (task_id, stage, 1))
            if existing is not None:
                if (
                    existing.state == "ATTEMPTING"
                    and (datetime.now(UTC) - existing.updated_at).total_seconds()
                    > FENCE_ATTEMPTING_STALE_SECONDS
                ):
                    # 残留 ATTEMPTING 超时无推进（worker 崩溃未走 terminal audit）：
                    # fail-closed 转 SIDE_EFFECT_UNCERTAIN，避免永久卡死；provider
                    # 副作用不确定，绝不自动重试。
                    session.execute(
                        update(Fence)
                        .where(
                            Fence.task_id == task_id,
                            Fence.stage == stage,
                            Fence.attempt == 1,
                            Fence.state == "ATTEMPTING",
                        )
                        .values(
                            state="SIDE_EFFECT_UNCERTAIN",
                            error="STALE_ATTEMPTING_TIMEOUT",
                            updated_at=datetime.now(UTC),
                        )
                    )
                    session.commit()
                    return observed(session.get(Fence, (task_id, stage, 1)))
                return observed(existing)
            token = uuid4().hex
            now = datetime.now(UTC)
            session.add(Fence(task_id=task_id, stage=stage, attempt=1, state="ATTEMPTING",
                              owner_token=token, created_at=now, updated_at=now))
            try:
                session.commit()
                return {"status": "CLAIMED", "owner_token": token}
            except IntegrityError:
                session.rollback()
                return observed(session.get(Fence, (task_id, stage, 1)))
        if state not in {"DONE", "SIDE_EFFECT_UNCERTAIN", "BLOCKED"} or not owner_token:
            raise RuntimeError("FENCE_TRANSITION_NOT_AUTHORIZED")
        changed = session.execute(
            update(Fence)
            .where(
                Fence.task_id == task_id, Fence.stage == stage, Fence.attempt == 1,
                Fence.state == "ATTEMPTING", Fence.owner_token == owner_token,
            )
            .values(
                state=state, error=error, stored_result=stored_result,
                updated_at=datetime.now(UTC),
            )
        )
        if getattr(changed, "rowcount", None) != 1:
            session.rollback()
            raise RuntimeError("FENCE_OWNER_STATE_CONFLICT")
        session.commit()
        return {"status": state, "stored_result": stored_result}


def _execute_owned_stage(
    key: str, stage: str, action: Callable[[], dict[str, Any]]
) -> dict[str, Any]:
    try:
        claim = _fence_stage(key, stage, "ATTEMPTING")
    except Exception as exc:
        exc.__dict__["provider_calls_known"] = 0
        exc.__dict__["provider_calls_unknown"] = False
        raise
    if claim["status"] == "DONE":
        stored = claim.get("stored_result")
        if not isinstance(stored, dict):
            raise RuntimeError(f"{stage}:DONE_RESULT_MISSING")
        return stored
    if claim["status"] != "CLAIMED":
        blocked_error = RuntimeError(f"{stage}:{claim['status']}:{claim.get('reason', '')}")
        blocked_error.__dict__["provider_calls_known"] = None
        blocked_error.__dict__["provider_calls_unknown"] = True
        raise blocked_error
    token = claim["owner_token"]
    try:
        result = action()
        _fence_stage(key, stage, "DONE", owner_token=token, stored_result=result)
        return result
    except Exception as exc:
        # If this write fails, the committed ATTEMPTING still blocks reentry.
        try:
            _fence_stage(key, stage, "SIDE_EFFECT_UNCERTAIN", str(exc)[:512], owner_token=token)
        except Exception:
            logger.exception("stage terminal audit failed; original claim remains blocking")
        raise


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
celery_app.conf.update(
    task_always_eager=False,
    task_ignore_result=False,
    # CAP-MISS：重任务路由到 heavy 队列，由第二个 worker 容器（-Q heavy）消费，
    # 避免阻塞原 worker 的检查点采集等时效任务。
    task_routes={
        "w2.forward_outcome_ledger": {"queue": "heavy"},
        "w2.candidate_notification_schedule": {"queue": "heavy"},
        # D2.2（指令书 D2 §二，2026-10-10）：决策与结算任务从默认队列分离到 heavy。
        # 根因：决策任务此前与 w2.future_fixture_refresh（110s/条，无 queue 参数 ⇒ 默认队列）
        # 共抢 worker 的 concurrency=1，真决策被排在刷新之后 → 迟到 1-4h → 开球后落账（废单）。
        # 依据：worker-heavy 专属消费 heavy 队列（CAP-MISS 既有设计：时效任务不被重任务阻塞）。
        # 部署前实测余量（2026-10-09 19:3xZ 亲测）：heavy 积压 0；6h 内 54 个任务
        # （candidate_notification_schedule 46 + forward_outcome_ledger 8）；耗时 p50=0.2s、
        # p90=519s；按 ~19% 利用率估算余量约 80% ⇒ 容纳决策任务可行。
        # 注意：heavy 也是 concurrency=1，某次 forward_outcome_ledger 最长 ~520s 会把决策
        # 顺延 ≤9min；决策窗口是 kickoff-2h，该顺延不破坏时效（且远优于原先 1-4h 排队）。
        "w2.ah_ou_decision_forward": {"queue": "heavy"},
        "w2.ah_ou_v3_settlement_sweep": {"queue": "heavy"},
    },
    # 推送排程（每日名单 / 验证样本推送 / 每日结算）从 scheduler 主循环移出，
    # 由 worker 的 beat 每 2 分钟调度一次，读 validation_samples 表，不再占用
    # scheduler 派发循环的 CPU。
    beat_schedule={
        "candidate-notification-schedule": {
            "task": "w2.candidate_notification_schedule",
            "schedule": 120.0,
            "options": {"queue": "heavy"},
        },
        # 结算重扫：定期对「selected=true 且结果已落库但 settlement 未落」的 v3 决策补结算，
        # 独立于赛果物化的一次性触发；已结算幂等跳过。纯 DB 对账，无 Provider 调用。
        "ah-ou-v3-settlement-sweep": {
            "task": "w2.ah_ou_v3_settlement_sweep",
            "schedule": 300.0,
        },
    },
)


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


@celery_app.task(name="w2.candidate_notification_schedule", bind=True)
def candidate_notification_schedule(self: object) -> dict[str, object]:
    """Schedule the v3 daily settlement from verified decision IDs only."""

    del self  # 未使用
    from w2.prematch.candidate_notifications import (
        enqueue_scheduled_notifications,
    )

    scheduled = enqueue_scheduled_notifications()
    return {
        "status": "ENQUEUED" if scheduled else "NO_SUMMARY_DUE",
        "outbox_event_ids": scheduled,
        "brewing_digest_ids": [],
        "scheduled_notification_ids": scheduled,
        "db_writes": len(scheduled),
        "provider_calls": 0,
    }


@celery_app.task(name="w2.ah_ou_v3_settlement_sweep", bind=True)
def ah_ou_v3_settlement_sweep(self: object) -> dict[str, object]:
    """Periodic idempotent re-scan of settled-but-missed v3.1 decisions.

    Reconciles every selected v3.1 decision that has a confirmed result but no
    settlement yet. Runs independently of result materialisation, so a decision
    whose settlement failed once (and rolled back) is retried on the next tick
    instead of staying missed forever. Pure DB reconciliation: no Provider call.
    """
    del self  # 未使用
    from w2.infrastructure.database import create_engine

    report = _settle_v3_postmatch(create_engine(), evaluated_at=datetime.now(UTC))
    return {
        "status": report["status"],
        "v3": report["v3"],
        "provider_calls": 0,
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
    # The dispatch key is part of the durable business identity. Constructing
    # it at consumption time would let a delayed Celery redelivery claim a new
    # interval and repeat a possible Provider side effect.
    if not task_key:
        return {
            "task_id": "future-refresh",
            "task_key": None,
            "status": "BLOCKED",
            "audit_status": "BLOCKED",
            "result": {
                "blockers": ["FUTURE_REFRESH_DISPATCH_KEY_MISSING"],
                "provider_calls": 0,
                "provider_calls_known": 0,
                "provider_calls_unknown": False,
            },
            "candidate": False,
            "formal_recommendation": False,
        }
    now = datetime.now(UTC)
    key = task_key
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
    h2h_report: dict[str, object] = {}
    xg_report: dict[str, object] = {}
    auto_capture = any(os.environ.get(flag, "false").lower() == "true" for flag in (
        "W2_H2H_AUTO_CAPTURE_ENABLED", "W2_XG_AUTO_CAPTURE_ENABLED"))
    # 每条自动 refresh 都先取得持久 PG owner claim；SQLite 的本地 task
    # audit 不是 Provider 执行权。无 PG / claim 写失败 → 0 次进入外部入口。
    get_settings.cache_clear()
    owned_pipeline = True
    task_claim = None
    try:
        if owned_pipeline:
            task_claim = _fence_stage(key, "task", "ATTEMPTING")
            if task_claim["status"] == "DONE":
                stored = task_claim.get("stored_result")
                if not isinstance(stored, dict):
                    raise RuntimeError("TASK_DONE_RESULT_MISSING")
                return stored
            if task_claim["status"] != "CLAIMED":
                raise RuntimeError(f"TASK_{task_claim['status']}:{task_claim.get('reason', '')}")
        if os.environ.get("W2_H2H_AUTO_CAPTURE_ENABLED", "false").lower() == "true":
            from w2.ingestion.h2h_capture import capture_h2h_for_competition
            h2h_report = _execute_owned_stage(
                key, "h2h", lambda: capture_h2h_for_competition(competition_id=competition_id)
            )
        if os.environ.get("W2_XG_AUTO_CAPTURE_ENABLED", "false").lower() == "true":
            from w2.ingestion.xg_backfill import run_xg_history_backfill
            xg_report = _execute_owned_stage(
                key, "xg", lambda: run_xg_history_backfill(competition_id=competition_id).as_dict()
            )
        # The refresh may call Provider; its ownership spans forward and the
        # final result. A crash in this phase is blocked, never falsely READY.
        refresh_claim = (_fence_stage(key, "refresh_forward", "ATTEMPTING") if owned_pipeline
                         else {"status": "CLAIMED", "owner_token": None})
        if refresh_claim["status"] == "DONE":
            stored = refresh_claim.get("stored_result")
            if not isinstance(stored, dict):
                raise RuntimeError("REFRESH_DONE_RESULT_MISSING")
            if task_claim and task_claim["status"] == "CLAIMED":
                _fence_stage(
                    key, "task", "DONE", owner_token=task_claim["owner_token"],
                    stored_result=stored,
                )
            return stored
        if refresh_claim["status"] != "CLAIMED":
            raise RuntimeError(f"REFRESH_{refresh_claim['status']}")
    except Exception as exc:
        if task_claim and task_claim["status"] == "CLAIMED":
            try:
                _fence_stage(
                    key, "task", "SIDE_EFFECT_UNCERTAIN", str(exc)[:512],
                    owner_token=task_claim["owner_token"],
                )
            except Exception:
                logger.exception("task terminal audit failed; task claim remains blocking")
        elif task_claim is None:
            exc.__dict__["provider_calls_known"] = 0
            exc.__dict__["provider_calls_unknown"] = False
        return {
            "task_id": task_id, "task_key": key, "status": "BLOCKED", "audit_status": "BLOCKED",
            "result": {"blockers": [f"TASK_STAGE_BLOCKED:{type(exc).__name__}:{exc}"],
                       "provider_calls": getattr(exc, "provider_calls_known", None),
                       "provider_calls_known": getattr(exc, "provider_calls_known", None),
                       "provider_calls_unknown": getattr(exc, "provider_calls_unknown", True)},
            "h2h_auto_capture": h2h_report, "xg_auto_capture": xg_report,
            "candidate": False, "formal_recommendation": False,
        }
    try:
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
        task_result: dict[str, Any] = {
            "task_id": audit.task_id,
            "task_key": audit.key,
            "status": _task_status(
                recording_report,
                default="PASS" if audit.status == "COMPLETED" else str(audit.status),
                ah_fact_report=ah_fact_report,
            ),
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
            "h2h_auto_capture": h2h_report,
            "xg_auto_capture": xg_report,
            "candidate": False,
            "formal_recommendation": False,
        }

        if not auto_capture:
            # Preserve the frozen legacy response schema when auto-capture is off.
            task_result.pop("h2h_auto_capture", None)
            task_result.pop("xg_auto_capture", None)
        if owned_pipeline:
            if task_claim is None:
                raise RuntimeError("TASK_CLAIM_MISSING")
            _fence_stage(
                key, "refresh_forward", "DONE", owner_token=refresh_claim["owner_token"],
                stored_result=task_result,
            )
            _fence_stage(
                key, "task", "DONE", owner_token=task_claim["owner_token"],
                stored_result=task_result,
            )
        return task_result
    except Exception as exc:
        try:
            _fence_stage(
                key, "refresh_forward", "SIDE_EFFECT_UNCERTAIN", str(exc)[:512],
                owner_token=refresh_claim["owner_token"],
            )
        except Exception:
            logger.exception("refresh terminal audit failed; claim remains blocking")
        if task_claim and task_claim["status"] == "CLAIMED":
            try:
                _fence_stage(
                    key, "task", "SIDE_EFFECT_UNCERTAIN", str(exc)[:512],
                    owner_token=task_claim["owner_token"],
                )
            except Exception:
                logger.exception("task final report audit failed; claim remains blocking")
        return {"task_id": task_id, "task_key": key, "status": "BLOCKED", "audit_status": "BLOCKED",
                "result": {"blockers": [f"REFRESH_FORWARD_UNCERTAIN:{exc}"], "provider_calls": None,
                           "provider_calls_known": None, "provider_calls_unknown": True},
                "h2h_auto_capture": h2h_report, "xg_auto_capture": xg_report,
                "candidate": False, "formal_recommendation": False}


@celery_app.task(name="w2.xg_history_backfill", bind=True)
def xg_history_backfill(
    self: object,
    queued_at_utc: str | None = None,
    competition_id: str | None = None,
    claim_key: str | None = None,
    planned_window_start_utc: str | None = None,
    plan_interval_seconds: int | None = None,
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
    from w2.ingestion.provider_task_identity import xg_backfill_claim_key

    # Celery redelivery keeps the scheduler's immutable planned-window key.
    # Missing or inconsistent dispatch evidence blocks before any Provider call.
    if not (competition_id and queued_at_utc and claim_key and
            planned_window_start_utc and plan_interval_seconds):
        return {"task_id": task_id, "status": "BLOCKED", "reason": "XG_CLAIM_KEY_MISSING",
                "provider_calls_known": 0, "provider_calls_unknown": False}
    try:
        queued_at = datetime.fromisoformat(queued_at_utc.replace("Z", "+00:00"))
        expected, start = xg_backfill_claim_key(
            competition_id=competition_id, queued_at=queued_at,
            interval_seconds=plan_interval_seconds)
        planned = datetime.fromisoformat(
            planned_window_start_utc.replace("Z", "+00:00"))
        if claim_key != expected or planned != start:
            raise ValueError("XG_CLAIM_KEY_MISMATCH")
    except (TypeError, ValueError) as exc:
        return {"task_id": task_id, "status": "BLOCKED", "reason": str(exc),
                "provider_calls_known": 0, "provider_calls_unknown": False}
    # Re-read settings only to honour a new worker process' current DB config.
    get_settings.cache_clear()
    try:
        result = _execute_owned_stage(
            claim_key, "xg",
            lambda: run_xg_history_backfill(competition_id=competition_id).as_dict(),
        )
    except Exception as exc:
        return {"task_id": task_id, "queued_at_utc": queued_at_utc,
                "claim_key": claim_key, "status": "BLOCKED",
                "reason": f"{type(exc).__name__}:{exc}",
                "provider_calls_known": getattr(exc, "provider_calls_known", None),
                "provider_calls_unknown": getattr(exc, "provider_calls_unknown", True)}
    return {
        "task_id": task_id,
        "queued_at_utc": queued_at_utc,
        "claim_key": claim_key,
        "status": "COMPLETED",
        "result": result,
        "candidate": False,
        "formal_recommendation": False,
    }


@celery_app.task(name="w2.ah_ou_decision_forward", bind=True)
def ah_ou_decision_forward(
    self: object,
    fixture_id: str | None = None,
    queued_at_utc: str | None = None,
) -> dict[str, object]:
    """决策点自动 forward：对单个 fixture 跑 build_ah_ou_selections 落账本。

    由 scheduler 的 ah_ou_decision_forward_tick 在 decision_at(=kickoff-2h) 到点
    且账本尚未决策时派发。复用 ReadModelService 卡片构建链（F9/F6 softmax →
    写 ah_ou_decision_ledger + cohort），不经 HTTP 读取、不依赖打开 Dashboard。
    """
    from w2.prematch.analysis_calculator import ReadModelService

    task_id = str(getattr(getattr(self, "request", None), "id", None) or "ah-ou-decision-forward")
    fixture = str(fixture_id or "")
    if not fixture:
        return {
            "task_id": task_id,
            "status": "BLOCKED",
            "reason": "FIXTURE_ID_MISSING",
            "candidate": False,
            "formal_recommendation": False,
        }
    try:
        # 决策点评估时刻 = scheduler 派发时刻（queued_at_utc）。生产上前者约等于
        # decision_at（kickoff-2h），但若 scheduler 误提前派发，仍以 queued_at 与
        # decision_at 的真实先后关系兜底：queued_at < decision_at 时该 fixture 落
        # PREDECISION_NOT_RECORDED，不会提前锁槽。测试/回放可通过 queued_at 显式
        # 注入「决策点已到」的评估时刻，无需改真实墙钟或 fixture kickoff。
        evaluation_time = (
            datetime.fromisoformat(queued_at_utc.replace("Z", "+00:00")).astimezone(UTC)
            if queued_at_utc
            else None
        )
        card = ReadModelService().public_analysis_card_bounded(
            fixture,
            use_frozen_canary=False,
            use_timeline_observations=True,
            evaluation_time=evaluation_time,
        )
    except Exception as exc:
        return {
            "task_id": task_id,
            "fixture_id": fixture,
            "status": "BLOCKED",
            "reason": f"{type(exc).__name__}:{exc}"[:512],
            "candidate": False,
            "formal_recommendation": False,
        }
    return {
        "task_id": task_id,
        "fixture_id": fixture,
        "queued_at_utc": queued_at_utc,
        "status": "COMPLETED",
        "card_built": card is not None,
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
    if result.get("status") == "BLOCKED" or str(result.get("status") or "").endswith("_INCOMPLETE"):
        runtime.mark_failed(task_id=task_id, error=str(result.get("status"))[:512],
                            now=datetime.now(UTC))
        return {"task_id": task_id, "queued_at_utc": queued_at_utc,
                "status": "BLOCKED", "result": result, "provider_calls": 0,
                "candidate": False, "formal_recommendation": False}
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


@celery_app.task(name="w2.backtest", bind=True)
def backtest(
    self: object,
    queued_at_utc: str | None = None,
    settled_lock_sample_count: int | None = None,
) -> dict[str, object]:
    """回测执行任务：门达标后执行 walk-forward，产出写 checkpoint（幂等）。

    全程 0 Provider 调用、0 决策链写入；db_writes 仅限 read_model_checkpoint。
    同水位线重入（should_dispatch False）直接返回已有结果。
    """
    from w2.backtest.backtest_runtime import (
        BACKTESTS_LATEST_KEY,
        BACKTESTS_WATERMARK_KEY,
        build_backtest_gate_report,
        build_watermark_payload,
        count_settled_lock_samples,
        read_checkpoint_payload,
        run_backtest_execution,
        should_dispatch,
        upsert_checkpoint,
        utc_now_iso,
    )
    from w2.infrastructure.database import create_engine

    engine = create_engine()
    sample_count = (
        settled_lock_sample_count
        if settled_lock_sample_count is not None
        else count_settled_lock_samples()
    )
    generated_at = queued_at_utc or utc_now_iso()
    gate = build_backtest_gate_report(
        settled_lock_sample_count=sample_count,
        generated_at=generated_at,
    )
    watermark = read_checkpoint_payload(engine, BACKTESTS_WATERMARK_KEY)
    if not should_dispatch(gate=gate, watermark=watermark):
        latest = read_checkpoint_payload(engine, BACKTESTS_LATEST_KEY)
        return {
            "status": "ALREADY_CONSUMED_OR_BLOCKED",
            "settled_lock_sample_count": sample_count,
            "gate_status": gate.get("status"),
            "latest": latest,
            "provider_calls": 0,
            "db_writes": 0,
            "candidate": False,
            "formal_recommendation": False,
        }
    result = run_backtest_execution(generated_at=generated_at)
    source_hash = result.pop("source_hash")
    upsert_checkpoint(engine, BACKTESTS_LATEST_KEY, source_hash, result)
    upsert_checkpoint(
        engine,
        BACKTESTS_WATERMARK_KEY,
        source_hash,
        build_watermark_payload(sample_count=sample_count, at=generated_at),
    )
    return {
        "status": "COMPLETED",
        "settled_lock_sample_count": sample_count,
        "gate_status": gate.get("status"),
        "latest": result,
        "provider_calls": 0,
        "db_writes": 2,
        "candidate": False,
        "formal_recommendation": False,
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
    all_fixture_ids = list(
        dict.fromkeys([*work.analysis_fixture_ids, *work.capture_retry_fixture_ids])
    )
    cards = ReadModelService().dashboard_cards_for_fixtures(
        all_fixture_ids,
        generated_at=evaluated_at,
    )
    analysis_set = set(work.analysis_fixture_ids)
    analysis_cards = [
        card for card in cards if str(card.get("fixture_id") or "") in analysis_set
    ]
    dashboard = {
        "generated_at": evaluated_at.isoformat().replace("+00:00", "Z"),
        "date": football_day,
        "selected_football_day": football_day,
        "timezone": "Asia/Shanghai",
        "window": window,
        "all": analysis_cards,
    }
    day_view = build_dashboard_day_view(dashboard, environment=get_settings().environment.value)
    model_forecast_repository = ModelForecastLedgerRepository(repository.engine)
    # Model forecast capture requires the card's ``neutral_site_resolution``.
    # ``build_dashboard_day_view`` projects the public card through an explicit
    # whitelist that strips that internal field, so feeding ``day_view`` to the
    # capture path made ``_neutral_site_blocker`` fail closed with
    # NOT_ESTIMABLE_NEUTRAL_SITE_RESOLUTION on every card since a1bae660.
    # Mirror the T-30 freeze track: capture consumes the raw cards directly
    # (simulation wrapped in its envelope), while the outcome ledger keeps
    # consuming ``day_view``.  No fail-closed predicate is relaxed.
    model_forecast_cards: list[dict[str, object]] = []
    for card in cards:
        simulation = card.get("simulation") or {}
        model_forecast_cards.append(
            {
                **card,
                "simulation": {
                    "status": simulation.get("status"),
                    "simulation": simulation,
                },
            }
        )
    model_forecast_capture = run_model_forecast_capture(
        {"cards": model_forecast_cards},
        repository=model_forecast_repository,
        dry_run=False,
        write_db=True,
        capture_retry_fixture_ids=set(work.capture_retry_fixture_ids),
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
    # Track D belongs to the retired V4 recommendation generation. Its rows
    # remain queryable as historical evidence; post-event writes stop here.
    track_d_settlement: dict[str, Any] = {
        "status": "HISTORICAL_READ_ONLY", "db_writes": 0
    }
    # F1R-C: the same natural writer, on the other natural result-materialisation
    # path. Materialsing results without materialising the facts they prove would
    # leave this branch with fewer facts than the refresh branch, for no reason a
    # reader could see.
    confirmed = materialization.get("confirmed_fixture_ids")
    ah_fact_report = _materialize_ah_facts_after_results(
        [str(item) for item in confirmed] if isinstance(confirmed, list) else [],
        result_status=str(materialization.get("status") or ""),
    )
    # PERF-01 阶段2：物化验证样本（validation_samples），供工作台/每日结算读取，
    # 避免每次请求对推荐表全量重算。结果刷新 + 结算回填之后才物化，保证
    # settlement / profit_units / settled_at 已随结果落库。物化失败不阻断
    # ledger 主流程（每 10 分钟重试，最终一致），但把错误带进返回值供监控。
    validation_sample_report: dict[str, Any] = _settle_v3_postmatch(
        repository.engine, evaluated_at=evaluated_at
    )
    if (validation_sample_report.get("v3") or {}).get("status") == "BLOCKED":
        return {"status": "BLOCKED", "source_cursor": work.source_cursor,
                "validation_samples": validation_sample_report,
                "pending_settlement_count": settlement.get("unresolved_count", 0),
                "provider_calls": 0, "db_writes": 0}
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

    status = (
        "BLOCKED" if materialization["status"] == "BLOCKED"
        else "PASS" if capture["status"] == "HISTORICAL_READ_ONLY"
        else capture["status"]
    )
    if not writer_status_is_clean(ah_fact_report):
        status = f"{status}_WITH_AH_FACT_INCOMPLETE"
    return {
        **capture,
        "status": status,
        "candidate": False,
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
        "track_d_validation_settlement": track_d_settlement,
        "runtime_ah_settlement_facts": ah_fact_report,
        "validation_samples": validation_sample_report,
    }


def _materialize_validation_sample_projections(
    engine: Any, *, evaluated_at: datetime
) -> dict[str, object]:
    """Historical entry retained for callers; no old sample writes are allowed."""
    del engine, evaluated_at
    return {"status": "HISTORICAL_READ_ONLY", "window_rows": 0, "deleted": 0}


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

    result = run_outcome_result_refresh(
        fixture_ids=fixture_ids,
        dry_run=False,
        write_db=True,
        now=now,
    )
    if result["status"] == "BLOCKED":
        return result
    from w2.infrastructure.database import create_engine as _engine
    result["validation_samples"] = _settle_v3_postmatch(
        _engine(), evaluated_at=now or datetime.now(UTC))
    if (result["validation_samples"].get("v3") or {}).get("status") == "BLOCKED":
        result["status"] = "BLOCKED"
    return result


def _settle_v3_postmatch(engine: Any, *, evaluated_at: datetime) -> dict[str, Any]:
    """Commit v3 settlement and validation sample together after trusted FT."""
    from sqlalchemy import inspect as _inspect, text
    from sqlalchemy.orm import Session as _OrmSession

    from w2.tracking.ah_ou_v3_monitoring import append_monitoring_in_session
    from w2.tracking.ah_ou_v3_postmatch import settle_ah_ou_v3_in_session

    # A failed migration can leave the recovery collectors on the trusted 0076
    # schema. FT materialization remains useful; v3 settlement is explicitly
    # blocked until its tables exist, rather than losing the already persisted
    # result or reporting a successful empty v3 reconciliation.
    required = ("ah_ou_decision_ledger", "ah_ou_v3_settlement", "ah_ou_v3_validation_sample",
                "ah_ou_v3_monitoring_fact", "ah_ou_v3_monitoring_report")
    if not all(_inspect(engine).has_table(table) for table in required):
        return {"status": "BLOCKED", "v3": {
            "status": "BLOCKED", "reason": "V3_POSTMATCH_SCHEMA_UNAVAILABLE",
        }}
    with _OrmSession(engine) as session:
        # Single-flight across every settlement entrypoint (result materialise,
        # forward outcome ledger and the periodic sweep). The settlement INSERT
        # happens before the monitoring advisory lock, so it needs its own
        # transaction-scoped claim to keep concurrent sweeps from racing the
        # same decision_id primary key.
        if session.get_bind().dialect.name == "postgresql":
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended('v3-postmatch', 0))")
            )
        report: dict[str, object] = settle_ah_ou_v3_in_session(session, now=evaluated_at)
        # 逐 fixture 隔离后，blocked 只是「部分场次未结算」，其余场次已正常
        # settle 且幂等，必须 commit 而非整轮回滚（否则又变成一坏全滚连坐）。
        # 真正的失败（决策字段篡改 / 字段冲突）在函数内已抛异常，走 except 回滚。
        report["monitoring"] = append_monitoring_in_session(session, now=evaluated_at)
        session.commit()
    return {"status": str(report["status"]), "v3": report}
