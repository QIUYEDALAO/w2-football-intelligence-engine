from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, time, timedelta
from typing import Annotated, Any, Literal
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import false, func, select
from sqlalchemy.orm import Session

from w2.api.cache import read_cache
from w2.api.repository import ReadModelService, SystemDegradedError
from w2.api.schemas import (
    AnalysisCardResponse,
    BacktestLatestResponse,
    CompetitionOperationsProfileResponse,
    DashboardDayViewResponse,
    DashboardIntelligenceCalibratedValidationResponse,
    DashboardIntelligenceReplayResponse,
    DashboardIntelligenceValidationResponse,
    DashboardIntelligenceWorkspaceListResponse,
    DashboardIntelligenceWorkspaceResponse,
    DashboardResponse,
    DashboardSummaryResponse,
    DataHealthResponse,
    ErrorPayload,
    FixtureDetailResponse,
    FixtureListResponse,
    FormalTrackingSummaryResponse,
    ForwardHoldoutStatusResponse,
    IntegrityResponse,
    LeagueListResponse,
    LeagueOnboardingResponse,
    LeagueReadinessResponse,
    MarketRankingResponse,
    MatchdayCoverageResponse,
    MatchdayResponse,
    OddsTimelineResponse,
    OperationListResponse,
    OperationsCycleResponse,
    OperationsLatestResponse,
    PageMeta,
    PerformanceResponse,
    ProbabilityResponse,
    ProviderStatusResponse,
    ReleaseReadinessResponse,
    ResearchCardResponse,
    RetentionStatusResponse,
    ValidationSummaryResponse,
    VersionResponse,
    WorkspaceMatch,
    WorkspaceMatchOutcome,
    WorkspacePublicTeamLabel,
    WorldCupReadinessResponse,
)
from w2.config import Environment, get_settings
from w2.dashboard.date_window import football_day_for_kickoff
from w2.dashboard.day_view import build_dashboard_day_view
from w2.dashboard.design_v1_projection import (
    performance_summary,
    replay_display_row,
    review_row,
    today_recommendations,
)
from w2.dashboard.results import normalize_match_status, outcome_public_cause
from w2.dashboard.workspace import (
    build_dashboard_intelligence_validation,
    build_dashboard_intelligence_workspace,
    build_dashboard_intelligence_workspace_list,
    build_dashboard_intelligence_workspace_summary,
)
from w2.domain.decision_contract import DecisionContractViolation
from w2.domain.ev_online_contract import (
    FAST_CRITERIA_MINIMUM_KEPT,
    FORWARD_START_UTC,
    SETTLED_STATES,
    is_forward,
)
from w2.domain.profit import profit_units_with_rebate
from w2.domain.recommendation_capabilities import load_recommendation_capability_manifest
from w2.infrastructure.persistence.dynamic_prematch_models import CalibratedValidationSampleModel
from w2.infrastructure.persistence.matchday_intake_models import MatchdayFixtureIdentityModel
from w2.monitoring.health import HealthPayload, build_health_payload
from w2.monitoring.readiness import ReadinessPayload, build_readiness_payload
from w2.prematch.candidate_notifications import notification_health
from w2.replay.front_door import build_replay_front_door
from w2.tracking.outcome_ledger_runtime import outcome_ledger_runtime_health

public_router = APIRouter(prefix="/v1", tags=["public-read"])
ops_router = APIRouter(prefix="/ops", tags=["operations-read"])
service = ReadModelService()
logger = logging.getLogger(__name__)
DASHBOARD_WINDOWS = {"today", "next36", "future", "results", "all"}


def _calibrated_sample_projection(
    row: CalibratedValidationSampleModel, kickoff_utc: datetime | None = None
) -> dict[str, Any]:
    """Serialize the already-materialized parallel row; no calibration here."""

    raw = {
        "fixture_id": row.fixture_id,
        "market": row.market,
        "competition_id": row.competition_id,
        "kickoff_utc": row.kickoff_utc or kickoff_utc,
        "selection": row.selection,
        "exact_line": row.exact_line,
        "decimal_odds": row.decimal_odds,
        "evaluation_id": row.evaluation_id,
        "settlement": row.settlement,
        "profit_units": row.profit_units,
        "score": row.score,
        "settled_at": row.settled_at,
        "evaluated_at": row.evaluated_at,
        "home_team_label": row.home_team_label or {},
        "away_team_label": row.away_team_label or {},
        "settlement_observed_at": row.settlement_observed_at,
        "bias_at_decision": row.bias_at_decision,
        "ev_raw": row.ev_raw,
        "ev_corrected": row.ev_corrected,
        "filter_decision": row.filter_decision,
        "param_version": row.param_version,
        "warmup": row.warmup,
        "forward": is_forward(row.evaluated_at),
    }
    display = review_row(raw, calibrated=True)
    return {
        **raw,
        **{
            field: display[field]
            for field in (
                "date",
                "league",
                "match",
                "recommendation",
                "result",
                "display_state",
                "display_notice",
                "calibration_decision",
                "calibrated_ev",
            )
        },
    }


def request_id(request: Request) -> str:
    return request.headers.get("x-request-id") or str(uuid4())


def cached_response(
    key: str,
    payload: dict[str, Any],
    response: Response,
    if_none_match: str | None,
) -> dict[str, Any] | Response:
    stable_payload = {name: value for name, value in payload.items() if name != "request_id"}
    cached = read_cache.get_or_set(key, stable_payload)
    response.headers["ETag"] = cached.etag
    if if_none_match == cached.etag:
        response.status_code = 304
        return Response(status_code=304, headers={"ETag": cached.etag})
    return payload


