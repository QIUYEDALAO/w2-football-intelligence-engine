from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from w2.config import get_settings
from w2.infrastructure.database import Base
from w2.infrastructure.persistence.stage7i_lifecycle_models import (
    Stage7ILifecycleEventModel,
    Stage7ILifecycleHeartbeatModel,
    Stage7ILifecycleRunModel,
)
from w2.monitoring.stage7i_supervision import (
    Stage7ILifecycleRepository,
    Stage7ILifecycleSupervisor,
)

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 6, 23, 10, 0, tzinfo=UTC)
KICKOFF = datetime(2026, 6, 23, 17, 0, tzinfo=UTC)


def configure_db(tmp_path: Path, monkeypatch: object) -> str:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'stage7i-supervision.db'}"
    monkeypatch.setenv("W2_ENVIRONMENT", "test")
    monkeypatch.setenv("W2_DATABASE_URL", database_url)
    get_settings.cache_clear()
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    return database_url


def supervisor() -> Stage7ILifecycleSupervisor:
    return Stage7ILifecycleSupervisor(
        repository=Stage7ILifecycleRepository(),
        heartbeat_timeout_seconds=60,
    )


def start(supervisor: Stage7ILifecycleSupervisor, run_id: str = "stage7i-test") -> None:
    supervisor.start_run(
        run_id=run_id,
        fixture_id="1489404",
        scheduled_kickoff_utc=KICKOFF,
        started_at=NOW,
        observer_pid=101,
        collector_pid=202,
    )


def complete_chain(supervisor: Stage7ILifecycleSupervisor, run_id: str = "stage7i-test") -> None:
    supervisor.record_closing_observation(
        run_id=run_id,
        captured_at=KICKOFF - timedelta(minutes=3),
    )
    supervisor.record_actual_kickoff(
        run_id=run_id,
        actual_kickoff_utc=KICKOFF,
        source="fixture.periods.first",
        observed_at=KICKOFF + timedelta(minutes=1),
    )
    supervisor.record_result(
        run_id=run_id,
        status="FT",
        observed_at=KICKOFF + timedelta(hours=2),
    )
    supervisor.record_settlement_evaluation(
        run_id=run_id,
        settlement_status="COMPLETED",
        evaluation_status="COMPLETED",
        observed_at=KICKOFF + timedelta(hours=3),
    )


def test_watchdog_marks_collector_timeout_failed_and_blocks_completion(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    configure_db(tmp_path, monkeypatch)
    svc = supervisor()
    start(svc)

    ok = svc.watchdog_check(
        run_id="stage7i-test",
        observed_at=NOW + timedelta(minutes=2),
    )

    assert ok is False
    run = svc.repository.run("stage7i-test")
    assert run["status"] == "FAILED"
    assert run["failure_reason"] == "COLLECTOR_HEARTBEAT_TIMEOUT"
    events = svc.repository.events("stage7i-test")
    assert any(event["event_type"] == "WATCHDOG_FAILURE" for event in events)
    audit = svc.final_audit(
        run_id="stage7i-test",
        observed_at=NOW + timedelta(minutes=3),
    )
    assert audit.status == "FAIL"
    assert "COLLECTOR_HEARTBEAT_TIMEOUT" in audit.blockers


def test_final_checker_fails_when_collector_is_inactive(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    database_url = configure_db(tmp_path, monkeypatch)
    svc = supervisor()
    start(svc)
    svc.heartbeat(
        run_id="stage7i-test",
        component="collector",
        observed_at=NOW + timedelta(seconds=10),
        pid=202,
        status="EXITED",
    )
    complete_chain(svc)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/check_w2_stage7i.py",
            "--mode",
            "final",
            "--db-run-id",
            "stage7i-test",
            "--observed-at-utc",
            (KICKOFF + timedelta(hours=3, minutes=1)).isoformat().replace("+00:00", "Z"),
        ],
        cwd=ROOT,
        env={
            **os.environ,
            "PYTHONPATH": ".:src",
            "W2_ENVIRONMENT": "test",
            "W2_DATABASE_URL": database_url,
        },
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "COLLECTOR_NOT_ACTIVE" in result.stderr


def test_happy_path_final_checker_completes_with_db_lifecycle_chain(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    database_url = configure_db(tmp_path, monkeypatch)
    svc = supervisor()
    start(svc)
    svc.heartbeat(
        run_id="stage7i-test",
        component="collector",
        observed_at=KICKOFF + timedelta(hours=3, minutes=1),
        pid=202,
    )
    complete_chain(svc)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/check_w2_stage7i.py",
            "--mode",
            "final",
            "--db-run-id",
            "stage7i-test",
            "--expected-fixture-id",
            "1489404",
            "--observed-at-utc",
            (KICKOFF + timedelta(hours=3, minutes=1)).isoformat().replace("+00:00", "Z"),
        ],
        cwd=ROOT,
        env={
            **os.environ,
            "PYTHONPATH": ".:src",
            "W2_ENVIRONMENT": "test",
            "W2_DATABASE_URL": database_url,
        },
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "W2 Stage7I check PASS" in result.stdout
    run = svc.repository.run("stage7i-test")
    assert run["status"] == "COMPLETED"
    assert run["final_audit_status"] == "PASS"
    assert run["candidate"] is False
    assert run["formal_recommendation"] is False


def test_lifecycle_state_is_db_backed_and_does_not_write_read_only_runtime(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    configure_db(tmp_path, monkeypatch)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    runtime.chmod(0o500)
    svc = supervisor()

    try:
        start(svc)
        svc.heartbeat(
            run_id="stage7i-test",
            component="collector",
            observed_at=KICKOFF + timedelta(hours=3, minutes=1),
            pid=202,
        )
        complete_chain(svc)
        audit = svc.final_audit(
            run_id="stage7i-test",
            observed_at=KICKOFF + timedelta(hours=3, minutes=1),
        )
    finally:
        runtime.chmod(0o700)

    assert audit.status == "COMPLETED"
    assert not any(runtime.iterdir())
    engine = create_engine(get_settings().database_url.get_secret_value())
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Stage7ILifecycleRunModel)) == 1
        assert session.scalar(select(func.count()).select_from(Stage7ILifecycleHeartbeatModel)) == 2
        assert session.scalar(select(func.count()).select_from(Stage7ILifecycleEventModel)) >= 5
