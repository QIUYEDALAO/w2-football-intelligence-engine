from __future__ import annotations

import apps.api.main as api_main
import pytest
from apps.api.main import app
from fastapi.testclient import TestClient

import w2.api.routers as api_routers
from w2.config import Environment, Settings
from w2.monitoring import health as health_module
from w2.monitoring.health import ReadinessPayload


def test_health_returns_public_status_without_secrets() -> None:
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == "w2-football-intelligence-engine"
    assert payload["version"] == "0.2.0"
    assert "password" not in str(payload).lower()


def test_health_is_liveness_and_does_not_probe_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_called(*_: object, **__: object) -> str:
        raise AssertionError("liveness must not probe dependencies")

    monkeypatch.setattr(health_module, "database_status", fail_if_called)
    monkeypatch.setattr(health_module, "redis_status", fail_if_called)

    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["database"] == "not_checked"
    assert response.json()["redis"] == "not_checked"


@pytest.mark.parametrize("path", ["/ready", "/v1/ready"])
def test_ready_returns_503_when_a_critical_dependency_fails(
    path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = ReadinessPayload(
        service="w2-football-intelligence-engine",
        version="0.2.0",
        environment="staging",
        status="not_ready",
        database="unavailable",
        redis="ok",
        ready=False,
        checks={
            "database": "unavailable",
            "redis": "ok",
            "artifact": "ok",
            "read_model": "ok",
            "schema": "ok",
        },
    )
    monkeypatch.setattr(api_main, "build_readiness_payload", lambda: payload, raising=False)
    monkeypatch.setattr(api_routers, "build_readiness_payload", lambda: payload, raising=False)

    response = TestClient(app).get(path)

    assert response.status_code == 503
    assert response.json()["ready"] is False
    assert response.json()["checks"]["database"] == "unavailable"


def test_readiness_requires_database_redis_artifact_read_model_and_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(environment=Environment.STAGING)
    monkeypatch.setattr(health_module, "database_status", lambda _: "ok")
    monkeypatch.setattr(health_module, "_redis_readiness", lambda _: "ok")
    monkeypatch.setattr(health_module, "_artifact_readiness", lambda _: "ok")
    monkeypatch.setattr(health_module, "_read_model_readiness", lambda _: "ok")
    monkeypatch.setattr(health_module, "_schema_readiness", lambda _: "ok")

    payload = health_module.build_readiness_payload(settings)

    assert payload.ready is True
    assert payload.status == "ready"
    assert set(payload.checks) == {"database", "redis", "artifact", "read_model", "schema"}


def test_v1_health_alias_returns_status_without_secrets() -> None:
    client = TestClient(app)
    response = client.get("/v1/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == "w2-football-intelligence-engine"
    assert "password" not in str(payload).lower()
