from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pydantic import BaseModel

from w2.config import Settings, get_settings
from w2.providers.ledger import provider_timeout_count_since


class HealthPayload(BaseModel):
    service: str
    version: str
    environment: str
    provider_timeouts_24h: int | None


def build_health_payload(settings: Settings | None = None) -> HealthPayload:
    resolved = settings or get_settings()
    try:
        timeout_count = provider_timeout_count_since(datetime.now(UTC) - timedelta(hours=24))
    except Exception:
        timeout_count = None
    return HealthPayload(
        service=resolved.service_name,
        version=resolved.service_version,
        environment=resolved.environment.value,
        provider_timeouts_24h=timeout_count,
    )
