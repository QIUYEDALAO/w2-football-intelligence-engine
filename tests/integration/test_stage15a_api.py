from __future__ import annotations

from apps.api.main import app
from fastapi.testclient import TestClient

from w2.config import get_settings


def test_operations_governance_endpoints(monkeypatch) -> None:
    monkeypatch.setenv("W2_ENVIRONMENT", "test")
    get_settings.cache_clear()
    client = TestClient(app)
    assert client.get("/ops/operations/cycles").status_code == 200
    latest = client.get("/ops/operations/latest")
    assert latest.status_code == 200
    assert "latest" in latest.json()
    release = client.get("/ops/releases/readiness")
    assert release.status_code == 200
    assert release.json()["production_release"] == "DISABLED"
    retention = client.get("/ops/retention/status")
    assert retention.status_code == 200
    assert retention.json()["status"] == "DRY_RUN_ONLY"


def test_operations_governance_production_reject(monkeypatch) -> None:
    client = TestClient(app)
    monkeypatch.setenv("W2_ENVIRONMENT", "production")
    get_settings.cache_clear()
    try:
        assert client.get("/ops/operations/cycles").status_code == 403
        assert client.get("/ops/releases/readiness").status_code == 403
    finally:
        monkeypatch.setenv("W2_ENVIRONMENT", "local")
        get_settings.cache_clear()


def test_no_governance_recommendation_routes() -> None:
    schema = TestClient(app).get("/openapi.json").json()
    paths = "\n".join(schema["paths"]).lower()
    assert "deepseek" not in paths
    assert "candidate" not in paths
    assert "recommend" not in paths
