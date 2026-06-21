from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from w2.api.routers import error_handler, ops_router, public_router
from w2.monitoring.health import HealthPayload, build_health_payload

app = FastAPI(title="W2 Football Intelligence Engine", version="0.2.0")
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


@app.get("/health", response_model=HealthPayload)
def health() -> HealthPayload:
    return build_health_payload()


@app.get("/ready", response_model=HealthPayload)
def ready() -> HealthPayload:
    return build_health_payload()
