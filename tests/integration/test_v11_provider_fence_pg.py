"""Automatic Provider entry must be owned by a durable planned-window claim."""

from __future__ import annotations

import os
import subprocess
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from apps.worker import celery_app as worker
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from w2.config import get_settings
from w2.infrastructure.persistence.provider_side_effect_fence_models import (
    ProviderSideEffectFenceModel,
)
from w2.ingestion.provider_task_identity import xg_backfill_claim_key


@pytest.fixture
def fence_pg(monkeypatch):
    url = os.environ.get("W2_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("W2_TEST_POSTGRES_URL required")
    name = "w2_v11_fence_" + uuid.uuid4().hex[:12]
    admin = create_engine(url, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    db_url = url.rsplit("/", 1)[0] + "/" + name
    monkeypatch.setenv("W2_DATABASE_URL", db_url)
    monkeypatch.setenv("W2_ENVIRONMENT", "test")
    monkeypatch.setenv("W2_PROVIDER_SCHEDULER_ENABLED", "true")
    get_settings.cache_clear()
    subprocess.run(
        [".venv/bin/alembic", "upgrade", "head"],
        check=True,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
    )
    yield db_url
    get_settings.cache_clear()
    admin.dispose()


def _xg_message(queued_at: datetime, competition: str = "allsvenskan") -> dict:
    interval = 6 * 3600
    key, window = xg_backfill_claim_key(
        competition_id=competition,
        queued_at=queued_at,
        interval_seconds=interval,
    )
    return {
        "competition_id": competition,
        "queued_at_utc": queued_at.isoformat(),
        "claim_key": key,
        "planned_window_start_utc": window.isoformat(),
        "plan_interval_seconds": interval,
    }


def test_xg_eight_workers_same_window_one_external_entry(fence_pg, monkeypatch):
    calls = []
    lock = threading.Lock()

    class Result:
        def as_dict(self):
            return {"provider_calls": 1, "team_count": 1}

    def external(**kwargs):
        with lock:
            calls.append(kwargs)
        time.sleep(0.15)
        return Result()

    monkeypatch.setattr(worker, "run_xg_history_backfill", external)
    message = _xg_message(datetime.now(UTC) - timedelta(seconds=91))
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: worker.xg_history_backfill.run(**message), range(8)))
    assert len(calls) == 1
    assert sum(result["status"] == "COMPLETED" for result in results) >= 1
    assert all(result["status"] in {"COMPLETED", "BLOCKED"} for result in results)
    assert worker.xg_history_backfill.run(**message)["status"] == "COMPLETED"
    assert len(calls) == 1
    # A later planned window is new work, never a permanent global lock.
    later = _xg_message(datetime.now(UTC) + timedelta(hours=7))
    assert later["claim_key"] != message["claim_key"]
    assert worker.xg_history_backfill.run(**later)["status"] == "COMPLETED"
    assert len(calls) == 2
    with Session(create_engine(fence_pg)) as session:
        rows = list(session.scalars(select(ProviderSideEffectFenceModel)))
        assert len(rows) == 2 and all(row.state == "DONE" for row in rows)


def test_xg_hard_exit_and_terminal_audit_failure_block_reentry(fence_pg, monkeypatch):
    message = _xg_message(datetime.now(UTC) - timedelta(minutes=8))
    calls = []

    def exits(**kwargs):
        calls.append(kwargs)
        raise SystemExit(73)

    monkeypatch.setattr(worker, "run_xg_history_backfill", exits)
    with pytest.raises(SystemExit):
        worker.xg_history_backfill.run(**message)
    time.sleep(1.3)  # Cross the old one-second claim-key boundary.
    retry = worker.xg_history_backfill.run(**message)
    assert retry["status"] == "BLOCKED" and len(calls) == 1
    with Session(create_engine(fence_pg)) as session:
        row = session.get(ProviderSideEffectFenceModel, (message["claim_key"], "xg", 1))
        assert row and row.state == "ATTEMPTING"

    audit_message = _xg_message(datetime.now(UTC) + timedelta(hours=7))
    original = worker._fence_stage

    class Result:
        def as_dict(self):
            return {"provider_calls": 1}

    monkeypatch.setattr(
        worker, "run_xg_history_backfill", lambda **kwargs: calls.append(kwargs) or Result()
    )

    def broken_terminal(key, stage, state, *args, **kwargs):
        if key == audit_message["claim_key"] and state != "ATTEMPTING":
            raise RuntimeError("AUDIT_WRITE_FAILED")
        return original(key, stage, state, *args, **kwargs)

    monkeypatch.setattr(worker, "_fence_stage", broken_terminal)
    failed = worker.xg_history_backfill.run(**audit_message)
    assert failed["status"] == "BLOCKED" and len(calls) == 2
    retry = worker.xg_history_backfill.run(**audit_message)
    assert retry["status"] == "BLOCKED" and len(calls) == 2


