from __future__ import annotations

from apps.api.main import app
from fastapi.testclient import TestClient

from w2.config import get_settings


def test_league_list_and_readiness_endpoints() -> None:
    client = TestClient(app)
    response = client.get("/v1/leagues")
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 5
    first_id = items[0]["competition_id"]
    readiness = client.get(f"/v1/leagues/{first_id}/readiness")
    assert readiness.status_code == 200
    assert readiness.json()["checklist"]["production"] == "DISABLED"


def test_ops_league_onboarding_and_production_reject(monkeypatch) -> None:
    monkeypatch.setenv("W2_ENVIRONMENT", "test")
    get_settings.cache_clear()
    client = TestClient(app)
    response = client.get("/ops/league-onboarding")
    assert response.status_code == 200
    assert len(response.json()["items"]) == 5
    monkeypatch.setenv("W2_ENVIRONMENT", "production")
    get_settings.cache_clear()
    try:
        assert client.get("/ops/league-onboarding").status_code == 403
    finally:
        monkeypatch.setenv("W2_ENVIRONMENT", "local")
        get_settings.cache_clear()


def test_no_deepseek_candidate_or_recommend_routes_for_leagues() -> None:
    schema = TestClient(app).get("/openapi.json").json()
    paths = "\n".join(schema["paths"]).lower()
    assert "deepseek" not in paths
    assert "candidate" not in paths
    assert "recommend" not in paths
