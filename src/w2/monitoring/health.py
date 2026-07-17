from __future__ import annotations

from pydantic import BaseModel

from w2.config import Settings, get_settings
from w2.infrastructure.cache import redis_status
from w2.infrastructure.database import database_status


class HealthPayload(BaseModel):
    service: str
    version: str
    environment: str
    database: str
    redis: str


def build_health_payload(settings: Settings | None = None) -> HealthPayload:
    resolved = settings or get_settings()
    return HealthPayload(
        service=resolved.service_name,
        version=resolved.service_version,
        environment=resolved.environment.value,
        database=database_status(resolved),
        redis=redis_status(resolved),
    )