@public_router.get("/health", response_model=HealthPayload)
def public_health() -> HealthPayload:
    return build_health_payload()


@public_router.get("/ready", response_model=ReadinessPayload)
def public_ready(response: Response) -> ReadinessPayload:
    payload = build_readiness_payload()
    response.status_code = 200 if payload.status == "READY" else 503
    response.headers["Deprecation"] = "true"
    response.headers["Link"] = '</ready>; rel="canonical"'
    return payload


async def error_handler(request: Request, exc: Exception) -> JSONResponse:
    rid = request_id(request)
    if isinstance(exc, SystemDegradedError | DecisionContractViolation):
        status_code = 503
        code = exc.code
        message = str(exc)
    elif isinstance(exc, HTTPException):
        status_code = exc.status_code
        code = "HTTP_ERROR"
        message = str(exc.detail)
    elif isinstance(exc, ValidationError):
        status_code = 422
        code = "VALIDATION_ERROR"
        message = "Invalid request"
    else:
        status_code = 500
        code = "INTERNAL_ERROR"
        message = "Internal error"
    payload = ErrorPayload(request_id=rid, code=code, message=message)
    return JSONResponse(status_code=status_code, content=payload.model_dump())


def ensure_ops_enabled() -> None:
    if get_settings().environment == Environment.PRODUCTION:
        raise HTTPException(status_code=403, detail="operations API disabled in production")


def _projection_error_team_label(match: dict[str, Any], side: str) -> dict[str, Any]:
    raw = match.get(f"{side}_team_label")
    try:
        return WorkspacePublicTeamLabel.model_validate(raw).model_dump(mode="json")
    except ValidationError:
        name = str(match.get(f"{side}_team_name") or "球队待确认")
        return {
            "display_name": name,
            "state": "IDENTITY_UNRESOLVED",
            "canonical_team_id": None,
            "provider_team_id": None,
            "public_semantics": {"scope": "MATCH", "cause": "IDENTITY_UNRESOLVED"},
            "technical": {"raw_provider_name": name},
        }


def _projection_error_outcome(
    match: dict[str, Any], generated_at: Any
) -> dict[str, Any]:
    try:
        return WorkspaceMatchOutcome.model_validate(match.get("outcome")).model_dump(mode="json")
    except ValidationError:
        finished = normalize_match_status(match.get("status")) == "FINISHED"
        return {
            "is_finished": finished,
            "is_tracked": False,
            "is_recorded": False,
            "public_semantics": {
                "scope": "MATCH",
                "cause": outcome_public_cause(
                    status=match.get("status"),
                    kickoff_utc=match.get("kickoff_utc"),
                    as_of=generated_at,
                    is_tracked=False,
                    is_recorded=False,
                ),
            },
        }


def _isolate_workspace_match_projection_failures(payload: dict[str, Any]) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    failed_fixture_ids: set[str] = set()
    for raw in payload.get("matches", []):
        match = dict(raw)
        try:
            WorkspaceMatch.model_validate(match)
        except ValidationError as exc:
            fixture_id = str(match.get("fixture_id") or "UNKNOWN_FIXTURE")
            detail = " | ".join(
                f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
                for error in exc.errors(include_url=False, include_context=False)
            )
            logger.error(
                "dashboard_match_projection_contract_violation fixture_id=%s detail=%s",
                fixture_id,
                detail,
            )
            failed_fixture_ids.add(fixture_id)
            matches.append(
                {
                    "projection_status": "ERROR",
                    "fixture_id": fixture_id,
                    "competition_id": match.get("competition_id"),
                    "competition_name": match.get("competition_name"),
                    "kickoff_utc": match.get("kickoff_utc"),
                    "home_team_name": match.get("home_team_name"),
                    "away_team_name": match.get("away_team_name"),
                    "home_team_label": _projection_error_team_label(match, "home"),
                    "away_team_label": _projection_error_team_label(match, "away"),
                    "public_semantics": {"scope": "MATCH", "cause": "UNAVAILABLE"},
                    "status": match.get("status"),
                    "outcome": _projection_error_outcome(match, payload.get("generated_at")),
                    "projection_error": {
                        "code": "MATCH_PROJECTION_CONTRACT_VIOLATION",
                        "message": "该场投影未通过一致性校验，其余比赛不受影响",
                        "detail": detail,
                    },
                }
            )
        else:
            matches.append(match)
    if not failed_fixture_ids:
        return payload
    isolated = dict(payload)
    isolated["matches"] = matches
    isolated["attention"] = [
        item
        for item in payload.get("attention", [])
        if str(item.get("fixture_id") or "") not in failed_fixture_ids
    ]
    summary = dict(payload.get("today_summary", {}))
    summary["match_count"] = len(matches)
    summary["competition_count"] = len(
        {match.get("competition_id") for match in matches if match.get("competition_id")}
    )
    summary["pending_owner_review_team_count"] = len(
        {
            label.get("canonical_team_id")
            for match in matches
            for label in (match["home_team_label"], match["away_team_label"])
            if label.get("state") == "CHINESE_LABEL_PENDING_OWNER_REVIEW"
            and label.get("canonical_team_id")
        }
    )
    isolated["today_summary"] = summary
    return isolated


@public_router.get("/version", response_model=VersionResponse)
def version(request: Request) -> dict[str, Any]:
    return {
        "request_id": request_id(request),
        **service.version(),
    }


@public_router.get("/dashboard", response_model=DashboardResponse)
def dashboard(
    request: Request,
    date: str | None = None,
    window: str = "today",
    timezone: str = "Asia/Shanghai",
    include_debug: bool = False,
) -> dict[str, Any]:
    normalized_window = window if window in DASHBOARD_WINDOWS else "today"
    return {
        "request_id": request_id(request),
        **service.public_dashboard(
            target_date=date,
            window=normalized_window,
            timezone=timezone,
            include_debug=include_debug,
        ),
    }


