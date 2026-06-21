from __future__ import annotations

import json
from pathlib import Path

from apps.api.main import app
from fastapi.testclient import TestClient

from w2.config import get_settings


def test_public_read_endpoints_schema_and_etag() -> None:
    client = TestClient(app)
    response = client.get("/v1/fixtures?page=1&page_size=2&timezone=UTC")
    assert response.status_code == 200
    payload = response.json()
    assert payload["request_id"]
    assert payload["meta"]["page_size"] == 2
    assert "ETag" in response.headers
    cached = client.get(
        "/v1/fixtures?page=1&page_size=2&timezone=UTC",
        headers={"If-None-Match": response.headers["ETag"]},
    )
    assert cached.status_code == 304


def test_fixture_filters_detail_probabilities_and_errors() -> None:
    client = TestClient(app)
    fixtures = client.get(
        "/v1/fixtures?page_size=1&status=NS&timezone=Asia/Shanghai"
    ).json()["items"]
    assert fixtures
    fixture_id = fixtures[0]["fixture_id"]
    assert "+08:00" in fixtures[0]["kickoff_display"]
    detail = client.get(f"/v1/fixtures/{fixture_id}").json()
    assert detail["forward_decision"] in {"WATCH", "SKIP"}
    market = client.get(f"/v1/fixtures/{fixture_id}/market-probabilities").json()
    model = client.get(f"/v1/fixtures/{fixture_id}/model-probabilities").json()
    assert market["probability_type"] == "market_fair_probability"
    assert model["probability_type"] == "independent_model_probability"
    assert client.get("/v1/fixtures/not-a-fixture").status_code == 404
    assert client.get("/v1/fixtures?page_size=101").status_code == 422


def test_operations_read_only_and_production_disabled(monkeypatch) -> None:
    client = TestClient(app)
    assert client.get("/ops/health").status_code == 200
    assert client.get("/ops/quota").json()["items"][0]["key"] == "quota"
    for route in app.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", set()) or set()
        if path.startswith("/ops") or path.startswith("/v1"):
            assert methods <= {"GET", "HEAD"}
    monkeypatch.setenv("W2_ENVIRONMENT", "production")
    get_settings.cache_clear()
    try:
        assert client.get("/ops/health").status_code == 403
    finally:
        monkeypatch.setenv("W2_ENVIRONMENT", "local")
        get_settings.cache_clear()


def test_no_recommendation_candidate_or_deepseek_routes() -> None:
    forbidden = ("recommend", "candidate", "deepseek")
    for route in app.routes:
        path = getattr(route, "path", "").lower()
        assert not any(token in path for token in forbidden)


def test_openapi_snapshot_and_web_notice() -> None:
    snapshot = json.loads(Path("contracts/openapi/w2-stage10a-openapi.json").read_text())
    assert "/v1/fixtures" in snapshot["paths"]
    assert "/ops/gates" in snapshot["paths"]
    web = Path("apps/web/src/main.tsx").read_text()
    assert "正式推荐尚未启用，当前仅为研究与前瞻验证。" in web
    assert "AI 推荐" not in web
