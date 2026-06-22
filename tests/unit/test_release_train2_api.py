from __future__ import annotations

from apps.api.main import app
from fastapi.testclient import TestClient


def test_release_train2_ops_routes_are_read_only() -> None:
    client = TestClient(app)
    for path in [
        "/ops/gates/5-preflight",
        "/ops/w1-w2-shadow-comparison",
        "/ops/shadow-strategy/status",
    ]:
        response = client.get(path)
        assert response.status_code == 200
    assert client.post("/ops/gates/5-preflight").status_code == 405
