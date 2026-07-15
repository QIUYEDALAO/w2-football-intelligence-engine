from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from pydantic import BaseModel
from sqlalchemy import inspect, text

from w2.config import Environment, Settings, get_settings
from w2.infrastructure.cache import redis_status
from w2.infrastructure.database import create_engine, database_status
from w2.models.r4_1_artifacts import load_r4_1_artifacts, r4_1_artifact_dir

REQUIRED_READ_MODEL_TABLES = {
    "fixtures",
    "future_market_observation",
    "forward_result_event",
}


class HealthPayload(BaseModel):
    service: str
    version: str
    environment: str
    status: str
    database: str = "not_checked"
    redis: str = "not_checked"


class ReadinessPayload(HealthPayload):
    ready: bool
    checks: dict[str, str]


def build_health_payload(settings: Settings | None = None) -> HealthPayload:
    """Process liveness only; never calls an external dependency."""
    resolved = settings or get_settings()
    return HealthPayload(
        service=resolved.service_name,
        version=resolved.service_version,
        environment=resolved.environment.value,
        status="ok",
    )


def build_readiness_payload(settings: Settings | None = None) -> ReadinessPayload:
    resolved = settings or get_settings()
    checks = {
        "database": database_status(resolved),
        "redis": _redis_readiness(resolved),
        "artifact": _artifact_readiness(resolved),
        "read_model": _read_model_readiness(resolved),
        "schema": _schema_readiness(resolved),
    }
    ready = all(value in {"ok", "disabled_by_policy"} for value in checks.values())
    return ReadinessPayload(
        service=resolved.service_name,
        version=resolved.service_version,
        environment=resolved.environment.value,
        status="ready" if ready else "not_ready",
        database=checks["database"],
        redis=checks["redis"],
        ready=ready,
        checks=checks,
    )


def _redis_readiness(settings: Settings) -> str:
    status = redis_status(settings)
    if status == "disabled" and settings.environment in {Environment.LOCAL, Environment.TEST}:
        return "disabled_by_policy"
    return status


def _artifact_readiness(settings: Settings) -> str:
    result = load_r4_1_artifacts(r4_1_artifact_dir(Path.cwd()))
    if result.invalid_reasons:
        return "invalid"
    if result.artifacts:
        return "ok"
    return (
        "disabled_by_policy"
        if settings.environment in {Environment.LOCAL, Environment.TEST}
        else "missing"
    )


def _read_model_readiness(settings: Settings) -> str:
    try:
        engine = create_engine(settings)
        tables = set(inspect(engine).get_table_names())
        engine.dispose()
    except Exception:
        return "unavailable"
    missing = REQUIRED_READ_MODEL_TABLES - tables
    return "ok" if not missing else "missing"


def _schema_readiness(settings: Settings) -> str:
    config_path = Path.cwd() / "alembic.ini"
    if not config_path.exists():
        return "unavailable"
    try:
        expected = ScriptDirectory.from_config(Config(str(config_path))).get_current_head()
        engine = create_engine(settings)
        with engine.connect() as connection:
            actual = connection.execute(text("select version_num from alembic_version")).scalar()
        engine.dispose()
    except Exception:
        return "unavailable"
    return "ok" if expected and actual == expected else "mismatch"
