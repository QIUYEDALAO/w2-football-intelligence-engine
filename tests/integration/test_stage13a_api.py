from __future__ import annotations

from apps.api.main import app
from fastapi.testclient import TestClient

from w2.config import get_settings


def test_world_cup_operations_profile_endpoint() -> None:
    response = TestClient(app).get("/v1/competitions/world_cup_2026/operations-profile")
    assert response.status_code == 200
    payload = response.json()
    assert payload["strategy_version"] == "NOT_AVAILABLE_GATE4"
    assert payload["competition_id"] == "world_cup_2026"
    assert payload["groups"]


def test_world_cup_readiness_ops_endpoint_and_production_reject(monkeypatch) -> None:
    client = TestClient(app)
    response = client.get("/ops/world-cup-readiness")
    assert response.status_code == 200
    assert response.json()["strategy_version"] == "NOT_AVAILABLE_GATE4"
    monkeypatch.setenv("W2_ENVIRONMENT", "production")
    get_settings.cache_clear()
    try:
        assert client.get("/ops/world-cup-readiness").status_code == 403
    finally:
        monkeypatch.setenv("W2_ENVIRONMENT", "local")
        get_settings.cache_clear()


def test_no_recommendation_or_deepseek_routes() -> None:
    schema = TestClient(app).get("/openapi.json").json()
    paths = "\n".join(schema["paths"])
    assert "recommend" not in paths.lower()
    assert "candidate" not in paths.lower()
    assert "deepseek" not in paths.lower()
