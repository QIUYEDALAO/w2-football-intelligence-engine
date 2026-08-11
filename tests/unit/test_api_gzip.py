from apps.api.main import app
from fastapi.testclient import TestClient


def test_large_json_responses_support_gzip() -> None:
    with TestClient(app) as client:
        response = client.get("/openapi.json", headers={"Accept-Encoding": "gzip"})

    assert response.status_code == 200
    assert response.headers["content-encoding"] == "gzip"
