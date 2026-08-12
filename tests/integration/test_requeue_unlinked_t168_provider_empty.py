from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from scripts.requeue_unlinked_t168_provider_empty import (
    main,
    requeue_unlinked_t168_provider_empty,
)
from sqlalchemy import create_engine, select

from w2.competitions.seed import (
    apply_collection_policy_update,
    seed_competition_runtime_authority,
)
from w2.infrastructure.database import Base
from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayCheckpointPlanModel,
    MatchdayEndpointCaptureModel,
    MatchdayEndpointCapturePlanModel,
)

NOW = datetime(2026, 8, 12, 10, 0, tzinfo=UTC)


def test_apply_requires_expected_count() -> None:
    with pytest.raises(SystemExit, match="--apply requires --expected-count"):
        main(["--apply"])


def test_requeue_is_dry_by_default_and_apply_is_exactly_guarded(tmp_path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'requeue.db'}")
    Base.metadata.create_all(engine)
    seed_competition_runtime_authority(engine, environment="test", now=NOW)
    apply_collection_policy_update(engine, updated_by="requeue-test", now=NOW)
    rows = [
        _plan("eligible"),
        _plan("expired", window_end=NOW - timedelta(hours=1)),
        _plan("future", window_start=NOW + timedelta(hours=1)),
        _plan("wrong-checkpoint", checkpoint="T72_ODDS"),
        _plan("wrong-status", status="FAILED"),
        _plan("second-attempt", attempt_count=2),
        _plan("captured", capture_id="capture-on-plan"),
        _plan("linked"),
        _plan("world-cup", competition_id="world_cup_2026"),
        _plan("test-only", test_only=True),
        _plan("namespaced", namespace="test"),
    ]
    with engine.begin() as connection:
        connection.execute(MatchdayCheckpointPlanModel.__table__.insert(), rows)
        connection.execute(
            MatchdayEndpointCaptureModel.__table__.insert(),
            {
                "capture_id": "linked-capture",
                "fixture_id": "fixture-linked",
                "competition_id": "allsvenskan",
                "checkpoint": "T168_OPEN_ODDS",
                "endpoint": "odds",
                "sanitized_params": {},
                "params_hash": "params-linked",
                "request_task_key": "task-linked",
                "attempt": 1,
                "requested_at": NOW,
                "provider_captured_at": NOW,
                "status_code": 200,
                "elapsed_ms": 1,
                "response_count": 0,
                "quota_values": {},
                "raw_payload_sha256": "a" * 64,
                "provider_event_time": None,
                "capture_status": "PROVIDER_EMPTY",
                "error_code": None,
            },
        )
        connection.execute(
            MatchdayEndpointCapturePlanModel.__table__.insert(),
            {
                "link_hash": "b" * 64,
                "capture_id": "linked-capture",
                "plan_id": "linked",
                "endpoint": "odds",
                "link_status": "LINKED",
                "linked_at": NOW,
            },
        )

    dry_run = requeue_unlinked_t168_provider_empty(engine, now=NOW)
    assert (dry_run.matched, dry_run.eligible, dry_run.updated, dry_run.plan_ids) == (
        3,
        1,
        0,
        ("eligible",),
    )
    assert dry_run.targets == (
        {
            "plan_id": "eligible",
            "fixture_id": "fixture-eligible",
            "competition_id": "allsvenskan",
        },
    )
    with pytest.raises(RuntimeError, match="REQUEUE_EXPECTED_COUNT_MISMATCH"):
        requeue_unlinked_t168_provider_empty(
            engine,
            now=NOW,
            apply=True,
            expected_count=2,
            expected_plan_ids_sha256=dry_run.plan_ids_sha256,
        )
    with pytest.raises(RuntimeError, match="REQUEUE_EXPECTED_PLAN_IDS_MISMATCH"):
        requeue_unlinked_t168_provider_empty(
            engine,
            now=NOW,
            apply=True,
            expected_count=1,
            expected_plan_ids_sha256="0" * 64,
        )

    applied = requeue_unlinked_t168_provider_empty(
        engine,
        now=NOW,
        apply=True,
        expected_count=1,
        expected_plan_ids_sha256=dry_run.plan_ids_sha256,
    )
    assert applied.updated == 1
    with engine.connect() as connection:
        rows = list(connection.execute(select(MatchdayCheckpointPlanModel)))
    eligible = next(row for row in rows if row.plan_id == "eligible")
    assert (eligible.status, eligible.claimed_by, eligible.attempt_count) == ("DUE", None, 1)
    assert sum(row.status == "DUE" for row in rows) == 1


def _plan(
    plan_id: str,
    window_start: datetime = NOW - timedelta(hours=1),
    window_end: datetime = NOW + timedelta(hours=1),
    *,
    checkpoint: str = "T168_OPEN_ODDS",
    status: str = "PROVIDER_EMPTY",
    attempt_count: int = 1,
    capture_id: str | None = None,
    competition_id: str = "allsvenskan",
    test_only: bool = False,
    namespace: str | None = None,
) -> dict[str, object]:
    return {
        "plan_id": plan_id,
        "fixture_id": f"fixture-{plan_id}",
        "competition_id": competition_id,
        "season": "2026",
        "policy_version": "test-policy",
        "checkpoint": checkpoint,
        "kickoff_utc": window_end + timedelta(days=1),
        "scheduled_at": window_start,
        "window_start": window_start,
        "window_end": window_end,
        "endpoints": ["odds"],
        "status": status,
        "claimed_at": window_start,
        "claimed_by": "old-worker",
        "claim_token": "old-token",
        "claim_expires_at": window_end,
        "attempt_count": attempt_count,
        "test_only": test_only,
        "namespace": namespace,
        "missed_at": None,
        "capture_id": capture_id,
        "current_unscheduled_capture_id": None,
        "blockers": ["ORIGINAL_PROVIDER_EMPTY_AUDIT"],
        "plan_hash": f"hash-{plan_id}",
    }
