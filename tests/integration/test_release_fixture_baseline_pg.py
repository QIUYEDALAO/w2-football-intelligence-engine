"""Offline release baseline uses actual PG with read-only fixture authority."""

import importlib.util
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

pytest_plugins = ["tests.integration.test_ah_ou_v9_system_pg"]


def tool():
    path = Path(__file__).resolve().parents[2] / "scripts/w2_safe_pause_identity.py"
    spec = importlib.util.spec_from_file_location("offline_release_baseline", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_offline_fixture_baseline_matches_real_api_and_noop_preserves_source(chain):
    from apps.api.main import app

    repo, _, _, _ = chain
    before = repo.engine.connect()
    original = before.execute(text(
        "SELECT fixture_id,kickoff_utc FROM matchday_fixture_identities ORDER BY fixture_id"
    )).all()
    before.close()
    module = tool()
    baseline = module.dashboard_baseline()
    assert module.dashboard_baseline() == baseline
    assert baseline["source"] == "readonly_dashboard_fixture_repository"
    with TestClient(app) as client:
        response = client.get("/v1/dashboard/intelligence-workspace")
    assert response.status_code == 200, response.text
    public = response.json()
    assert baseline["football_day_start_utc"] == public["football_day_start_utc"]
    assert {row["fixture_id"] for row in baseline["matches"]} == {
        row["fixture_id"] for row in public["matches"]
    }
    with repo.engine.connect() as connection:
        assert connection.execute(text(
            "SELECT fixture_id,kickoff_utc FROM matchday_fixture_identities ORDER BY fixture_id"
        )).all() == original


def test_offline_fixture_baseline_pg_forbids_writes_without_empty_fallback(chain, monkeypatch):
    from w2.api.repository import ReadModelRepository

    module = tool()
    control = module.dashboard_baseline()
    assert isinstance(control["matches"], list)

    def attempted_write(repository, **_kwargs):
        with repository._database_engine().begin() as connection:
            assert connection.scalar(text("SHOW transaction_read_only")) == "on"
            connection.execute(text("CREATE TABLE invalid_baseline_write (id integer)"))

    monkeypatch.setattr(ReadModelRepository, "dashboard_fixtures_for_window", attempted_write)
    with pytest.raises(DBAPIError, match="read-only transaction"):
        module.dashboard_baseline()
