from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import monotonic

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from w2.api.metrics import metrics as api_metrics
from w2.api.routers import error_handler, ops_router, public_router, service
from w2.config import Environment, get_settings
from w2.monitoring.health import HealthPayload, build_health_payload
from w2.monitoring.readiness import ReadinessPayload, build_readiness_payload
from w2.operations.observability import default_metric_registry


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    service.warm_dashboard_cache()
    yield


app = FastAPI(
    title="W2 Football Intelligence Engine",
    version="0.2.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://staging.w2.local",
    ],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["x-request-id", "if-none-match"],
)
app.add_exception_handler(Exception, error_handler)
app.include_router(public_router)
app.include_router(ops_router)


@app.middleware("http")
async def record_api_metrics(request: Request, call_next):  # type: ignore[no-untyped-def]
    started = monotonic()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        route = request.scope.get("route")
        endpoint = getattr(route, "path", "__unmatched__")
        api_metrics.record(endpoint, status_code, started)


@app.get("/health", response_model=HealthPayload)
def health() -> HealthPayload:
    return build_health_payload()


@app.get("/ready", response_model=ReadinessPayload)
def ready(response: Response) -> ReadinessPayload:
    payload = build_readiness_payload()
    response.status_code = 200 if payload.status == "READY" else 503
    registry = default_metric_registry()
    registry.gauge("w2_readiness_status", 1 if payload.status == "READY" else 0)
    for check_name, check in payload.checks.items():
        registry.gauge(
            "w2_readiness_check_status",
            1 if check.status == "PASS" else 0,
            labels={"check": check_name},
        )
    return payload


@app.get("/metrics")
def metrics() -> Response:
    if get_settings().environment == Environment.PRODUCTION:
        raise HTTPException(status_code=403, detail="metrics disabled in production")
    body = default_metric_registry().prometheus_text()
    return Response(content=body, media_type="text/plain; version=0.0.4")
