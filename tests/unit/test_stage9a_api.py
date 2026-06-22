from __future__ import annotations

from apps.api.main import app
from fastapi.testclient import TestClient


def test_shadow_strategy_ops_endpoints_are_read_only() -> None:
    client = TestClient(app)
    for path in [
        "/ops/shadow-strategy/status",
        "/ops/shadow-strategy/locks",
        "/ops/shadow-strategy/evaluations",
        "/ops/shadow-strategy/replay",
    ]:
        response = client.get(path)
        assert response.status_code == 200
    assert client.post("/ops/shadow-strategy/status").status_code == 405


def test_no_public_recommendation_routes() -> None:
    client = TestClient(app)
    assert client.get("/v1/recommendations").status_code == 404
    assert client.get("/v1/candidates").status_code == 404
    assert client.get("/v1/deepseek").status_code == 404
