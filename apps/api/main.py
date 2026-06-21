from __future__ import annotations

from fastapi import FastAPI

from w2.monitoring.health import HealthPayload, build_health_payload

app = FastAPI(title="W2 Football Intelligence Engine", version="0.2.0")


@app.get("/health", response_model=HealthPayload)
def health() -> HealthPayload:
    return build_health_payload()


@app.get("/ready", response_model=HealthPayload)
def ready() -> HealthPayload:
    return build_health_payload()