@public_router.get("/performance", response_model=PerformanceResponse)
def performance(
    request: Request,
    window: Literal["7d", "30d", "90d"] = "30d",
    league: str | None = None,
    tier: Literal["ALL", "STRICT", "ADVISORY"] = "ALL",
) -> dict[str, Any]:
    return {
        "request_id": request_id(request),
        **service.performance(window=window, league=league, tier=tier),
    }


@public_router.get("/dashboard/day-view", response_model=DashboardDayViewResponse)
def dashboard_day_view(
    request: Request,
    date: str | None = None,
    window: str = "today",
    timezone: str = "Asia/Shanghai",
) -> dict[str, Any]:
    normalized_window = window if window in DASHBOARD_WINDOWS else "today"
    payload = service.public_dashboard(
        target_date=date,
        window=normalized_window,
        timezone=timezone,
        include_debug=False,
    )
    day_view = build_dashboard_day_view(
        payload,
        environment=get_settings().environment.value,
    )
    day_view["performance"] = payload.get("performance")
    return {
        "request_id": request_id(request),
        **day_view,
    }


@public_router.get(
    "/dashboard/intelligence-workspace",
    response_model=DashboardIntelligenceWorkspaceResponse,
)
def dashboard_intelligence_workspace(
    request: Request,
    date: str | None = None,
    window: Literal["today"] = "today",
    timezone: str = "Asia/Shanghai",
    projection: Literal["full", "summary"] = "full",
) -> dict[str, Any]:
    if projection == "summary":
        payload = service.public_dashboard(
            target_date=date,
            window=window,
            timezone=timezone,
            include_debug=False,
            include_details=False,
        )
        day_view = build_dashboard_day_view(
            payload,
            environment=get_settings().environment.value,
        )
        replay = build_replay_front_door(
            football_day=day_view["football_day"],
            environment=day_view["environment"],
            day_view=day_view,
            outcomes=[],
            as_of=day_view.get("generated_at"),
        )
        workspace = build_dashboard_intelligence_workspace_summary(
            day_view,
            replay=replay,
            recommendation_capabilities=load_recommendation_capability_manifest().public_summary()[
                "capabilities"
            ],
        )
        return {
            "request_id": request_id(request),
            **workspace,
        }
    payload = service.public_dashboard(
        target_date=date,
        window=window,
        timezone=timezone,
        include_debug=False,
        include_details=True,
    )
    day_view = build_dashboard_day_view(
        payload,
        environment=get_settings().environment.value,
    )
    fixture_ids = [str(card.get("fixture_id") or "") for card in day_view["cards"]]
    outcomes = service.dashboard_outcomes_for_fixtures(fixture_ids)
    model_forecasts = service.dashboard_model_forecasts_for_fixtures(fixture_ids)
    evaluations = service.dashboard_dynamic_evaluations_for_fixtures(fixture_ids)
    evaluation_checkpoints = service.dashboard_evaluation_checkpoints_for_fixtures(fixture_ids)
    for card in day_view["cards"]:
        fixture_id = str(card.get("fixture_id") or "")
        if fixture_id in evaluations:
            card["dynamic_prematch"] = evaluations[fixture_id]
        card["evaluation_checkpoints"] = evaluation_checkpoints.get(fixture_id, [])
    model_forecast_progress = service.dashboard_model_forecast_validation_progress()
    replay = build_replay_front_door(
        football_day=day_view["football_day"],
        environment=day_view["environment"],
        day_view=day_view,
        outcomes=outcomes,
        as_of=day_view.get("generated_at"),
    )
    workspace = build_dashboard_intelligence_workspace(
        day_view,
        replay=replay,
        model_forecasts=model_forecasts,
        model_forecast_progress=model_forecast_progress,
        candidate_enabled=os.environ.get("W2_CANDIDATE_ENABLED", "false").lower() == "true",
        recommendation_capabilities=load_recommendation_capability_manifest().public_summary()[
            "capabilities"
        ],
    )
    return {
        "request_id": request_id(request),
        **_isolate_workspace_match_projection_failures(workspace),
    }


