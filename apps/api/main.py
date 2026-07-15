from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from w2.api.routers import error_handler, ops_router, public_router, service
from w2.config import Environment, get_settings
from w2.monitoring.health import (
    HealthPayload,
    ReadinessPayload,
    build_health_payload,
    build_readiness_payload,
)
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
app.add_middleware(GZipMiddleware, minimum_size=1_024, compresslevel=5)
app.add_exception_handler(Exception, error_handler)
app.include_router(public_router)
app.include_router(ops_router)


@app.get("/health", response_model=HealthPayload)
def health() -> HealthPayload:
    return build_health_payload()


@app.get("/ready", response_model=ReadinessPayload)
def ready(response: Response) -> ReadinessPayload:
    payload = build_readiness_payload()
    response.status_code = 200 if payload.ready else 503
    return payload


@app.get("/metrics")
def metrics() -> Response:
    if get_settings().environment == Environment.PRODUCTION:
        raise HTTPException(status_code=403, detail="metrics disabled in production")
    body = default_metric_registry().prometheus_text()
    return Response(content=body, media_type="text/plain; version=0.0.4")
