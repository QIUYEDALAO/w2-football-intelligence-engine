from __future__ import annotations

from apps.api.main import app
from fastapi.testclient import TestClient


def test_health_returns_public_status_without_secrets() -> None:
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == "w2-football-intelligence-engine"
    assert payload["version"] == "0.2.0"
    assert "password" not in str(payload).lower()


def test_ready_returns_public_status_without_secrets() -> None:
    response = TestClient(app).get("/ready")
    assert response.status_code == 200
    payload = response.json()
    assert {"service", "version", "environment", "database", "redis"} <= set(payload)