@public_router.get(
    "/dashboard/intelligence-workspace/list",
    response_model=DashboardIntelligenceWorkspaceListResponse,
)
def dashboard_intelligence_workspace_list(
    request: Request,
    date: str | None = None,
    window: Literal["today"] = "today",
    timezone: str = "Asia/Shanghai",
) -> dict[str, Any]:
    payload = service.public_dashboard(
        target_date=date,
        window=window,
        timezone=timezone,
        include_debug=False,
        include_details=False,
    )
    day_view = build_dashboard_day_view(
        payload,
        environment=get_settings().environment.value,
    )
    workspace = build_dashboard_intelligence_workspace_list(
        day_view,
        recommendation_capabilities=load_recommendation_capability_manifest().public_summary()[
            "capabilities"
        ],
    )
    anchor = datetime.fromisoformat(str(day_view["date"])).date()
    facts_reader = getattr(service, "dashboard_design_v1_facts", None)
    facts = (
        facts_reader(anchor=anchor)
        if callable(facts_reader)
        else {"rows": [], "current_calibration_identity": None}
    )
    workspace["performance_summary"] = performance_summary(
        facts["rows"], anchor=anchor,
        calibration_identity=facts["current_calibration_identity"],
        total_profit_units=facts.get("total_profit_units"),
        total_absolute_profit_units=facts.get("total_absolute_profit_units"),
    )
    workspace["today_recommendations"] = today_recommendations(
        workspace["matches"], facts["rows"], anchor=anchor,
        calibration_identity=facts["current_calibration_identity"],
    )
    workspace["system_status"] = {
        "data": (
            "实时数据"
            if workspace["freshness"]["domains"]["odds_prematch"]["status"] == "AVAILABLE"
            and workspace["data_operations"]["system_health"]
            not in {"STALE_DATA", "PROVIDER_BUDGET_EXHAUSTED", "BLOCKED_DAY", "EMPTY_DAY"}
            else "数据未就绪"
        ),
        "recommendations": (
            "推荐已开启"
            if any(
                row.get("feature_enabled") is True
                for row in workspace["runtime"]["recommendation_capabilities"].values()
            )
            else "推荐未开启"
        ),
    }
    upcoming_reader = getattr(service, "dashboard_upcoming_football_days", None)
    workspace["upcoming_football_days"] = (
        upcoming_reader() if callable(upcoming_reader) else []
    )
    forward_reader = getattr(service, "dashboard_forward_wait_monitor", None)
    forward_monitor = forward_reader() if callable(forward_reader) else {}
    odds_status = workspace["freshness"]["domains"]["odds_prematch"]["status"]
    forward_monitor["data_source"] = {
        "status": odds_status,
        "provider_calls_on_read": 0,
    }
    workspace["forward_wait_monitor"] = forward_monitor
    return {"request_id": request_id(request), **workspace}


