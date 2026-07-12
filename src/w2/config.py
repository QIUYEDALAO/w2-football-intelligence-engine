from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    LOCAL = "local"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="W2_", env_file=None, extra="ignore")

    environment: Environment = Environment.LOCAL
    service_name: str = "w2-football-intelligence-engine"
    service_version: str = "0.2.0"
    database_url: SecretStr = Field(default=SecretStr("sqlite+pysqlite:///.local/w2.db"))
    redis_url: SecretStr | None = None
    celery_broker_url: SecretStr | None = None
    celery_result_backend: SecretStr | None = None
    minio_endpoint: str | None = None
    runtime_root: Path = Path("runtime")

    @field_validator("database_url", "redis_url", "celery_broker_url", "celery_result_backend")
    @classmethod
    def reject_w1_paths(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return value
        raw = value.get_secret_value()
        if "/w1_world_cup_engine" in raw or "/v2_football_quant" in raw:
            raise ValueError("W2 configuration must not depend on W1 or legacy project paths")
        return value

    @property
    def safe_database_label(self) -> str:
        url = self.database_url.get_secret_value()
        return url.split(":", 1)[0]

    @property
    def resolved_runtime_root(self) -> Path:
        if self.runtime_root.is_absolute():
            return self.runtime_root
        return Path.cwd() / self.runtime_root


@lru_cache
def get_settings() -> Settings:
    return Settings()
