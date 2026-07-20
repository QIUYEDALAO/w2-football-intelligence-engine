from __future__ import annotations

from apps.api import main as api_main
from apps.api.main import app
from fastapi.testclient import TestClient

from w2.api import routers
from w2.monitoring.readiness import (
    ProviderIntakeOperationalReadinessV1,
    ReadinessCheck,
    ReadinessPayload,
)


def _ready_payload(*, ready: bool = True) -> ReadinessPayload:
    status = "PASS" if ready else "FAIL"
    return ReadinessPayload(
        service="w2-football-intelligence-engine",
        version="0.2.0",
        environment="test",
        status="READY" if ready else "NOT_READY",
        checks={
            "database": ReadinessCheck(
                status=status,
                critical=True,
                detail="test dependency",
            )
        },
        warnings=[],
        matchday_intake_status="NOT_READY",
        matchday_intake=ProviderIntakeOperationalReadinessV1(
            environment="test",
            allow_live=True,
            provider_calls_disabled=False,
            scheduler_enabled=False,
            future_refresh_enabled=False,
            competition_ids=[],
            allsvenskan_registered=False,
            api_key_visible_to_worker=False,
            endpoint_allowlist=["fixtures", "odds", "status"],
            db_persistence=True,
            redis_dedupe=False,
            worker_task_registered=True,
            last_error_code="MATCHDAY_INTAKE_STAGING_ONLY",
            ready=False,
            blockers=["MATCHDAY_INTAKE_STAGING_ONLY"],
        ),
    )


def test_health_is_pure_liveness_without_dependency_fields() -> None:
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"service", "version", "environment"}
    assert payload["service"] == "w2-football-intelligence-engine"
    assert payload["version"] == "0.2.0"


def test_ready_returns_503_when_a_critical_check_fails(monkeypatch) -> None:
    monkeypatch.setattr(api_main, "build_readiness_payload", lambda: _ready_payload(ready=False))
    response = TestClient(app).get("/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "NOT_READY"


def test_v1_ready_has_identical_semantics_and_deprecation_headers(monkeypatch) -> None:
    payload = _ready_payload()
    monkeypatch.setattr(api_main, "build_readiness_payload", lambda: payload)
    monkeypatch.setattr(routers, "build_readiness_payload", lambda: payload)
    client = TestClient(app)
    canonical = client.get("/ready")
    legacy = client.get("/v1/ready")
    assert canonical.status_code == legacy.status_code == 200
    assert canonical.json() == legacy.json()
    assert legacy.headers["deprecation"] == "true"
    assert legacy.headers["link"] == '</ready>; rel="canonical"'


def test_v1_health_is_also_pure_liveness() -> None:
    response = TestClient(app).get("/v1/health")
    assert response.status_code == 200
    assert set(response.json()) == {"service", "version", "environment"}
