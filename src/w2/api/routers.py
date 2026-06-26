from __future__ import annotations

from datetime import datetime
from time import monotonic
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from w2.api.cache import read_cache
from w2.api.metrics import metrics
from w2.api.repository import ReadModelService
from w2.api.schemas import (
    AnalysisCardResponse,
    BacktestLatestResponse,
    CompetitionOperationsProfileResponse,
    DashboardResponse,
    DataHealthResponse,
    ErrorPayload,
    FixtureDetailResponse,
    FixtureListResponse,
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
    ProbabilityResponse,
    ProviderStatusResponse,
    ReleaseReadinessResponse,
    ResearchCardResponse,
    RetentionStatusResponse,
    ShadowStrategyStatusResponse,
    VersionResponse,
    WorldCupReadinessResponse,
)
from w2.config import Environment, get_settings

public_router = APIRouter(prefix="/v1", tags=["public-read"])
ops_router = APIRouter(prefix="/ops", tags=["operations-read"])
service = ReadModelService()


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


async def error_handler(request: Request, exc: Exception) -> JSONResponse:
    rid = request_id(request)
    if isinstance(exc, HTTPException):
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
    normalized_window = window if window in {"today", "next36", "results", "all"} else "today"
    return {
        "request_id": request_id(request),
        **service.dashboard(
            target_date=date,
            window=normalized_window,
            timezone=timezone,
            include_debug=include_debug,
        ),
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
    started = monotonic()
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
    metrics.record("/v1/fixtures", 200, started)
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
    started = monotonic()
    item = service.fixture(fixture_id, timezone)
    if item is None:
        metrics.record("/v1/fixtures/{fixture_id}", 404, started)
        raise HTTPException(status_code=404, detail="fixture not found")
    item["request_id"] = request_id(request)
    metrics.record("/v1/fixtures/{fixture_id}", 200, started)
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
    card = service.analysis_card(fixture_id)
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
        "status": "READY",
        "gate4_national_1x2": "PROVISIONAL_FORWARD_HOLDOUT_PENDING",
        "metrics": service.repository.stage8_summary(),
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
def ops_health(request: Request) -> dict[str, str]:
    ensure_ops_enabled()
    return {"request_id": request_id(request), "status": "READY", "mode": "read-only"}


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


@ops_router.get("/shadow-strategy/status", response_model=ShadowStrategyStatusResponse)
def ops_shadow_strategy_status(request: Request) -> dict[str, Any]:
    ensure_ops_enabled()
    return {"request_id": request_id(request), **service.shadow_strategy_status()}


@ops_router.get("/shadow-strategy/locks", response_model=OperationListResponse)
def ops_shadow_strategy_locks(request: Request) -> dict[str, Any]:
    ensure_ops_enabled()
    return {
        "request_id": request_id(request),
        "items": [
            {"key": str(item.get("decision_hash")), "status": "LOCKED", "payload": item}
            for item in service.shadow_strategy_locks()
        ],
    }


@ops_router.get("/shadow-strategy/evaluations", response_model=OperationListResponse)
def ops_shadow_strategy_evaluations(request: Request) -> dict[str, Any]:
    ensure_ops_enabled()
    return {
        "request_id": request_id(request),
        "items": [
            {
                "key": f"{item.get('fixture_id')}:{item.get('phase')}",
                "status": str(item.get("public_decision", "NOT_READY")),
                "payload": item,
            }
            for item in service.shadow_strategy_evaluations()
        ],
    }


@ops_router.get("/shadow-strategy/replay", response_model=OperationListResponse)
def ops_shadow_strategy_replay(request: Request) -> dict[str, Any]:
    ensure_ops_enabled()
    replay = service.shadow_strategy_replay()
    return {
        "request_id": request_id(request),
        "items": [
            {
                "key": str(replay.get("run_id", "stage9a-shadow-replay")),
                "status": "READY" if replay else "EMPTY",
                "payload": replay,
            }
        ],
    }
