from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from apps.api.main import app
from fastapi.testclient import TestClient

import w2.api.repository as repository
from w2.config import get_settings


def write_fixture_payload(root: Path) -> None:
    raw = root / "stage7c/raw"
    raw.mkdir(parents=True)
    future_kickoff = (datetime.now(UTC) + timedelta(days=180)).replace(microsecond=0)
    payload = {
        "payload": {
            "response": [
                {
                    "fixture": {
                        "id": 900001,
                        "date": future_kickoff.isoformat(),
                        "status": {"short": "NS"},
                        "venue": {"name": "Test Venue"},
                    },
                    "league": {
                        "id": 1,
                        "name": "World Cup",
                        "round": "Test Round",
                    },
                    "teams": {
                        "home": {"id": 1001, "name": "Test Home"},
                        "away": {"id": 1002, "name": "Test Away"},
                    },
                }
            ]
        }
    }
    (raw / "test_fixtures.json").write_text(json.dumps(payload), encoding="utf-8")


def write_future_refresh_payload(root: Path) -> None:
    read_model = root / "future_refresh/read_model"
    read_model.mkdir(parents=True)
    fixture = {
        "fixture": {
            "id": "legacy-file-fixture",
            "date": "2026-12-31T17:00:00+00:00",
            "status": {"short": "NS"},
            "venue": {"name": "Future Venue"},
        },
        "league": {"id": 1, "name": "World Cup", "round": "Group K"},
        "teams": {
            "home": {"id": 3001, "name": "Future Home"},
            "away": {"id": 3002, "name": "Future Away"},
        },
    }
    (read_model / "fixtures.json").write_text(
        json.dumps({"items": [fixture]}),
        encoding="utf-8",
    )
    (read_model / "market_snapshots.json").write_text(
        json.dumps(
            [
                {
                    "fixture_id": "1489404",
                    "captured_at": "2026-12-31T10:00:00Z",
                    "bookmaker_count": 14,
                    "quality": "READY",
                }
            ]
        ),
        encoding="utf-8",
    )
    (read_model / "latest_market_observations.json").write_text(
        json.dumps(
            [
                {
                    "observation_id": "obs-1",
                    "fixture_id": "1489404",
                    "provider": "api_football",
                    "bookmaker_id": "1",
                    "bookmaker_name": "Book A",
                    "canonical_market": "ONE_X_TWO",
                    "selection": "HOME",
                    "line": None,
                    "decimal_odds": "1.80",
                    "captured_at": "2026-12-31T10:00:00Z",
                    "provider_updated_at": "2026-12-31T09:59:00Z",
                },
                {
                    "observation_id": "obs-2",
                    "fixture_id": "1489404",
                    "provider": "api_football",
                    "bookmaker_id": "2",
                    "bookmaker_name": "Book B",
                    "canonical_market": "TOTALS",
                    "selection": "OVER",
                    "line": "2.5",
                    "decimal_odds": "1.92",
                    "captured_at": "2026-12-31T10:01:00Z",
                    "provider_updated_at": "2026-12-31T10:00:00Z",
                },
            ]
        ),
        encoding="utf-8",
    )
    (read_model / "provider_status.json").write_text(
        json.dumps(
            {
                "provider": "api_football",
                "status": "READY",
                "remaining_quota": 6323,
                "credential_status": "PRESENT",
                "last_request_status": 200,
            }
        ),
        encoding="utf-8",
    )


def test_load_json_treats_unreadable_legacy_runtime_as_missing(tmp_path: Path) -> None:
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    target = blocked / "fixtures.json"
    target.write_text('{"items": []}', encoding="utf-8")
    blocked.chmod(0)
    try:
        assert repository.load_json(target, {"items": ["fallback"]}) == {
            "items": ["fallback"]
        }
    finally:
        blocked.chmod(0o700)


def test_load_json_treats_invalid_json_as_missing(tmp_path: Path) -> None:
    target = tmp_path / "broken.json"
    target.write_text("{", encoding="utf-8")

    assert repository.load_json(target, {"fallback": True}) == {"fallback": True}


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


