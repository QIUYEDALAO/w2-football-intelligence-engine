"""决策点自动 forward：scheduler 扫描 decision_at 到点且未决策的 fixture。

验收第 1 项（decision_at 到点自动落账本、无需读取调用）的「任务落账本」在
test_ah_ou_v9_system_pg.py::test_ah_ou_decision_forward_task_writes_ledger 覆盖；
本文件覆盖「扫描」：只有 kickoff-2h 已到点且 kickoff 未到、且账本尚无任何
market 行的 fixture 才被派发。
"""
from __future__ import annotations

import os
import subprocess
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import create_engine, text

from w2.config import get_settings


@pytest.fixture
def forward_pg(tmp_path: Any, monkeypatch: Any) -> None:
    url = os.environ.get("W2_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("W2_TEST_POSTGRES_URL required")
    admin = create_engine(url, isolation_level="AUTOCOMMIT")
    name = "w2_fwd_" + uuid.uuid4().hex[:12]
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{name}"'))
    db = url.rsplit("/", 1)[0] + "/" + name
    monkeypatch.setenv("W2_DATABASE_URL", db)
    monkeypatch.setenv("W2_ENVIRONMENT", "test")
    get_settings.cache_clear()
    subprocess.run(
        [".venv/bin/alembic", "upgrade", "head"],
        check=True,
        env=os.environ.copy(),
        capture_output=True,
    )
    yield


def _seed_identity(monkeypatch: Any, fid: str, kickoff: datetime) -> None:
    from w2.matchday.repository import MatchdayRuntimeRepository

    MatchdayRuntimeRepository().upsert_fixture_identities_with_business_changes(
        [
            {
                "fixture_id": f"api_football:{fid}",
                "provider": "api_football",
                "provider_fixture_id": fid,
                "competition_id": "allsvenskan",
                "provider_league_id": "113",
                "season": "2026",
                "kickoff_utc": kickoff,
                "fixture_status": "NS",
                "home_provider_team_id": "10",
                "away_provider_team_id": "20",
                "home_w2_team_id": "H",
                "away_w2_team_id": "A",
                "team_identity_status": "READY",
                "raw_payload_sha256": "a" * 64,
                "endpoint_capture_id": None,
                "captured_at": kickoff - timedelta(days=1),
                "identity_hash": "b" * 64,
                "payload": {},
            }
        ]
    )


def test_ah_ou_decision_forward_tick_scans_only_due_undecided(
    forward_pg: None, monkeypatch: Any
) -> None:
    from w2.ingestion.future_refresh_repository import FutureRefreshDbRepository

    engine = FutureRefreshDbRepository().engine
    now = datetime.now(UTC)
    _seed_identity(monkeypatch, "1001", now + timedelta(hours=1))  # 到点未决策
    _seed_identity(monkeypatch, "1002", now + timedelta(hours=5))  # 未到点
    _seed_identity(monkeypatch, "1003", now + timedelta(hours=1))  # 到点已决策
    with engine.begin() as c:
        c.execute(
            text(
                """
                INSERT INTO ah_ou_decision_ledger
                (decision_id, fixture_id, market, decision_at, model_version,
                 calibration_version, input_hash, full_distribution,
                 quote_identity_hash, source_capture_sha256, capture_id, source_id,
                 home_team_id, away_team_id, selected, score, created_at)
                VALUES ('d-1003', '1003', 'ASIAN_HANDICAP', now(), 'm1', 'c1',
                        'x', '{}', 'q', 's', 'cap', 'src', 'H', 'A', false, '0', now())
                """
            )
        )

    sent: list[str] = []
    monkeypatch.setattr(
        "apps.worker.celery_app.celery_app.send_task",
        lambda *args, **kwargs: sent.append(str(kwargs.get("kwargs", {}).get("fixture_id"))),
    )
    monkeypatch.setenv("W2_AH_OU_DECISION_FORWARD_ENABLED", "true")

    from apps.scheduler.main import ah_ou_decision_forward_tick

    result = ah_ou_decision_forward_tick()
    assert result["status"] == "QUEUED", result
    assert result["fixture_ids"] == ["1001"], result
    assert sent == ["1001"], sent


def test_ah_ou_decision_forward_tick_nothing_due(forward_pg: None, monkeypatch: Any) -> None:
    from apps.scheduler.main import ah_ou_decision_forward_tick

    monkeypatch.setenv("W2_AH_OU_DECISION_FORWARD_ENABLED", "true")
    result = ah_ou_decision_forward_tick()
    assert result["status"] == "NOTHING_DUE", result