def test_no_pg_and_claim_write_error_have_zero_external_calls(fence_pg, monkeypatch):
    message = _xg_message(datetime.now(UTC))
    calls = []
    monkeypatch.setattr(worker, "run_xg_history_backfill", lambda **kwargs: calls.append(kwargs))
    missing_dispatch = worker.future_fixture_refresh.run(competition_id="allsvenskan")
    assert missing_dispatch["status"] == "BLOCKED"
    assert missing_dispatch["result"]["blockers"] == ["FUTURE_REFRESH_DISPATCH_KEY_MISSING"]
    assert missing_dispatch["result"]["provider_calls_known"] == 0 and not calls
    monkeypatch.setenv("W2_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    get_settings.cache_clear()
    blocked = worker.xg_history_backfill.run(**message)
    assert blocked["status"] == "BLOCKED"
    assert blocked["provider_calls_known"] == 0 and not calls
    future = worker.future_fixture_refresh.run(
        competition_id="allsvenskan", task_key="no-pg-future"
    )
    assert future["status"] == "BLOCKED"
    assert future["result"]["provider_calls_known"] == 0 and not calls
    monkeypatch.setenv("W2_DATABASE_URL", fence_pg)
    get_settings.cache_clear()

    def broken_claim(*args, **kwargs):
        raise RuntimeError("CLAIM_WRITE_FAILED")

    monkeypatch.setattr(worker, "_fence_stage", broken_claim)
    blocked = worker.xg_history_backfill.run(**message)
    assert blocked["status"] == "BLOCKED"
    assert blocked["provider_calls_known"] == 0 and not calls
    future = worker.future_fixture_refresh.run(
        competition_id="allsvenskan", task_key="claim-write-future"
    )
    assert future["status"] == "BLOCKED"
    assert future["result"]["provider_calls_known"] == 0 and not calls


def test_xg_done_does_not_make_unfinished_refresh_ready(fence_pg, monkeypatch):
    calls = []

    class Result:
        def as_dict(self):
            return {"provider_calls": 1, "team_count": 1}

    monkeypatch.setenv("W2_XG_AUTO_CAPTURE_ENABLED", "true")
    monkeypatch.setenv("W2_H2H_AUTO_CAPTURE_ENABLED", "false")
    monkeypatch.setattr(
        "w2.ingestion.xg_backfill.run_xg_history_backfill",
        lambda **kwargs: calls.append(kwargs) or Result(),
    )

    def unfinished_refresh(**kwargs):
        raise RuntimeError("REFRESH_POST_XG_FAILURE")

    monkeypatch.setattr(worker, "run_future_refresh_task", unfinished_refresh)
    first = worker.future_fixture_refresh.run(
        competition_id="allsvenskan", task_key="v11-xg-done-refresh-incomplete"
    )
    assert first["status"] == "BLOCKED" and len(calls) == 1, first["result"]["blockers"]
    second = worker.future_fixture_refresh.run(
        competition_id="allsvenskan", task_key="v11-xg-done-refresh-incomplete"
    )
    assert second["status"] == "BLOCKED" and len(calls) == 1
    with Session(create_engine(fence_pg)) as session:
        states = {
            row.stage: row.state
            for row in session.scalars(
                select(ProviderSideEffectFenceModel).where(
                    ProviderSideEffectFenceModel.task_id == "v11-xg-done-refresh-incomplete"
                )
            )
        }
    assert states == {
        "task": "SIDE_EFFECT_UNCERTAIN",
        "xg": "DONE",
        "refresh_forward": "SIDE_EFFECT_UNCERTAIN",
    }


def test_future_task_done_replays_stored_result_without_reentry(fence_pg, monkeypatch):
    calls = []

    class Audit:
        task_id = "v11-future-once"
        key = "v11-future-once"
        status = "COMPLETED"
        result = {"refresh_checkpoints": [], "requests": []}
        finished_at = datetime.now(UTC)

    monkeypatch.setenv("W2_XG_AUTO_CAPTURE_ENABLED", "false")
    monkeypatch.setenv("W2_H2H_AUTO_CAPTURE_ENABLED", "false")
    monkeypatch.setattr(
        worker, "run_future_refresh_task",
        lambda **kwargs: calls.append(kwargs) or Audit(),
    )
    first = worker.future_fixture_refresh.run(
        competition_id="allsvenskan", task_key="v11-future-once"
    )
    assert first["audit_status"] == "COMPLETED", first
    second = worker.future_fixture_refresh.run(
        competition_id="allsvenskan", task_key="v11-future-once"
    )
    assert second == first and len(calls) == 1
    with Session(create_engine(fence_pg)) as session:
        rows = list(session.scalars(select(ProviderSideEffectFenceModel).where(
            ProviderSideEffectFenceModel.task_id == "v11-future-once"
        )))
    assert {row.stage: row.state for row in rows} == {
        "task": "DONE", "refresh_forward": "DONE",
    }