@public_router.get(
    "/dashboard/intelligence-workspace/validation",
    response_model=DashboardIntelligenceValidationResponse,
)
def dashboard_intelligence_validation(
    request: Request,
    date: str | None = None,
    window: Literal["today"] = "today",
    timezone: str = "Asia/Shanghai",
    days: Annotated[int | None, Query(ge=1, le=365)] = None,
    limit: Annotated[int | None, Query(ge=1, le=500)] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    payload = service.public_dashboard(
        target_date=date,
        window=window,
        timezone=timezone,
        include_debug=False,
        include_details=False,
    )
    day_view = build_dashboard_day_view(
        payload,
        environment=get_settings().environment.value,
    )
    validation = build_dashboard_intelligence_validation(
        day_view,
        model_forecast_progress=service.dashboard_model_forecast_validation_progress(),
    )
    sample_reader = getattr(service, "dashboard_validation_samples", None)
    samples, total = (
        sample_reader(
            anchor=datetime.fromisoformat(str(day_view["date"])).date(),
            days=days, limit=limit, offset=offset,
        ) if callable(sample_reader) else ([], 0)
    )
    profit_reader = getattr(service, "dashboard_validation_profit_summary", None)
    profit_summary = profit_reader() if callable(profit_reader) else {
        "profit_units": 0.0, "profit_units_with_rebate": 0.0
    }
    validation_signal_reader = getattr(service, "dashboard_track_d_validation_signals", None)
    validation_signals = (
        validation_signal_reader() if callable(validation_signal_reader) else {
            "watermark": "验证期信号 · 非正式推荐 · 不计入档位",
            "candidate_kind": "TRACK_D_FADE",
            "display_state": "VALIDATION_SIGNAL",
            "count": 0,
            "settled_count": 0,
            "hit_rate": None,
            "profit_units_channel": 0.0,
            "rebate_rate": 0.025,
            "rows": [],
            "small_sample_leagues": [],
        }
    )
    return {
        "request_id": request_id(request),
        "schema_version": "w2.dashboard-intelligence-validation.v1",
        "generated_at": day_view.get("generated_at"),
        "validation": validation,
        "samples": [review_row(row) for row in samples],
        "cumulative_profit_units": profit_summary["profit_units"],
        "cumulative_profit_units_with_rebate": profit_summary["profit_units_with_rebate"],
        "validation_signals": validation_signals,
        "pagination": {"days": days, "limit": limit, "offset": offset, "total": total},
        "read_contract": {
            "provider_calls": int(day_view.get("provider_calls") or 0),
            "db_writes": int(day_view.get("db_writes") or 0),
            "would_write_checkpoint": day_view.get("would_write_checkpoint") is True,
            "no_call_on_read": True,
        },
    }


@public_router.get(
    "/dashboard/intelligence-workspace/validation-calibrated",
    response_model=DashboardIntelligenceCalibratedValidationResponse,
)
def dashboard_intelligence_validation_calibrated(
    request: Request,
    date: str | None = None,
    window: Literal["today"] = "today",
    timezone: str = "Asia/Shanghai",
    days: Annotated[int | None, Query(ge=1, le=365)] = None,
    limit: Annotated[int | None, Query(ge=1, le=500)] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    """Read the EV-ONLINE-01 parallel projection; never recompute old validation."""

    kickoff = func.coalesce(
        CalibratedValidationSampleModel.kickoff_utc,
        MatchdayFixtureIdentityModel.kickoff_utc,
    )
    stmt = select(CalibratedValidationSampleModel, kickoff).outerjoin(
        MatchdayFixtureIdentityModel,
        MatchdayFixtureIdentityModel.fixture_id == CalibratedValidationSampleModel.fixture_id,
    ).order_by(kickoff.desc().nullslast(), CalibratedValidationSampleModel.fixture_id.desc())
    identity_reader = getattr(service, "dashboard_current_calibration_identity", None)
    current_identity = identity_reader() if callable(identity_reader) else None
    with Session(service.repository._database_engine()) as session:
        calibrated_stmt = stmt
        if callable(identity_reader):
            calibrated_stmt = calibrated_stmt.where(
                CalibratedValidationSampleModel.calibration_identity == current_identity
                if current_identity is not None else false()
            )
        all_rows = [
            _calibrated_sample_projection(row, row_kickoff)
            for row, row_kickoff in session.execute(calibrated_stmt)
        ]
    kept_profit_units = round(sum(
        float(row["profit_units"]) for row in all_rows
        if row["filter_decision"] == "KEPT" and row["settlement"] in SETTLED_STATES
        and row["profit_units"] is not None
    ), 3)
    filtered_profit_units = round(sum(
        float(row["profit_units"]) for row in all_rows
        if row["filter_decision"] == "FILTERED" and row["settlement"] in SETTLED_STATES
        and row["profit_units"] is not None
    ), 3)
    kept_profits = [
        row["profit_units"] for row in all_rows
        if row["filter_decision"] == "KEPT" and row["settlement"] in SETTLED_STATES
        and row["profit_units"] is not None
    ]
    filtered_profits = [
        row["profit_units"] for row in all_rows
        if row["filter_decision"] == "FILTERED" and row["settlement"] in SETTLED_STATES
        and row["profit_units"] is not None
    ]
    rows = all_rows
    if date and days is None:
        try:
            local_zone = ZoneInfo(timezone)
            local_start = datetime.combine(
                datetime.fromisoformat(date).date(), time.min, tzinfo=local_zone
            )
            start = local_start.astimezone(UTC)
            rows = [
                row for row in all_rows
                if row["kickoff_utc"] is not None
                and start <= (
                    row["kickoff_utc"] if row["kickoff_utc"].tzinfo
                    else row["kickoff_utc"].replace(tzinfo=UTC)
                ) < start + timedelta(days=1)
            ]
        except (ValueError, ZoneInfoNotFoundError):
            raise HTTPException(status_code=400, detail="invalid date") from None
    if days is not None:
        try:
            anchor = (
                datetime.fromisoformat(date).date()
                if date
                else datetime.now(ZoneInfo(timezone)).date()
            )
        except (ValueError, ZoneInfoNotFoundError):
            raise HTTPException(status_code=400, detail="invalid date or timezone") from None
        start = anchor - timedelta(days=days - 1)
        rows = [
            row for row in rows if row["date"] is not None
            and start <= datetime.fromisoformat(row["date"]).date() <= anchor
        ]
    total_before_page = len(rows)
    if offset:
        rows = rows[offset:]
    if limit is not None:
        rows = rows[:limit]
    kept = sum(row["filter_decision"] == "KEPT" for row in rows)
    filtered = len(rows) - kept
    warmup_kept = sum(row["filter_decision"] == "KEPT" and row["warmup"] for row in rows)
    non_warmup_kept = sum(
        row["filter_decision"] == "KEPT" and not row["warmup"] for row in rows
    )
    non_warmup_filtered = sum(
        row["filter_decision"] == "FILTERED" and not row["warmup"] for row in rows
    )
    unsettled_excluded = sum(
        row["forward"] and not row["warmup"] and row["settlement"] not in SETTLED_STATES
        for row in all_rows
    )
    forward_kept = sum(
        row["forward"] and not row["warmup"] and row["filter_decision"] == "KEPT"
        for row in all_rows
    )
    return {
        "request_id": request_id(request),
        "schema_version": "w2.dashboard-intelligence-validation-calibrated.v1",
        "generated_at": datetime.now(UTC),
        "date": date,
        "forward_start": FORWARD_START_UTC,
        "forward_progress": {
            "kept": forward_kept,
            "target": FAST_CRITERIA_MINIMUM_KEPT,
            "ratio": min(1.0, forward_kept / FAST_CRITERIA_MINIMUM_KEPT),
        },
        "samples": rows,
        "kept_profit_units": kept_profit_units,
        "filtered_profit_units": filtered_profit_units,
        "kept_profit_units_with_rebate": round(
            float(profit_units_with_rebate(kept_profits)), 3
        ),
        "filtered_profit_units_with_rebate": round(
            float(profit_units_with_rebate(filtered_profits)), 3
        ),
        "pagination": {"days": days, "limit": limit, "offset": offset, "total": total_before_page},
        "counts": {
            "total": len(rows),
            "kept": kept,
            "filtered": filtered,
            "warmup_kept": warmup_kept,
            "non_warmup_kept": non_warmup_kept,
            "non_warmup_filtered": non_warmup_filtered,
            "unsettled_excluded": unsettled_excluded,
        },
        "decision_contract": {
            "kind": "EV_ONLINE_FAST_CRITERIA_V3",
            "minimum_non_warmup_kept": FAST_CRITERIA_MINIMUM_KEPT,
            "population_filter": "forward=true AND warmup=false",
            "unsettled_rows_excluded": (
                "settlement must be one of WIN, HALF_WIN, PUSH, HALF_LOSS, LOSS"
            ),
            "forward_start": FORWARD_START_UTC,
            "criteria": [
                "bias_by_market_selection_stays_positive",
                "filtered_positive_rate_below_kept",
                "kept_absolute_cal_gap_not_worse_than_filtered",
            ],
            "slow_pnl_comparison": "RECORD_ONLY_NOT_A_DECISION_CRITERION",
        },
        "read_contract": {
            "provider_calls": 0,
            "db_writes": 0,
            "would_write_checkpoint": False,
            "no_call_on_read": True,
        },
    }


@public_router.get(
    "/dashboard/intelligence-workspace/replay",
    response_model=DashboardIntelligenceReplayResponse,
    response_model_exclude_defaults=True,
)
def dashboard_intelligence_replay(
    request: Request,
    date: str | None = None,
    window: Literal["today"] = "today",
    timezone: str = "Asia/Shanghai",
) -> dict[str, Any]:
    payload = service.public_dashboard(
        target_date=date,
        window=window,
        timezone=timezone,
        include_debug=False,
        include_details=True,
    )
    day_view = build_dashboard_day_view(
        payload,
        environment=get_settings().environment.value,
    )
    fixture_ids = [str(card.get("fixture_id") or "") for card in day_view["cards"]]
    outcomes = service.dashboard_outcomes_for_fixtures(fixture_ids)
    replay = build_replay_front_door(
        football_day=day_view["football_day"],
        environment=day_view["environment"],
        day_view=day_view,
        outcomes=outcomes,
        as_of=day_view.get("generated_at"),
    )
    workspace = build_dashboard_intelligence_workspace(
        day_view,
        replay=replay,
        recommendation_capabilities=load_recommendation_capability_manifest().public_summary()[
            "capabilities"
        ],
    )
    isolated = _isolate_workspace_match_projection_failures(workspace)
    evaluation_reader = getattr(service, "dashboard_dynamic_evaluations_for_fixtures", None)
    evaluation_map = evaluation_reader(fixture_ids) if callable(evaluation_reader) else {}
    matches = [
        {
            key: match.get(key)
            for key in (
                "fixture_id",
                "competition_id",
                "competition_name",
                "kickoff_utc",
                "home_team_name",
                "away_team_name",
                "home_team_label",
                "away_team_label",
                "public_semantics",
                "status",
                "outcome",
            )
        }
        for match in isolated["matches"]
    ]
    for match in matches:
        versions = evaluation_map.get(str(match.get("fixture_id")), {}).get("versions", [])
        match.update(replay_display_row(match, versions))
        kickoff = match.get("kickoff_utc")
        if kickoff:
            parsed = datetime.fromisoformat(str(kickoff).replace("Z", "+00:00"))
            match["date"] = football_day_for_kickoff(parsed).isoformat()
    return {
        "request_id": request_id(request),
        "schema_version": "w2.dashboard-intelligence-replay.v1",
        "generated_at": day_view.get("generated_at"),
        "date": workspace["date"],
        "matches": matches,
        "history_replay": workspace["validation"]["history_replay"],
        "read_contract": workspace["read_contract"],
    }


@public_router.get(
    "/dashboard/intelligence-workspace/matches/{fixture_id}",
    response_model=WorkspaceMatch,
)
def dashboard_intelligence_match(fixture_id: str) -> dict[str, Any]:
    match = service.dashboard_intelligence_match(
        fixture_id,
        candidate_enabled=os.environ.get("W2_CANDIDATE_ENABLED", "false").lower() == "true",
    )
    if match is None:
        raise HTTPException(status_code=404, detail="dashboard match not found")
    return match


@public_router.get("/dashboard/summary", response_model=DashboardSummaryResponse)
def dashboard_summary(
    request: Request,
    date: str | None = None,
    window: str = "today",
    timezone: str = "Asia/Shanghai",
) -> dict[str, Any]:
    normalized_window = window if window in DASHBOARD_WINDOWS else "today"
    return {
        "request_id": request_id(request),
        **service.public_dashboard_summary(
            target_date=date,
            window=normalized_window,
            timezone=timezone,
        ),
    }


@public_router.get("/validation/summary", response_model=ValidationSummaryResponse)
def validation_summary(
    request: Request,
    date: str | None = None,
    window: str = "today",
    timezone: str = "Asia/Shanghai",
) -> dict[str, Any]:
    normalized_window = window if window in DASHBOARD_WINDOWS else "today"
    return {
        "request_id": request_id(request),
        **service.public_validation_summary(
            target_date=date,
            window=normalized_window,
            timezone=timezone,
        ),
    }


@public_router.get("/formal/tracking/summary", response_model=FormalTrackingSummaryResponse)
def formal_tracking_summary(request: Request) -> dict[str, Any]:
    return {
        "request_id": request_id(request),
        **service.formal_tracking_summary(),
    }


@public_router.get("/fixtures", response_model=FixtureListResponse)
def list_fixtures(
    request: Request,
    response: Response,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    competition_id: str | None = None,
    status: str | None = None,
    team_id: str | None = None,
    timezone: str = "UTC",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
) -> Any:
    items, total = service.fixtures(
        timezone=timezone,
        page=page,
        page_size=page_size,
        date_from=date_from,
        date_to=date_to,
        competition_id=competition_id,
        status=status,
        team_id=team_id,
    )
    payload = {
        "request_id": request_id(request),
        "meta": PageMeta(page=page, page_size=page_size, total=total).model_dump(),
        "items": items,
    }
    cache_key = ":".join(
        [
            "fixtures",
            str(page),
            str(page_size),
            str(date_from),
            str(date_to),
            str(competition_id),
            str(status),
            str(team_id),
            timezone,
        ]
    )
    return cached_response(cache_key, payload, response, if_none_match)


@public_router.get("/matchday", response_model=MatchdayResponse)
def matchday(
    request: Request,
    date: str | None = None,
    competition_id: str | None = None,
    status: str | None = None,
    research_grade: str | None = None,
    data_status: str | None = None,
) -> dict[str, Any]:
    return {
        "request_id": request_id(request),
        **service.matchday(
            target_date=date,
            competition_id=competition_id,
            status=status,
            research_grade=research_grade,
            data_status=data_status,
        ),
    }


@public_router.get("/matchday/next-36-hours", response_model=MatchdayResponse)
def matchday_next_36_hours(request: Request) -> dict[str, Any]:
    return {
        "request_id": request_id(request),
        "date": "NEXT_36_HOURS",
        **service.matchday_next_36_hours(),
    }


@public_router.get("/matchday/{date}", response_model=MatchdayResponse)
def matchday_by_date(
    date: str,
    request: Request,
    competition_id: str | None = None,
    status: str | None = None,
    research_grade: str | None = None,
    data_status: str | None = None,
) -> dict[str, Any]:
    return {
        "request_id": request_id(request),
        **service.matchday(
            target_date=date,
            competition_id=competition_id,
            status=status,
            research_grade=research_grade,
            data_status=data_status,
        ),
    }


@ops_router.get("/matchday-coverage", response_model=MatchdayCoverageResponse)
def matchday_coverage(request: Request, date: str | None = None) -> dict[str, Any]:
    ensure_ops_enabled()
    coverage = service.matchday_coverage(target_date=date)
    return {
        "request_id": request_id(request),
        "requested_date_beijing": str(coverage["local_date"]),
        "timezone": "Asia/Shanghai",
        "window_start_beijing": str(coverage["start_local"]),
        "window_end_beijing": str(coverage["end_local"]),
        "window_start_utc": str(coverage["start_utc"]),
        "window_end_utc": str(coverage["end_utc"]),
        "authoritative_count": coverage["authoritative_count"],
        "discovered_count": coverage["discovered_count"],
        "eligible_count": coverage["eligible_count"],
        "card_count": coverage["card_count"],
        "read_model_count": coverage["read_model_count"],
        "displayed_count": coverage["displayed_count"],
        "missing_count": coverage["missing_count"],
        "reason_distribution": coverage["reason_distribution"],
        "coverage_status": coverage["coverage_status"],
    }


@public_router.get("/fixtures/{fixture_id}", response_model=FixtureDetailResponse)
def fixture_detail(fixture_id: str, request: Request, timezone: str = "UTC") -> dict[str, Any]:
    item = service.fixture(fixture_id, timezone)
    if item is None:
        raise HTTPException(status_code=404, detail="fixture not found")
    item["request_id"] = request_id(request)
    return item


@public_router.get("/fixtures/{fixture_id}/odds-timeline", response_model=OddsTimelineResponse)
def odds_timeline(fixture_id: str, request: Request) -> dict[str, Any]:
    return {
        "request_id": request_id(request),
        "fixture_id": fixture_id,
        "items": service.odds_timeline(fixture_id),
    }


@public_router.get(
    "/fixtures/{fixture_id}/research-card",
    response_model=ResearchCardResponse,
)
def research_card(fixture_id: str, request: Request) -> dict[str, Any]:
    card = service.research_card(fixture_id)
    if card is None:
        raise HTTPException(status_code=404, detail="research card not found")
    return {"request_id": request_id(request), "fixture_id": fixture_id, "card": card}


@public_router.get(
    "/fixtures/{fixture_id}/analysis-card",
    response_model=AnalysisCardResponse,
)
def analysis_card(fixture_id: str, request: Request) -> dict[str, Any]:
    card = service.public_analysis_card_bounded(fixture_id)
    if card is None:
        raise HTTPException(status_code=404, detail="analysis card not found")
    return {"request_id": request_id(request), "fixture_id": fixture_id, "card": card}


@public_router.get(
    "/fixtures/{fixture_id}/market-ranking",
    response_model=MarketRankingResponse,
)
def market_ranking(fixture_id: str, request: Request) -> dict[str, Any]:
    return {
        "request_id": request_id(request),
        "fixture_id": fixture_id,
        "items": service.market_ranking(fixture_id),
    }


@public_router.get("/fixtures/{fixture_id}/integrity", response_model=IntegrityResponse)
def fixture_integrity(fixture_id: str, request: Request) -> dict[str, Any]:
    integrity = service.integrity(fixture_id)
    if integrity is None:
        raise HTTPException(status_code=404, detail="fixture integrity not found")
    return {"request_id": request_id(request), "fixture_id": fixture_id, "integrity": integrity}


@public_router.get(
    "/fixtures/{fixture_id}/market-probabilities",
    response_model=ProbabilityResponse,
)
def market_probabilities(fixture_id: str, request: Request) -> dict[str, Any]:
    return {
        "request_id": request_id(request),
        "fixture_id": fixture_id,
        **service.market_probabilities(fixture_id),
    }


@public_router.get("/fixtures/{fixture_id}/model-probabilities", response_model=ProbabilityResponse)
def model_probabilities(fixture_id: str, request: Request) -> dict[str, Any]:
    return {
        "request_id": request_id(request),
        "fixture_id": fixture_id,
        **service.model_probabilities(fixture_id),
    }


@public_router.get("/data-health", response_model=DataHealthResponse)
def data_health(request: Request) -> dict[str, Any]:
    return {"request_id": request_id(request), **service.data_health()}


@public_router.get("/providers/status", response_model=ProviderStatusResponse)
def providers_status(request: Request) -> dict[str, Any]:
    return {"request_id": request_id(request), **service.provider_status()}


@public_router.get("/backtests/latest", response_model=BacktestLatestResponse)
def backtests_latest(request: Request) -> dict[str, Any]:
    return {
        "request_id": request_id(request),
        "status": "NOT_READY",
        "gate4_national_1x2": "PROVISIONAL_FORWARD_HOLDOUT_PENDING",
        "metrics": {
            "status": "NOT_READY",
            "reason": "BACKTEST_READ_MODEL_UNAVAILABLE",
        },
    }


@public_router.get("/forward-holdout/status", response_model=ForwardHoldoutStatusResponse)
def forward_holdout_status(request: Request) -> dict[str, Any]:
    return {"request_id": request_id(request), **service.forward_status()}


@public_router.get(
    "/competitions/{competition_id}/operations-profile",
    response_model=CompetitionOperationsProfileResponse,
)
def competition_operations_profile(competition_id: str, request: Request) -> dict[str, Any]:
    payload = service.competition_operations_profile(competition_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="competition operations profile not found")
    return {"request_id": request_id(request), **payload}


@public_router.get("/leagues", response_model=LeagueListResponse)
def leagues(request: Request) -> dict[str, Any]:
    return {"request_id": request_id(request), "items": service.leagues()}


@public_router.get("/leagues/{competition_id}/readiness", response_model=LeagueReadinessResponse)
def league_readiness(competition_id: str, request: Request) -> dict[str, Any]:
    payload = service.league_readiness(competition_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="league readiness not found")
    return {"request_id": request_id(request), **payload}


@ops_router.get("/health")
def ops_health(request: Request) -> dict[str, Any]:
    ensure_ops_enabled()
    outcome_health = outcome_ledger_runtime_health()
    return {
        "request_id": request_id(request),
        "status": "DEGRADED" if outcome_health["status"] == "DEGRADED" else "READY",
        "mode": "read-only",
        "outcome_ledger": outcome_health,
    }


@ops_router.get("/notification-outbox-health")
def notification_outbox_health(request: Request) -> dict[str, Any]:
    ensure_ops_enabled()
    return {"request_id": request_id(request), **notification_health()}


@ops_router.get("/outcome-ledger-health")
def outcome_ledger_health(request: Request) -> dict[str, Any]:
    ensure_ops_enabled()
    return {"request_id": request_id(request), **outcome_ledger_runtime_health()}


def ops_list(name: str, request: Request) -> dict[str, Any]:
    ensure_ops_enabled()
    return OperationListResponse(
        request_id=request_id(request),
        items=service.operations_items(name),
    ).model_dump()


@ops_router.get("/quota", response_model=OperationListResponse)
def ops_quota(request: Request) -> dict[str, Any]:
    return ops_list("quota", request)


@ops_router.get("/tasks", response_model=OperationListResponse)
def ops_tasks(request: Request) -> dict[str, Any]:
    return ops_list("tasks", request)


@ops_router.get("/alerts", response_model=OperationListResponse)
def ops_alerts(request: Request) -> dict[str, Any]:
    return ops_list("alerts", request)


@ops_router.get("/mapping-conflicts", response_model=OperationListResponse)
def ops_mapping_conflicts(request: Request) -> dict[str, Any]:
    return ops_list("mapping-conflicts", request)


@ops_router.get("/forward-cycles", response_model=OperationListResponse)
def ops_forward_cycles(request: Request) -> dict[str, Any]:
    return ops_list("forward-cycles", request)


@ops_router.get("/locks", response_model=OperationListResponse)
def ops_locks(request: Request) -> dict[str, Any]:
    return ops_list("locks", request)


@ops_router.get("/settlements", response_model=OperationListResponse)
def ops_settlements(request: Request) -> dict[str, Any]:
    return ops_list("settlements", request)


@ops_router.get("/gates", response_model=OperationListResponse)
def ops_gates(request: Request) -> dict[str, Any]:
    return ops_list("gates", request)


@ops_router.get("/gates/5-preflight", response_model=OperationListResponse)
def ops_gate5_preflight(request: Request) -> dict[str, Any]:
    ensure_ops_enabled()
    payload = service.gate5_preflight()
    return {
        "request_id": request_id(request),
        "items": [
            {
                "key": "gate5-preflight",
                "status": str(payload.get("gate5_result", "NO_RUN")),
                "payload": payload,
            }
        ],
    }


@ops_router.get("/w1-w2-shadow-comparison", response_model=OperationListResponse)
def ops_w1_w2_shadow_comparison(request: Request) -> dict[str, Any]:
    ensure_ops_enabled()
    payload = service.w1_w2_shadow_comparison()
    return {
        "request_id": request_id(request),
        "items": [
            {
                "key": "w1-w2-shadow-comparison",
                "status": str(payload.get("status", "NO_RUN")),
                "payload": payload,
            }
        ],
    }


@ops_router.get("/world-cup-readiness", response_model=WorldCupReadinessResponse)
def ops_world_cup_readiness(request: Request) -> dict[str, Any]:
    ensure_ops_enabled()
    return {"request_id": request_id(request), **service.world_cup_readiness()}


@ops_router.get("/league-onboarding", response_model=LeagueOnboardingResponse)
def ops_league_onboarding(request: Request) -> dict[str, Any]:
    ensure_ops_enabled()
    return {"request_id": request_id(request), "items": service.league_onboarding()}


@ops_router.get("/operations/cycles", response_model=OperationsCycleResponse)
def ops_operations_cycles(request: Request) -> dict[str, Any]:
    ensure_ops_enabled()
    return {"request_id": request_id(request), "items": service.operations_cycles()}


@ops_router.get("/operations/latest", response_model=OperationsLatestResponse)
def ops_operations_latest(request: Request) -> dict[str, Any]:
    ensure_ops_enabled()
    return {"request_id": request_id(request), "latest": service.operations_latest()}


@ops_router.get("/releases/readiness", response_model=ReleaseReadinessResponse)
def ops_releases_readiness(request: Request) -> dict[str, Any]:
    ensure_ops_enabled()
    return {"request_id": request_id(request), **service.releases_readiness()}


@ops_router.get("/retention/status", response_model=RetentionStatusResponse)
def ops_retention_status(request: Request) -> dict[str, Any]:
    ensure_ops_enabled()
    return {"request_id": request_id(request), **service.retention_status()}
