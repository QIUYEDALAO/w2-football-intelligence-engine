from __future__ import annotations

import hashlib
import json
from pathlib import Path

from apps.api.main import app
from fastapi.testclient import TestClient

from w2.api.dashboard_read_models import (
    DashboardProjectionError,
    MatchdaySnapshotProjector,
    write_projection,
)
from w2.config import get_settings
from w2.infrastructure.database import Base, create_engine


def write_json(path: Path, payload: dict[str, object]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(payload, indent=2, sort_keys=True).encode()
    path.write_bytes(body)
    return hashlib.sha256(body).hexdigest()


def build_snapshot(root: Path) -> Path:
    snapshot = root / "20260622T140004_324054Z"
    normalized = {
        "rows": [
            {
                "fixture_id": "1489399",
                "bookmaker_id": "4",
                "bookmaker_name": "Pinnacle",
                "market_type": "ONE_X_TWO",
                "canonical_selection": "ARGENTINA_WIN",
                "normalized_line": None,
                "odds_value": "1.51",
                "captured_at_utc": "2026-06-22T14:00:04.324054Z",
                "provider_updated_at": "2026-06-22T17:00:00+00:00",
                "stale": False,
                "suspended": False,
                "live": False,
            },
            {
                "fixture_id": "1489399",
                "bookmaker_id": "5",
                "bookmaker_name": "SBO",
                "market_type": "ASIAN_HANDICAP",
                "canonical_selection": "AUSTRIA",
                "normalized_line": "+1",
                "odds_value": "2.17",
                "captured_at_utc": "2026-06-22T14:00:04.324054Z",
                "provider_updated_at": "2026-06-22T17:00:00+00:00",
                "stale": False,
                "suspended": False,
                "live": False,
            },
            {
                "fixture_id": "1489399",
                "bookmaker_id": "6",
                "bookmaker_name": "Betfair",
                "market_type": "TOTALS",
                "canonical_selection": "UNDER",
                "normalized_line": "2.5",
                "odds_value": "1.96",
                "captured_at_utc": "2026-06-22T14:00:04.324054Z",
                "provider_updated_at": "2026-06-22T17:00:00+00:00",
                "stale": False,
                "suspended": False,
                "live": False,
            },
        ]
    }
    decision = {
        "state": "WATCH",
        "most_likely_outcome": "ARGENTINA_WIN",
        "research_value_lean": "WATCH_VALUE_AUSTRIA_WIN_ONE_X_TWO_NO_LINE",
        "formal_recommendation": False,
        "candidate": False,
        "gate4_status": "PROVISIONAL_FORWARD_HOLDOUT_PENDING",
        "selected_value": {"market": "ONE_X_TWO", "selection": "AUSTRIA_WIN"},
    }
    model = {
        "probabilities": {
            "ARGENTINA_WIN": 0.52320320572583,
            "DRAW": 0.2507510531818066,
            "AUSTRIA_WIN": 0.2260457410923633,
        },
        "expected_goals": {"argentina": 1.595, "austria": 0.955},
        "score_matrix_probability_sum": 1.0,
        "score_matrix_top": [{"score": "1-0", "probability": 0.12454}],
        "value_rows": [
            {
                "market": "ONE_X_TWO",
                "selection": "ARGENTINA_WIN",
                "line": None,
                "market_fair_probability": 0.6709803443189662,
                "captured_at_utc": "2026-06-22T14:00:04.324054Z",
                "executable_odds": "1.51",
                "available_bookmaker_count": 14,
                "status": "READY",
            },
            {
                "market": "ONE_X_TWO",
                "selection": "DRAW",
                "line": None,
                "market_fair_probability": 0.21182347798654705,
                "captured_at_utc": "2026-06-22T14:00:04.324054Z",
                "executable_odds": "4.50",
                "available_bookmaker_count": 14,
                "status": "READY",
            },
            {
                "market": "ONE_X_TWO",
                "selection": "AUSTRIA_WIN",
                "line": None,
                "market_fair_probability": 0.11719617769448673,
                "captured_at_utc": "2026-06-22T14:00:04.324054Z",
                "executable_odds": "8.25",
                "available_bookmaker_count": 14,
                "status": "READY",
            },
        ],
    }
    quality = {
        "status": "READY",
        "fixture_identity": "PASS",
        "frozen_artifact_hash": "PASS",
        "feature_leakage": "PASS",
        "warnings": [],
    }
    fixture = {
        "payload": {
            "response": [
                {
                    "fixture": {
                        "id": 1489399,
                        "date": "2026-06-22T17:00:00Z",
                        "status": {"short": "NS"},
                        "venue": {"name": "Synthetic Stadium"},
                    },
                    "league": {"id": 1, "name": "FIFA World Cup", "round": "Group J"},
                    "teams": {
                        "home": {"id": 26, "name": "Argentina"},
                        "away": {"id": 775, "name": "Austria"},
                    },
                }
            ]
        }
    }
    normalized_sha = write_json(snapshot / "normalized_odds.json", normalized)
    decision_sha = write_json(snapshot / "decision.json", decision)
    write_json(snapshot / "model_output.json", model)
    write_json(snapshot / "data_quality.json", quality)
    write_json(snapshot / "raw" / "01_fixture_detail.json", fixture)
    write_json(snapshot / "raw" / "02_odds.json", {"payload": {"response": []}})
    write_json(snapshot / "raw" / "03_lineups.json", {"payload": {"response": []}})
    write_json(snapshot / "raw" / "04_injuries.json", {"payload": {"response": []}})
    write_json(
        snapshot / "manifest.json",
        {
            "fixture_id": "1489399",
            "phase": "T-3h",
            "captured_at_utc": "2026-06-22T14:00:04.324054Z",
            "kickoff_utc": "2026-06-22T17:00:00Z",
            "append_only": True,
            "previous_snapshot_id": None,
            "remaining_quota": 6934,
            "request_count": 6,
            "normalized_data_sha256": normalized_sha,
            "decision_sha256": decision_sha,
            "model_artifact_sha256": "model_hash",
            "calibration_sha256": "calibration_hash",
        },
    )
    return snapshot


def test_projector_validates_and_writes_idempotent_read_model(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "snapshots"
    build_snapshot(root)
    projection = MatchdaySnapshotProjector(root).project_latest("1489399")
    assert projection.fixture["fixture_id"] == "1489399"
    assert projection.fixture["decision_status"] == "WATCH"
    assert projection.fixture["formal_recommendation"] is False
    db_path = tmp_path / "stage10b.db"
    monkeypatch.setenv("W2_DATABASE_URL", f"sqlite+pysqlite:///{db_path}")
    get_settings.cache_clear()
    engine = create_engine()
    Base.metadata.create_all(engine)
    write_projection(engine, projection)
    write_projection(engine, projection)
    client = TestClient(app)
    fixtures = client.get("/v1/fixtures").json()["items"]
    assert len(fixtures) == 1
    assert fixtures[0]["fixture_id"] == "1489399"
    detail = client.get("/v1/fixtures/1489399").json()
    assert detail["bookmaker_count"] == 3
    market = client.get("/v1/fixtures/1489399/market-probabilities").json()
    model = client.get("/v1/fixtures/1489399/model-probabilities").json()
    assert market["probability_type"] == "market_fair_probability"
    assert model["probability_type"] == "independent_model_probability"
    assert "ARGENTINA_WIN" in market["probabilities"]
    get_settings.cache_clear()


def test_projector_rejects_hash_mismatch(tmp_path: Path) -> None:
    root = tmp_path / "snapshots"
    snapshot = build_snapshot(root)
    manifest = json.loads((snapshot / "manifest.json").read_text())
    manifest["decision_sha256"] = "bad"
    write_json(snapshot / "manifest.json", manifest)
    try:
        MatchdaySnapshotProjector(root).project_latest("1489399")
    except DashboardProjectionError as exc:
        assert "decision_sha256 mismatch" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("hash mismatch was not rejected")


def test_web_proxy_and_no_api_host_hardcoding() -> None:
    web = Path("apps/web/src/main.tsx").read_text()
    nginx = Path("apps/web/nginx.conf").read_text()
    compose = Path("infra/compose/compose.staging.yml").read_text()
    assert 'const API_BASE = "/v1"' in web
    assert "${API_BASE}/fixtures" in web
    assert "Live read-model dashboard" not in web
    assert "127.0.0.1:18000" not in web
    assert "api:8000" not in web
    assert "location /api/" in nginx
    assert "location /v1/" in nginx
    assert "proxy_pass http://api:8000/" in nginx
    assert "proxy_pass http://api:8000/v1/" in nginx
    assert "VITE_API_BASE_URL" not in compose