def test_fixture_filters_detail_probabilities_and_errors(
    tmp_path: Path, monkeypatch
) -> None:
    write_fixture_payload(tmp_path)
    monkeypatch.setattr(repository, "RUNTIME", tmp_path)
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


def test_future_refresh_db_projection_feeds_fixtures_and_provider_status(
    tmp_path: Path,
    monkeypatch,
) -> None:
    write_future_refresh_payload(tmp_path)
    monkeypatch.setattr(repository, "RUNTIME", tmp_path)

    class DbRepository:
        def fixture_payloads(self) -> list[dict[str, Any]]:
            return [
                {
                    "fixture": {
                        "id": 1489404,
                        "date": "2026-12-31T17:00:00+00:00",
                        "status": {"short": "NS"},
                        "venue": {"name": "Future Venue"},
                    },
                    "league": {"id": 1, "name": "World Cup", "round": "Group K"},
                    "teams": {
                        "home": {"id": 3001, "name": "Future Home"},
                        "away": {"id": 3002, "name": "Future Away"},
                    },
                }
            ]

        def market_snapshots(self) -> list[dict[str, Any]]:
            return [
                {
                    "fixture_id": "1489404",
                    "captured_at": "2026-12-31T10:00:00+00:00",
                    "bookmaker_count": 14,
                    "quality": "READY",
                }
            ]

        def latest_market_observations(self) -> list[dict[str, Any]]:
            return [
                {
                    "observation_id": "obs-1",
                    "fixture_id": "1489404",
                    "provider": "api_football",
                    "bookmaker_id": "1",
                    "bookmaker_name": "Book A",
                    "canonical_market": "ONE_X_TWO",
                    "selection": "HOME",
                    "line": None,
                    "decimal_odds": "1.80",
                    "captured_at": "2026-12-31T10:00:00Z",
                    "provider_updated_at": "2026-12-31T09:59:00Z",
                },
                {
                    "observation_id": "obs-2",
                    "fixture_id": "1489404",
                    "provider": "api_football",
                    "bookmaker_id": "2",
                    "bookmaker_name": "Book B",
                    "canonical_market": "TOTALS",
                    "selection": "OVER",
                    "line": "2.5",
                    "decimal_odds": "1.92",
                    "captured_at": "2026-12-31T10:01:00Z",
                    "provider_updated_at": "2026-12-31T10:00:00Z",
                },
            ]

        def provider_status(self) -> dict[str, Any]:
            return {
                "status": "READY",
                "remaining_quota": 6323,
                "last_request_status": 200,
                "last_successful_refresh_at": None,
                "blockers": [],
            }

    monkeypatch.setattr(repository, "future_refresh_db_repository", lambda: DbRepository())
    client = TestClient(app)

    fixtures = client.get("/v1/fixtures?page_size=10&status=NS&timezone=UTC").json()["items"]
    assert [item["fixture_id"] for item in fixtures] == ["1489404"]
    detail = client.get("/v1/fixtures/1489404").json()
    assert detail["bookmaker_count"] == 14
    assert detail["market_coverage"]["TOTALS"]
    timeline = client.get("/v1/fixtures/1489404/odds-timeline").json()["items"]
    assert timeline[0]["bookmaker"] == "Book A"
    assert timeline[0]["closing"] is False
    assert {item["market"] for item in timeline} >= {"ONE_X_TWO", "TOTALS"}
    provider = client.get("/v1/providers/status").json()
    assert provider["remaining_quota"] == 6323
    assert "blockers" in provider


def test_future_refresh_hides_past_ns_fixture_from_default_list(
    tmp_path: Path,
    monkeypatch,
) -> None:
    write_fixture_payload(tmp_path)
    payload_path = tmp_path / "stage7c/raw/test_fixtures.json"
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    payload["payload"]["response"][0]["fixture"]["date"] = "2026-06-22T00:00:00+00:00"
    payload_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(repository, "RUNTIME", tmp_path)
    client = TestClient(app)

    fixtures = client.get("/v1/fixtures?page_size=10&status=NS&timezone=UTC").json()["items"]
    health = client.get("/v1/data-health").json()

    assert fixtures == []
    assert health["stale_data_count"] == 1


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
