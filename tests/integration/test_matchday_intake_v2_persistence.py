from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from w2.infrastructure.database import Base
from w2.infrastructure.persistence.dynamic_prematch_models import (
    DynamicPrematchEvaluationModel,
    DynamicPrematchOpportunityModel,
)
from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayCheckpointPlanModel,
    MatchdayCheckpointPlanRescheduleModel,
    MatchdayEndpointCaptureModel,
    MatchdayEndpointCapturePlanModel,
    MatchdayEvidenceManifestModel,
    MatchdayFixtureIdentityModel,
)
from w2.infrastructure.persistence.model_forecast_models import ModelForecastCaptureModel
from w2.ingestion.future_refresh_repository import FutureRefreshDbRepository
from w2.matchday.intake_v2 import (
    CheckpointPlan,
    build_checkpoint_plans,
    competition_policies,
    endpoint_capture_contract,
    freshness_status,
    load_matchday_policy,
    materialize_evidence_manifest,
    normalize_matchday_odds_payload,
    public_manifest_read,
    stable_hash,
)
from w2.matchday.repository import (
    MatchdayRepositoryError,
    MatchdayRuntimeRepository,
    normalize_repo_time,
)

NOW = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
KICKOFF = datetime(2026, 7, 20, 18, 0, tzinfo=UTC)


def test_matchday_intake_v2_isolated_persistence_smoke() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    policy = competition_policies(load_matchday_policy())["allsvenskan"]
    fixture = {
        "fixture_id": "api_football:100",
        "competition_id": "allsvenskan",
        "season": "2026",
        "kickoff_utc": KICKOFF.isoformat(),
        "fixture_status": "NS",
        "team_identity_status": "READY",
    }
    plans = build_checkpoint_plans(
        fixture_id="api_football:100",
        competition_id="allsvenskan",
        season="2026",
        kickoff_utc=KICKOFF,
        now=KICKOFF - timedelta(minutes=50),
        policy=policy,
    )
    capture = endpoint_capture_contract(
        endpoint="odds",
        params={"fixture": "100"},
        requested_at=NOW,
        provider_captured_at=NOW,
        status_code=200,
        elapsed_ms=10,
        payload=_odds_payload(),
    )
    rows, _rejected = normalize_matchday_odds_payload(
        _odds_payload(),
        captured_at=NOW,
        ingested_at=NOW,
        raw_payload_sha256=capture["raw_payload_sha256"],
        source_revision="unit",
        capture_id=str(capture["capture_id"]),
        competition_id="allsvenskan",
    )
    audit = _manifest_market_audit_fixture(rows, evaluated_at=NOW)
    manifest = materialize_evidence_manifest(
        fixture_identity=fixture,
        competition_policy=policy,
        generated_at=NOW,
        checkpoint_plans=plans,
        endpoint_captures=[capture],
        market_audit=audit,
        enrichments={},
        model_evidence={"status": "COMPLETE", "comparison": {"analysis_direction_allowed": False}},
    )

    with Session(engine) as session:
        session.add(
            MatchdayEndpointCaptureModel(
                capture_id=str(capture["capture_id"]),
                endpoint=str(capture["endpoint"]),
                sanitized_params=dict(capture["sanitized_params"]),
                params_hash=str(capture["params_hash"]),
                request_task_key=str(capture["request_task_key"]),
                requested_at=NOW,
                provider_captured_at=NOW,
                status_code=int(capture["status_code"]),
                elapsed_ms=int(capture["elapsed_ms"]),
                response_count=int(capture["response_count"]),
                quota_values=dict(capture["quota_values"]),
                raw_payload_sha256=str(capture["raw_payload_sha256"]),
                provider_event_time=None,
                capture_status=str(capture["capture_status"]),
                error_code=None,
            )
        )
        first_plan = plans[0]
        session.add(
            MatchdayCheckpointPlanModel(
                plan_id=stable_hash(first_plan.natural_identity),
                fixture_id=first_plan.fixture_id,
                competition_id=first_plan.competition_id,
                season=first_plan.season,
                policy_version=first_plan.policy_version,
                checkpoint=first_plan.checkpoint,
                kickoff_utc=first_plan.kickoff_utc,
                scheduled_at=first_plan.scheduled_at,
                window_start=first_plan.window_start,
                window_end=first_plan.window_end,
                endpoints=list(first_plan.endpoints),
                status=first_plan.status,
                missed_at=first_plan.missed_at,
                capture_id=None,
                current_unscheduled_capture_id=None,
                blockers=list(first_plan.blockers),
                plan_hash=first_plan.plan_hash,
            )
        )
        session.add(
            MatchdayEvidenceManifestModel(
                manifest_id=str(manifest["manifest_hash"]),
                fixture_id=str(fixture["fixture_id"]),
                competition_id="allsvenskan",
                as_of=NOW,
                outcome=str(manifest["decision"]["outcome"]),
                reason_code=str(manifest["decision"]["reason"]),
                manifest_hash=str(manifest["manifest_hash"]),
                input_manifest_hash=str(manifest["input_manifest_hash"]),
                payload=manifest,
            )
        )
        session.commit()
    with Session(engine) as session:
        assert session.query(MatchdayEndpointCaptureModel).count() == 1
        assert session.query(MatchdayCheckpointPlanModel).count() == 1
        assert session.query(MatchdayEvidenceManifestModel).count() == 1
        session.add(
            MatchdayCheckpointPlanModel(
                plan_id="conflict",
                fixture_id=first_plan.fixture_id,
                competition_id=first_plan.competition_id,
                season=first_plan.season,
                policy_version=first_plan.policy_version,
                checkpoint=first_plan.checkpoint,
                kickoff_utc=first_plan.kickoff_utc,
                scheduled_at=first_plan.scheduled_at + timedelta(minutes=1),
                window_start=first_plan.window_start,
                window_end=first_plan.window_end,
                endpoints=list(first_plan.endpoints),
                status="CONFLICT",
                missed_at=None,
                capture_id=None,
                current_unscheduled_capture_id=None,
                blockers=["PLAN_CONFLICT"],
                plan_hash="x" * 64,
            )
        )
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
        else:
            raise AssertionError("plan conflict must fail closed")

    public = public_manifest_read(manifest)
    assert public["provider_calls"] == 0
    assert public["db_writes"] == 0


def test_latest_endpoint_capture_reuses_persisted_raw_payload_after_restart() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = MatchdayRuntimeRepository(engine=engine)
    payload = _odds_payload()
    capture = endpoint_capture_contract(
        endpoint="odds",
        params={"fixture": "100"},
        requested_at=NOW,
        provider_captured_at=NOW,
        status_code=200,
        elapsed_ms=10,
        payload=payload,
        fixture_id="api_football:100",
        competition_id="allsvenskan",
    )
    repository.save_raw_payload(
        sha256=str(capture["raw_payload_sha256"]),
        endpoint="odds",
        captured_at=NOW,
        payload=payload,
    )
    repository.insert_endpoint_capture(capture)

    cached = MatchdayRuntimeRepository(engine=engine).latest_endpoint_capture(
        request_task_key=str(capture["request_task_key"]),
        since=NOW - timedelta(minutes=1),
    )

    assert cached is not None
    assert cached["capture"]["capture_id"] == capture["capture_id"]
    assert cached["payload"] == payload


def test_checkpoint_state_machine_due_claim_capture_and_single_winner() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = MatchdayRuntimeRepository(engine=engine)
    policy = competition_policies(load_matchday_policy())["allsvenskan"]
    plan = next(
        item
        for item in build_checkpoint_plans(
            fixture_id="api_football:claim",
            competition_id="allsvenskan",
            season="2026",
            kickoff_utc=KICKOFF,
            now=KICKOFF - timedelta(hours=25),
            policy=policy,
        )
        if item.checkpoint == "T24_ODDS"
    )

    repository.upsert_checkpoint_plan(plan)
    due = repository.due_checkpoint_plans(now=plan.window_start + timedelta(minutes=1))
    first_claim = repository.claim_due_checkpoint_plans(
        now=plan.window_start + timedelta(minutes=1),
        worker_id="worker-a",
        limit=10,
    )
    second_claim = repository.claim_due_checkpoint_plans(
        now=plan.window_start + timedelta(minutes=1),
        worker_id="worker-b",
        limit=10,
    )
    repository.transition_checkpoint(
        fixture_id=plan.fixture_id,
        competition_id=plan.competition_id,
        season=plan.season,
        checkpoint=plan.checkpoint,
        policy_version=plan.policy_version,
        status="CAPTURED",
        capture_id="capture-1",
        now=plan.window_start + timedelta(minutes=2),
        claim_token=str(first_claim[0]["claim_token"]),
    )

    assert [item["checkpoint"] for item in due] == ["T24_ODDS"]
    assert first_claim[0]["claimed_by"] == "worker-a"
    assert first_claim[0]["claim_token"]
    assert first_claim[0]["claim_expires_at"]
    assert first_claim[0]["attempt_count"] == 1
    assert second_claim == []
    with Session(engine) as session:
        row = session.get(MatchdayCheckpointPlanModel, first_claim[0]["id"])
        assert row is not None
        assert row.status == "CAPTURED"
        assert row.capture_id == "capture-1"
        assert row.claim_token is None


def test_prematch_collection_is_claimed_before_ordinary_postmatch_result() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = MatchdayRuntimeRepository(engine=engine)
    shared = {
        "competition_id": "allsvenskan",
        "season": "2026",
        "kickoff_utc": NOW,
        "window_start": NOW - timedelta(hours=1),
        "window_end": NOW + timedelta(hours=1),
        "status": "DUE",
        "blockers": (),
    }
    repository.upsert_checkpoint_plan(
        CheckpointPlan(
            **shared,
            fixture_id="api_football:prematch",
            checkpoint="T60_ODDS_LINEUPS",
            scheduled_at=NOW - timedelta(minutes=30),
            endpoints=("odds", "lineups"),
        )
    )
    repository.upsert_checkpoint_plan(
        CheckpointPlan(
            **shared,
            fixture_id="api_football:result",
            checkpoint="POSTMATCH_RESULT",
            scheduled_at=NOW,
            endpoints=("status", "fixtures"),
        )
    )

    claimed = repository.claim_due_checkpoint_plans(now=NOW, worker_id="priority-test")

    assert [row["checkpoint"] for row in claimed] == [
        "T60_ODDS_LINEUPS",
        "POSTMATCH_RESULT",
    ]


def test_unsettled_model_forecast_postmatch_is_claimed_before_other_results() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = MatchdayRuntimeRepository(engine=engine)
    shared = {
        "competition_id": "allsvenskan",
        "season": "2026",
        "kickoff_utc": NOW - timedelta(hours=4),
        "window_start": NOW - timedelta(hours=1),
        "window_end": NOW + timedelta(hours=1),
        "status": "DUE",
        "blockers": (),
        "checkpoint": "POSTMATCH_RESULT",
        "endpoints": ("status", "fixtures"),
    }
    repository.upsert_checkpoint_plan(
        CheckpointPlan(
            **shared,
            fixture_id="api_football:ordinary",
            scheduled_at=NOW - timedelta(minutes=30),
        )
    )
    repository.upsert_checkpoint_plan(
        CheckpointPlan(
            **shared,
            fixture_id="api_football:capture",
            scheduled_at=NOW,
        )
    )
    with Session(engine) as session:
        session.add(
            ModelForecastCaptureModel(
                capture_identity_hash="1" * 64,
                fixture_id="capture",
                competition_id="allsvenskan",
                kickoff_utc=NOW - timedelta(hours=4),
                captured_at=NOW - timedelta(days=1),
                lead_time_seconds=72000,
                lead_time_bucket="H6_TO_LT_24H",
                model_family="EXACT_DC_POISSON",
                model_version="model-v1",
                model_input_manifest_hash="2" * 64,
                four_field_xg_identity_hash="3" * 64,
                score_matrix_hash="4" * 64,
                payload={"fixture_id": "capture"},
                payload_sha256="5" * 64,
                inserted_at=NOW - timedelta(days=1),
            )
        )
        session.commit()

    quota_repository = FutureRefreshDbRepository(engine=engine)
    assert quota_repository.unsettled_model_forecast_postmatch_count(
        window_start=NOW.replace(hour=0, minute=0, second=0, microsecond=0),
        window_end=NOW.replace(hour=0, minute=0, second=0, microsecond=0)
        + timedelta(days=1),
    ) == 1
    assert quota_repository.unsettled_model_forecast_postmatch_count(
        window_start=NOW.replace(hour=0, minute=0, second=0, microsecond=0),
        window_end=NOW.replace(hour=0, minute=0, second=0, microsecond=0)
        + timedelta(days=1),
        exclude_fixture_ids=("api_football:capture",),
    ) == 0
    assert repository.due_checkpoint_plans(now=NOW, limit=1)[0]["fixture_id"] == (
        "api_football:capture"
    )
    assert repository.claim_due_checkpoint_plans(
        now=NOW,
        worker_id="capture-priority-test",
        limit=1,
    )[0]["fixture_id"] == "api_football:capture"


def test_checkpoint_claim_release_restores_only_an_exact_unattempted_claim() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = MatchdayRuntimeRepository(engine=engine)
    policy = competition_policies(load_matchday_policy())["allsvenskan"]
    plan = next(
        item
        for item in build_checkpoint_plans(
            fixture_id="api_football:release",
            competition_id="allsvenskan",
            season="2026",
            kickoff_utc=KICKOFF,
            now=KICKOFF - timedelta(hours=25),
            policy=policy,
        )
        if item.checkpoint == "T24_ODDS"
    )
    repository.upsert_checkpoint_plan(plan)
    now = plan.window_start + timedelta(minutes=1)

    first = repository.claim_due_checkpoint_plans(now=now, worker_id="worker-a")[0]
    assert not repository.release_checkpoint_claim(
        plan_id=first["id"],
        claim_token=f"wrong:{first['claim_token']}",
        reason="NOT_ATTEMPTED",
        restore_attempt=True,
    )
    assert repository.release_checkpoint_claim(
        plan_id=first["id"],
        claim_token=first["claim_token"],
        reason="NOT_ATTEMPTED",
        restore_attempt=True,
    )
    assert not repository.release_checkpoint_claim(
        plan_id=first["id"],
        claim_token=first["claim_token"],
        reason="DUPLICATE_RELEASE",
        restore_attempt=True,
    )
    second = repository.claim_due_checkpoint_plans(now=now, worker_id="worker-b")[0]
    assert second["attempt_count"] == 1
    assert repository.release_checkpoint_claim(
        plan_id=second["id"],
        claim_token=second["claim_token"],
        reason="ENQUEUE_AMBIGUOUS",
    )
    with Session(engine) as session:
        row = session.get(MatchdayCheckpointPlanModel, second["id"])
        assert row is not None
        assert row.attempt_count == 1
        assert row.claim_token is None


def test_checkpoint_claim_expiry_releases_due_plan_inside_window() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = MatchdayRuntimeRepository(engine=engine)
    policy = competition_policies(load_matchday_policy())["allsvenskan"]
    plan = next(
        item
        for item in build_checkpoint_plans(
            fixture_id="api_football:lease",
            competition_id="allsvenskan",
            season="2026",
            kickoff_utc=KICKOFF,
            now=KICKOFF - timedelta(hours=25),
            policy=policy,
        )
        if item.checkpoint == "T24_ODDS"
    )

    repository.upsert_checkpoint_plan(plan)
    first_claim = repository.claim_due_checkpoint_plans(
        now=plan.window_start + timedelta(minutes=1),
        worker_id="worker-a",
        limit=1,
        lease_seconds=1,
    )
    second_claim = repository.claim_due_checkpoint_plans(
        now=plan.window_start + timedelta(minutes=2),
        worker_id="worker-b",
        limit=1,
    )

    assert first_claim[0]["claim_token"] != second_claim[0]["claim_token"]
    assert second_claim[0]["claimed_by"] == "worker-b"
    assert second_claim[0]["attempt_count"] == 2


def test_active_checkpoint_claim_can_finish_after_its_window_closes() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = MatchdayRuntimeRepository(engine=engine)
    policy = competition_policies(load_matchday_policy())["allsvenskan"]
    plan = next(
        item
        for item in build_checkpoint_plans(
            fixture_id="api_football:active-after-window",
            competition_id="allsvenskan",
            season="2026",
            kickoff_utc=KICKOFF,
            now=KICKOFF - timedelta(hours=25),
            policy=policy,
        )
        if item.checkpoint == "T24_ODDS"
    )

    repository.upsert_checkpoint_plan(plan)
    claim = repository.claim_due_checkpoint_plans(
        now=plan.window_end - timedelta(seconds=1),
        worker_id="worker-a",
        limit=1,
        lease_seconds=60,
    )[0]

    assert repository.due_checkpoint_plans(
        now=plan.window_end + timedelta(seconds=1)
    ) == []
    capture = endpoint_capture_contract(
        endpoint="odds",
        params={"fixture": "active-after-window"},
        requested_at=plan.window_end - timedelta(seconds=1),
        provider_captured_at=plan.window_end + timedelta(seconds=1),
        status_code=200,
        elapsed_ms=2_000,
        payload=_odds_payload(),
        fixture_id=plan.fixture_id,
        competition_id=plan.competition_id,
        checkpoint=plan.checkpoint,
        checkpoint_plan_ids=[str(claim["id"])],
    )
    repository.insert_endpoint_capture(capture)
    repository.link_endpoint_capture_plans(
        capture_id=str(capture["capture_id"]),
        plan_ids=[str(claim["id"])],
        endpoint="odds",
        linked_at=plan.window_end + timedelta(seconds=1),
    )
    repository.transition_checkpoint(
        fixture_id=plan.fixture_id,
        competition_id=plan.competition_id,
        season=plan.season,
        checkpoint=plan.checkpoint,
        policy_version=plan.policy_version,
        status="CAPTURED",
        capture_id=str(capture["capture_id"]),
        now=plan.window_end + timedelta(seconds=2),
        claim_token=str(claim["claim_token"]),
    )

    with Session(engine) as session:
        row = session.get(MatchdayCheckpointPlanModel, str(claim["id"]))
        assert row is not None
        assert row.status == "CAPTURED"
        assert row.capture_id == capture["capture_id"]
        assert row.claim_token is None


def test_endpoint_capture_can_link_multiple_checkpoint_plans_explicitly() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = MatchdayRuntimeRepository(engine=engine)
    base = {
        "fixture_id": "api_football:100",
        "competition_id": "allsvenskan",
        "season": "2026",
        "policy_version": "unit-policy",
        "kickoff_utc": KICKOFF.isoformat(),
        "scheduled_at": NOW.isoformat(),
        "window_start": (NOW - timedelta(minutes=5)).isoformat(),
        "window_end": (NOW + timedelta(minutes=5)).isoformat(),
        "endpoints": ["odds"],
        "status": "DUE",
        "blockers": [],
    }
    plan_ids = []
    for checkpoint in ("T30_LINEUPS_RETRY", "T-30m_VALIDATION_LOCK"):
        payload = {**base, "checkpoint": checkpoint}
        payload["plan_hash"] = stable_hash(payload)
        plan_ids.append(repository.upsert_checkpoint_plan(payload))
    capture = endpoint_capture_contract(
        endpoint="odds",
        params={"fixture": "100"},
        requested_at=NOW,
        provider_captured_at=NOW,
        status_code=200,
        elapsed_ms=10,
        payload=_odds_payload(),
        fixture_id="api_football:100",
        competition_id="allsvenskan",
        checkpoint="T-30m_VALIDATION_LOCK,T30_LINEUPS_RETRY",
        checkpoint_plan_ids=plan_ids,
    )
    repository.insert_endpoint_capture(capture)
    links = repository.link_endpoint_capture_plans(
        capture_id=str(capture["capture_id"]),
        plan_ids=plan_ids,
        endpoint="odds",
        linked_at=NOW,
    )

    assert len(links) == 2
    with Session(engine) as session:
        assert session.query(MatchdayEndpointCapturePlanModel).count() == 2


def test_checkpoint_missed_is_immutable_and_planned_due_becomes_missed() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = MatchdayRuntimeRepository(engine=engine)
    policy = competition_policies(load_matchday_policy())["allsvenskan"]
    plan = next(
        item
        for item in build_checkpoint_plans(
            fixture_id="api_football:missed",
            competition_id="allsvenskan",
            season="2026",
            kickoff_utc=KICKOFF,
            now=KICKOFF - timedelta(hours=25),
            policy=policy,
        )
        if item.checkpoint == "T24_ODDS"
    )

    repository.upsert_checkpoint_plan(plan)
    due_after_window = repository.due_checkpoint_plans(now=plan.window_end + timedelta(seconds=1))

    assert due_after_window == []
    with Session(engine) as session:
        row = session.get(MatchdayCheckpointPlanModel, stable_hash(plan.natural_identity))
        assert row is not None
        assert row.status == "MISSED"
        assert "CHECKPOINT_MISSING" in row.blockers
    try:
        repository.transition_checkpoint(
            fixture_id=plan.fixture_id,
            competition_id=plan.competition_id,
            season=plan.season,
            checkpoint=plan.checkpoint,
            policy_version=plan.policy_version,
            status="CAPTURED",
            capture_id="capture-late",
        )
    except MatchdayRepositoryError as exc:
        assert str(exc) in {
            "MISSED_CHECKPOINT_IMMUTABLE",
            "CHECKPOINT_STATUS_TRANSITION_INVALID:MISSED->CAPTURED",
        }
    else:
        raise AssertionError("MISSED -> CAPTURED must fail closed")


def test_registered_missed_checkpoint_writes_two_opportunities_without_attempts() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = MatchdayRuntimeRepository(engine=engine)
    fixture_id = "api_football:missed-opportunity"
    policy = competition_policies(load_matchday_policy())["allsvenskan"]
    plan = next(
        item
        for item in build_checkpoint_plans(
            fixture_id=fixture_id,
            competition_id="allsvenskan",
            season="2026",
            kickoff_utc=KICKOFF,
            now=KICKOFF - timedelta(hours=2),
            policy=policy,
        )
        if item.checkpoint == "T60_ODDS_LINEUPS"
    )
    with Session(engine) as session:
        session.add(
            ModelForecastCaptureModel(
                capture_identity_hash="1" * 64,
                fixture_id="missed-opportunity",
                competition_id="allsvenskan",
                kickoff_utc=KICKOFF,
                captured_at=KICKOFF - timedelta(days=1),
                lead_time_seconds=86400,
                lead_time_bucket="D1_TO_D3",
                model_family="EXACT_DC_POISSON",
                model_version="model-v1",
                model_input_manifest_hash="2" * 64,
                four_field_xg_identity_hash="3" * 64,
                score_matrix_hash="4" * 64,
                payload={"fixture_id": "missed-opportunity"},
                payload_sha256="5" * 64,
                inserted_at=KICKOFF - timedelta(days=1),
            )
        )
        session.commit()

    repository.upsert_checkpoint_plan(plan)
    assert repository.due_checkpoint_plans(now=plan.window_end + timedelta(seconds=1)) == []

    with Session(engine) as session:
        opportunities = list(session.scalars(select(DynamicPrematchOpportunityModel)))
        attempts = list(session.scalars(select(DynamicPrematchEvaluationModel)))
    assert {row.market for row in opportunities} == {"ASIAN_HANDICAP", "TOTALS"}
    assert {row.state for row in opportunities} == {"MISSED_CHECKPOINT"}
    assert all(row.evaluated_at is None for row in opportunities)
    assert all(row.latest_attempt_identity_hash is None for row in opportunities)
    assert all(row.payload["blocker"] == "CHECKPOINT_WINDOW_MISSED" for row in opportunities)
    assert attempts == []


def test_terminal_checkpoint_is_not_rewritten_by_rescheduled_missed_plan() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = MatchdayRuntimeRepository(engine=engine)
    policy = competition_policies(load_matchday_policy())["allsvenskan"]
    # MISSED is deliberately absent: it records no provider interaction, so a
    # moved kickoff re-dates it (see
    # test_postponed_fixture_reschedules_its_checkpoint_plans).  FAILED is
    # absent too, but for a different reason -- it is decided per row on
    # whether provider evidence exists, covered by the two tests below.
    for terminal_status in ("CAPTURED",):
        plan = next(
            item
            for item in build_checkpoint_plans(
                fixture_id=f"api_football:{terminal_status.lower()}",
                competition_id="allsvenskan",
                season="2026",
                kickoff_utc=KICKOFF,
                now=KICKOFF - timedelta(hours=25),
                policy=policy,
            )
            if item.checkpoint == "T24_ODDS"
        )
        plan_id = repository.upsert_checkpoint_plan(plan)
        repository.transition_checkpoint(
            fixture_id=plan.fixture_id,
            competition_id=plan.competition_id,
            season=plan.season,
            checkpoint=plan.checkpoint,
            policy_version=plan.policy_version,
            status="DUE",
        )
        repository.transition_checkpoint(
            fixture_id=plan.fixture_id,
            competition_id=plan.competition_id,
            season=plan.season,
            checkpoint=plan.checkpoint,
            policy_version=plan.policy_version,
            status=terminal_status,
            capture_id="capture-terminal" if terminal_status == "CAPTURED" else None,
        )
        with Session(engine) as session:
            row = session.get(MatchdayCheckpointPlanModel, plan_id)
            assert row is not None
            row.blockers = [f"{terminal_status}_EVIDENCE"]
            session.commit()
            terminal_missed_at = row.missed_at

        missed = next(
            item
            for item in build_checkpoint_plans(
                fixture_id=plan.fixture_id,
                competition_id=plan.competition_id,
                season=plan.season,
                kickoff_utc=KICKOFF + timedelta(days=1),
                now=KICKOFF + timedelta(days=2),
                policy=policy,
            )
            if item.checkpoint == plan.checkpoint
        )
        assert missed.status == "MISSED"
        repository.upsert_checkpoint_plan(missed)

        with Session(engine) as session:
            row = session.get(MatchdayCheckpointPlanModel, plan_id)
            assert row is not None
            assert row.status == terminal_status
            assert row.blockers == [f"{terminal_status}_EVIDENCE"]
            assert row.missed_at == terminal_missed_at
            assert normalize_repo_time(row.kickoff_utc) == KICKOFF
            assert normalize_repo_time(row.scheduled_at) == plan.scheduled_at


def test_observation_conflict_and_manifest_identity_fail_closed() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = MatchdayRuntimeRepository(engine=engine)
    capture = endpoint_capture_contract(
        endpoint="odds",
        params={"fixture": "100"},
        requested_at=NOW,
        provider_captured_at=NOW + timedelta(seconds=2),
        status_code=200,
        elapsed_ms=10,
        payload=_odds_payload(),
        fixture_id="api_football:100",
        competition_id="allsvenskan",
        checkpoint="T6_ODDS",
        attempt=1,
    )
    repository.insert_endpoint_capture(capture)
    rows, rejected = normalize_matchday_odds_payload(
        _odds_payload(),
        captured_at=NOW + timedelta(seconds=2),
        ingested_at=NOW + timedelta(seconds=3),
        raw_payload_sha256=str(capture["raw_payload_sha256"]),
        source_revision="unit",
        capture_id=str(capture["capture_id"]),
        competition_id="allsvenskan",
    )
    assert rejected == []
    assert repository.insert_market_observations(rows[:1]) == 1
    conflict = {**rows[0], "decimal_odds": "9.99"}
    try:
        repository.insert_market_observations([conflict])
    except MatchdayRepositoryError as exc:
        assert str(exc) == "OBSERVATION_IDENTITY_CONFLICT"
    else:
        raise AssertionError("observation identity conflict must fail closed")

    manifest = materialize_evidence_manifest(
        fixture_identity={
            "fixture_id": "api_football:100",
            "competition_id": "allsvenskan",
            "season": "2026",
            "kickoff_utc": KICKOFF.isoformat(),
            "fixture_status": "NS",
            "team_identity_status": "READY",
        },
        competition_policy=competition_policies(load_matchday_policy())["allsvenskan"],
        generated_at=NOW,
        checkpoint_plans=[],
        endpoint_captures=[capture],
        market_audit=_manifest_market_audit_fixture(rows, evaluated_at=NOW),
        enrichments={},
        model_evidence={"status": "NOT_READY"},
    )
    broken = {**manifest, "manifest_hash": "0" * 64}
    try:
        repository.insert_manifest(broken)
    except ValueError as exc:
        assert str(exc) == "MANIFEST_IDENTITY_CONFLICT"
    else:
        raise AssertionError("repository must validate manifest identity before insert")


def test_observation_replay_is_idempotent_across_release_revision() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = MatchdayRuntimeRepository(engine=engine)
    capture = endpoint_capture_contract(
        endpoint="odds",
        params={"fixture": "100"},
        requested_at=NOW,
        provider_captured_at=NOW + timedelta(seconds=2),
        status_code=200,
        elapsed_ms=10,
        payload=_odds_payload(),
        fixture_id="api_football:100",
        competition_id="allsvenskan",
        checkpoint="T6_ODDS",
        attempt=1,
    )
    rows, rejected = normalize_matchday_odds_payload(
        _odds_payload(),
        captured_at=NOW + timedelta(seconds=2),
        ingested_at=NOW + timedelta(seconds=3),
        raw_payload_sha256=str(capture["raw_payload_sha256"]),
        source_revision="release-one",
        capture_id=str(capture["capture_id"]),
        competition_id="allsvenskan",
    )
    assert rejected == []
    assert repository.insert_market_observations(rows[:1]) == 1

    replay = {**rows[0], "source_revision": "release-two", "ingested_at": NOW.isoformat()}
    assert repository.insert_market_observations([replay]) == 0

    for field, changed in (
        ("decimal_odds", "9.99"),
        ("line", "9.75"),
        ("capture_id", "new-capture"),
    ):
        conflict = {**replay, field: changed}
        try:
            repository.insert_market_observations([conflict])
        except MatchdayRepositoryError as exc:
            assert str(exc) == "OBSERVATION_IDENTITY_CONFLICT"
        else:
            raise AssertionError(f"changed {field} must fail closed")


def test_fixture_identity_persists_provider_fixture_before_team_crosswalk() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = MatchdayRuntimeRepository(engine=engine)
    payload = _fixtures_payload()
    capture = endpoint_capture_contract(
        endpoint="fixtures",
        params={"league": "113", "season": "2026", "from": "2026-07-20", "to": "2026-08-03"},
        requested_at=NOW,
        provider_captured_at=NOW + timedelta(seconds=1),
        status_code=200,
        elapsed_ms=20,
        payload=payload,
        competition_id="allsvenskan",
        attempt=1,
    )
    repository.insert_endpoint_capture(capture)
    identity_body = {
        "fixture_id": "api_football:1494224",
        "provider": "api_football",
        "provider_fixture_id": "1494224",
        "competition_id": "allsvenskan",
        "provider_league_id": "113",
        "season": "2026",
        "kickoff_utc": KICKOFF.isoformat(),
        "fixture_status": "NS",
        "home_provider_team_id": "364",
        "away_provider_team_id": "367",
        "home_w2_team_id": None,
        "away_w2_team_id": None,
        "team_identity_status": "REVIEW_REQUIRED",
        "raw_payload_sha256": str(capture["raw_payload_sha256"]),
        "endpoint_capture_id": str(capture["capture_id"]),
        "captured_at": (NOW + timedelta(seconds=1)).isoformat(),
        "payload": payload["response"][0],
        "schema_version": "MatchdayFixtureIdentityV1",
    }
    row = {**identity_body, "identity_hash": stable_hash(identity_body)}

    assert repository.upsert_fixture_identities_with_business_changes([row]) == (
        1,
        ["api_football:1494224"],
    )
    assert repository.upsert_fixture_identities_with_business_changes([row]) == (0, [])
    with Session(engine) as session:
        stored = session.get(MatchdayFixtureIdentityModel, "api_football:1494224")
        assert stored is not None
        assert stored.home_w2_team_id is None
        assert stored.away_w2_team_id is None
        assert stored.team_identity_status == "REVIEW_REQUIRED"
        assert stored.endpoint_capture_id == str(capture["capture_id"])

    conflict = {
        **row,
        "away_provider_team_id": "999999",
        "identity_hash": stable_hash({**identity_body, "away_provider_team_id": "999999"}),
    }
    try:
        repository.insert_fixture_identities([conflict])
    except MatchdayRepositoryError as exc:
        assert str(exc) == "FIXTURE_IDENTITY_CONFLICT"
    else:
        raise AssertionError("fixture identity conflict must fail closed")


def test_fixture_identity_upsert_preserves_reviewed_mapping_and_updates_capture() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = MatchdayRuntimeRepository(engine=engine)
    payload = _fixtures_payload()
    first_capture = endpoint_capture_contract(
        endpoint="fixtures",
        params={"league": "113", "season": "2026", "from": "2026-07-20", "to": "2026-08-03"},
        requested_at=NOW,
        provider_captured_at=NOW + timedelta(seconds=1),
        status_code=200,
        elapsed_ms=20,
        payload=payload,
        competition_id="allsvenskan",
        attempt=1,
    )
    second_capture = endpoint_capture_contract(
        endpoint="fixtures",
        params={"league": "113", "season": "2026", "from": "2026-07-20", "to": "2026-08-03"},
        requested_at=NOW + timedelta(seconds=30),
        provider_captured_at=NOW + timedelta(seconds=31),
        status_code=200,
        elapsed_ms=20,
        payload=payload,
        competition_id="allsvenskan",
        attempt=2,
    )
    repository.insert_endpoint_capture(first_capture)
    repository.insert_endpoint_capture(second_capture)
    identity_body = {
        "fixture_id": "api_football:1494224",
        "provider": "api_football",
        "provider_fixture_id": "1494224",
        "competition_id": "allsvenskan",
        "provider_league_id": "113",
        "season": "2026",
        "kickoff_utc": KICKOFF.isoformat(),
        "fixture_status": "NS",
        "home_provider_team_id": "364",
        "away_provider_team_id": "367",
        "home_w2_team_id": None,
        "away_w2_team_id": None,
        "team_identity_status": "REVIEW_REQUIRED",
        "raw_payload_sha256": str(first_capture["raw_payload_sha256"]),
        "endpoint_capture_id": str(first_capture["capture_id"]),
        "captured_at": (NOW + timedelta(seconds=1)).isoformat(),
        "payload": payload["response"][0],
        "schema_version": "MatchdayFixtureIdentityV1",
    }
    row = {**identity_body, "identity_hash": stable_hash(identity_body)}

    assert repository.insert_fixture_identities([row]) == 1
    with Session(engine) as session:
        stored = session.get(MatchdayFixtureIdentityModel, "api_football:1494224")
        assert stored is not None
        stored.home_w2_team_id = "w2:team:home"
        stored.away_w2_team_id = "w2:team:away"
        stored.team_identity_status = "PROVIDER_PRIMARY_READY"
        reviewed_hash = stored.identity_hash
        session.commit()

    incoming_body = {
        **identity_body,
        "raw_payload_sha256": str(second_capture["raw_payload_sha256"]),
        "endpoint_capture_id": str(second_capture["capture_id"]),
        "captured_at": (NOW + timedelta(seconds=31)).isoformat(),
    }
    incoming = {**incoming_body, "identity_hash": stable_hash(incoming_body)}

    assert repository.upsert_fixture_identities_with_business_changes([incoming]) == (1, [])
    with Session(engine) as session:
        stored = session.get(MatchdayFixtureIdentityModel, "api_football:1494224")
        assert stored is not None
        assert stored.home_w2_team_id == "w2:team:home"
        assert stored.away_w2_team_id == "w2:team:away"
        assert stored.team_identity_status == "PROVIDER_PRIMARY_READY"
        assert stored.endpoint_capture_id == str(second_capture["capture_id"])
        assert stored.captured_at.replace(tzinfo=UTC) == NOW + timedelta(seconds=31)
        assert stored.identity_hash != incoming["identity_hash"]
        assert stored.identity_hash != reviewed_hash

    changed_body = {
        **incoming_body,
        "kickoff_utc": (KICKOFF + timedelta(hours=1)).isoformat(),
        "fixture_status": "TBD",
        "captured_at": (NOW + timedelta(seconds=61)).isoformat(),
    }
    changed = {**changed_body, "identity_hash": stable_hash(changed_body)}
    assert repository.upsert_fixture_identities_with_business_changes([changed]) == (
        1,
        ["api_football:1494224"],
    )


def test_fixture_identity_same_capture_time_provenance_conflict_fails_closed() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = MatchdayRuntimeRepository(engine=engine)
    payload = _fixtures_payload()
    first_capture = endpoint_capture_contract(
        endpoint="fixtures",
        params={"league": "113", "season": "2026"},
        requested_at=NOW,
        provider_captured_at=NOW + timedelta(seconds=1),
        status_code=200,
        elapsed_ms=20,
        payload=payload,
        competition_id="allsvenskan",
        attempt=1,
    )
    second_capture = endpoint_capture_contract(
        endpoint="fixtures",
        params={"league": "113", "season": "2026"},
        requested_at=NOW + timedelta(seconds=10),
        provider_captured_at=NOW + timedelta(seconds=1),
        status_code=200,
        elapsed_ms=20,
        payload=payload,
        competition_id="allsvenskan",
        attempt=2,
    )
    repository.insert_endpoint_capture(first_capture)
    repository.insert_endpoint_capture(second_capture)
    identity_body = {
        "fixture_id": "api_football:1494224",
        "provider": "api_football",
        "provider_fixture_id": "1494224",
        "competition_id": "allsvenskan",
        "provider_league_id": "113",
        "season": "2026",
        "kickoff_utc": KICKOFF.isoformat(),
        "fixture_status": "NS",
        "home_provider_team_id": "364",
        "away_provider_team_id": "367",
        "home_w2_team_id": None,
        "away_w2_team_id": None,
        "team_identity_status": "REVIEW_REQUIRED",
        "raw_payload_sha256": str(first_capture["raw_payload_sha256"]),
        "endpoint_capture_id": str(first_capture["capture_id"]),
        "captured_at": (NOW + timedelta(seconds=1)).isoformat(),
        "payload": payload["response"][0],
        "schema_version": "MatchdayFixtureIdentityV1",
    }
    assert (
        repository.insert_fixture_identities(
            [{**identity_body, "identity_hash": stable_hash(identity_body)}]
        )
        == 1
    )

    conflict_body = {
        **identity_body,
        "endpoint_capture_id": str(second_capture["capture_id"]),
    }
    try:
        repository.insert_fixture_identities(
            [{**conflict_body, "identity_hash": stable_hash(conflict_body)}]
        )
    except MatchdayRepositoryError as exc:
        assert str(exc) == "CAPTURE_PROVENANCE_CONFLICT"
    else:
        raise AssertionError("same captured_at provenance conflict must fail closed")


def test_fixture_identity_older_replay_cannot_overwrite_latest_capture() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = MatchdayRuntimeRepository(engine=engine)
    payload = _fixtures_payload()
    older_capture = endpoint_capture_contract(
        endpoint="fixtures",
        params={"league": "113", "season": "2026"},
        requested_at=NOW,
        provider_captured_at=NOW + timedelta(seconds=1),
        status_code=200,
        elapsed_ms=20,
        payload=payload,
        competition_id="allsvenskan",
        attempt=1,
    )
    newer_capture = endpoint_capture_contract(
        endpoint="fixtures",
        params={"league": "113", "season": "2026"},
        requested_at=NOW + timedelta(seconds=30),
        provider_captured_at=NOW + timedelta(seconds=31),
        status_code=200,
        elapsed_ms=20,
        payload=payload,
        competition_id="allsvenskan",
        attempt=2,
    )
    repository.insert_endpoint_capture(older_capture)
    repository.insert_endpoint_capture(newer_capture)
    stored_body = {
        "fixture_id": "api_football:1494224",
        "provider": "api_football",
        "provider_fixture_id": "1494224",
        "competition_id": "allsvenskan",
        "provider_league_id": "113",
        "season": "2026",
        "kickoff_utc": KICKOFF.isoformat(),
        "fixture_status": "TBD",
        "home_provider_team_id": "364",
        "away_provider_team_id": "367",
        "home_w2_team_id": None,
        "away_w2_team_id": None,
        "team_identity_status": "REVIEW_REQUIRED",
        "raw_payload_sha256": str(newer_capture["raw_payload_sha256"]),
        "endpoint_capture_id": str(newer_capture["capture_id"]),
        "captured_at": (NOW + timedelta(seconds=31)).isoformat(),
        "payload": payload["response"][0],
        "schema_version": "MatchdayFixtureIdentityV1",
    }
    assert (
        repository.insert_fixture_identities(
            [{**stored_body, "identity_hash": stable_hash(stored_body)}]
        )
        == 1
    )

    replay_body = {
        **stored_body,
        "fixture_status": "NS",
        "endpoint_capture_id": str(older_capture["capture_id"]),
        "captured_at": (NOW + timedelta(seconds=1)).isoformat(),
        "home_w2_team_id": "w2:team:home",
        "team_identity_status": "PROVIDER_PRIMARY_READY",
    }
    assert (
        repository.insert_fixture_identities(
            [{**replay_body, "identity_hash": stable_hash(replay_body)}]
        )
        == 1
    )

    with Session(engine) as session:
        stored = session.get(MatchdayFixtureIdentityModel, "api_football:1494224")
        assert stored is not None
        assert stored.fixture_status == "TBD"
        assert stored.endpoint_capture_id == str(newer_capture["capture_id"])
        assert stored.captured_at.replace(tzinfo=UTC) == NOW + timedelta(seconds=31)
        assert stored.home_w2_team_id == "w2:team:home"
        assert stored.team_identity_status == "PROVIDER_PRIMARY_READY"


def _manifest_market_audit_fixture(
    rows: list[dict[str, object]], *, evaluated_at: datetime
) -> dict[str, object]:
    home = next(
        row
        for row in rows
        if row["canonical_market"] == "ASIAN_HANDICAP"
        and row["canonical_selection"] == "HOME"
    )
    away = next(
        row
        for row in rows
        if row["canonical_market"] == "ASIAN_HANDICAP"
        and row["canonical_selection"] == "AWAY"
    )
    pair = {
        "market": "ASIAN_HANDICAP",
        "line": "-0.25",
        "left": home,
        "right": away,
        "status": "COMPLETE",
        "freshness": freshness_status(
            [home, away],
            evaluated_at=evaluated_at,
            max_age_seconds=1800,
        ),
    }
    return {
        "independent_candidates": [pair],
        "integrity_status": "PASS",
        "audit_hash": "integration-market-audit-fixture",
    }


def _odds_payload() -> dict[str, object]:
    return {
        "parameters": {"fixture": "100"},
        "response": [
            {
                "fixture": {"id": "100"},
                "bookmakers": [
                    {
                        "id": "8",
                        "name": "Book",
                        "bets": [
                            {
                                "id": "1",
                                "name": "Match Winner",
                                "values": [
                                    {"value": "Home", "odd": "2.10"},
                                    {"value": "Draw", "odd": "3.30"},
                                    {"value": "Away", "odd": "3.60"},
                                ],
                            },
                            {
                                "id": "4",
                                "name": "Asian Handicap",
                                "values": [
                                    {"value": "Home -0.25", "odd": "1.91"},
                                    {"value": "Away 0.25", "odd": "1.95"},
                                ],
                            },
                            {
                                "id": "5",
                                "name": "Goals Over/Under",
                                "values": [
                                    {"value": "Over 2.5", "odd": "1.88"},
                                    {"value": "Under 2.5", "odd": "2.02"},
                                ],
                            },
                        ],
                    }
                ],
            }
        ],
    }


def _fixtures_payload() -> dict[str, object]:
    return {
        "parameters": {"league": "113", "season": "2026"},
        "response": [
            {
                "fixture": {
                    "id": 1494224,
                    "date": KICKOFF.isoformat(),
                    "status": {"short": "NS"},
                },
                "league": {"id": 113, "season": 2026},
                "teams": {
                    "home": {"id": 364, "name": "Home FC"},
                    "away": {"id": 367, "name": "Away FC"},
                },
            }
        ],
    }


def test_postponed_fixture_reschedules_its_checkpoint_plans() -> None:
    """A moved kickoff must re-date the plan, not be rejected as a conflict.

    plan_id is keyed on fixture x checkpoint x policy and excludes the kickoff,
    so a postponed match reuses the same rows. Treating the new time as a
    conflict left every checkpoint stranded on the original date: fixture
    1523198 moved from 2026-07-11 to 2026-08-18, kept eleven July plans marked
    MISSED, collected no odds at all, and offered a "next window" five weeks in
    the past.
    """

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = MatchdayRuntimeRepository(engine=engine)
    original = NOW
    moved = NOW + timedelta(days=38)

    def plan(kickoff: datetime, status: str) -> CheckpointPlan:
        return CheckpointPlan(
            competition_id="chinese_super_league",
            season="2026",
            fixture_id="api_football:1523198",
            checkpoint="T3_ODDS",
            kickoff_utc=kickoff,
            scheduled_at=kickoff - timedelta(hours=3),
            window_start=kickoff - timedelta(hours=3),
            window_end=kickoff - timedelta(hours=2, minutes=30),
            endpoints=("odds",),
            status=status,
            blockers=(),
        )

    repository.upsert_checkpoint_plan(plan(original, "PLANNED"))
    repository.upsert_checkpoint_plan(plan(original, "MISSED"))
    repository.upsert_checkpoint_plan(plan(moved, "PLANNED"))

    with Session(engine) as session:
        rows = list(session.scalars(select(MatchdayCheckpointPlanModel)))

    assert len(rows) == 1, "a reschedule reuses the row rather than forking it"
    row = rows[0]
    assert row.kickoff_utc.replace(tzinfo=UTC) == moved
    assert row.scheduled_at.replace(tzinfo=UTC) == moved - timedelta(hours=3)
    # The old MISSED verdict described a window that no longer exists, so the row
    # takes the new projection's verdict instead of lingering as a collection
    # failure on a date the fixture never had.
    assert row.status == "PLANNED"
    assert row.missed_at is None


def test_same_kickoff_with_a_different_schedule_is_still_a_conflict() -> None:
    """Only a moved kickoff earns the re-dating; anything else stays a conflict."""

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = MatchdayRuntimeRepository(engine=engine)

    def plan(scheduled_at: datetime) -> CheckpointPlan:
        return CheckpointPlan(
            competition_id="chinese_super_league",
            season="2026",
            fixture_id="api_football:1523199",
            checkpoint="T3_ODDS",
            kickoff_utc=NOW,
            scheduled_at=scheduled_at,
            window_start=scheduled_at,
            window_end=scheduled_at + timedelta(minutes=30),
            endpoints=("odds",),
            status="PLANNED",
            blockers=(),
        )

    repository.upsert_checkpoint_plan(plan(NOW - timedelta(hours=3)))
    with pytest.raises(MatchdayRepositoryError, match="CHECKPOINT_PLAN_CONFLICT"):
        repository.upsert_checkpoint_plan(plan(NOW - timedelta(hours=2)))


def test_reschedule_releases_a_claim_held_against_the_old_window() -> None:
    """An in-flight worker must not report a capture into the re-dated window."""

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = MatchdayRuntimeRepository(engine=engine)
    policy = competition_policies(load_matchday_policy())["allsvenskan"]
    original = KICKOFF
    moved = KICKOFF + timedelta(days=38)

    def projection(kickoff: datetime) -> CheckpointPlan:
        return next(
            item
            for item in build_checkpoint_plans(
                fixture_id="api_football:1523198",
                competition_id="allsvenskan",
                season="2026",
                kickoff_utc=kickoff,
                now=kickoff - timedelta(hours=25),
                policy=policy,
            )
            if item.checkpoint == "T24_ODDS"
        )

    plan = projection(original)
    plan_id = repository.upsert_checkpoint_plan(plan)
    claimed = repository.claim_due_checkpoint_plans(
        now=original - timedelta(hours=24),
        worker_id="odds-worker",
        limit=1,
    )
    assert claimed and claimed[0]["fixture_id"] == plan.fixture_id
    claim_token = str(claimed[0]["claim_token"])

    repository.upsert_checkpoint_plan(projection(moved))

    with pytest.raises(MatchdayRepositoryError, match="CHECKPOINT_CLAIM_TOKEN_MISMATCH"):
        repository.transition_checkpoint(
            fixture_id=plan.fixture_id,
            competition_id=plan.competition_id,
            season=plan.season,
            checkpoint=plan.checkpoint,
            policy_version=plan.policy_version,
            status="CAPTURED",
            capture_id="capture-from-the-old-window",
            claim_token=claim_token,
        )

    # All four claim fields must clear together.  claim_due_checkpoint_plans
    # requires claimed_at and claim_token to both be null, and the lease reaper
    # only runs where claim_expires_at is set, so a leftover claimed_at would
    # leave the re-dated plan unclaimable for the whole of its new window.
    with Session(engine) as session:
        row = session.get(MatchdayCheckpointPlanModel, plan_id)
        assert row is not None
        assert (row.claimed_at, row.claimed_by, row.claim_token, row.claim_expires_at) == (
            None,
            None,
            None,
            None,
        )

    reclaimed = repository.claim_due_checkpoint_plans(
        now=moved - timedelta(hours=24),
        worker_id="odds-worker-after-reschedule",
        limit=1,
    )
    assert [row["id"] for row in reclaimed] == [plan_id]


def _failed_plan_fixture(
    repository: MatchdayRuntimeRepository,
    *,
    fixture_id: str,
    kickoff: datetime,
) -> tuple[CheckpointPlan, str]:
    policy = competition_policies(load_matchday_policy())["allsvenskan"]
    plan = next(
        item
        for item in build_checkpoint_plans(
            fixture_id=fixture_id,
            competition_id="allsvenskan",
            season="2026",
            kickoff_utc=kickoff,
            now=kickoff - timedelta(hours=25),
            policy=policy,
        )
        if item.checkpoint == "T24_ODDS"
    )
    plan_id = repository.upsert_checkpoint_plan(plan)
    for status in ("DUE", "FAILED"):
        repository.transition_checkpoint(
            fixture_id=plan.fixture_id,
            competition_id=plan.competition_id,
            season=plan.season,
            checkpoint=plan.checkpoint,
            policy_version=plan.policy_version,
            status=status,
        )
    return plan, plan_id


def _reproject(plan: CheckpointPlan, kickoff: datetime, now: datetime) -> CheckpointPlan:
    policy = competition_policies(load_matchday_policy())["allsvenskan"]
    return next(
        item
        for item in build_checkpoint_plans(
            fixture_id=plan.fixture_id,
            competition_id=plan.competition_id,
            season=plan.season,
            kickoff_utc=kickoff,
            now=now,
            policy=policy,
        )
        if item.checkpoint == plan.checkpoint
    )


def test_failed_plan_without_provider_evidence_is_redated() -> None:
    """A failure that never reached the provider describes no window worth keeping.

    Nothing in production drives FAILED back to DUE, so a FAILED row left on the
    old kickoff is lost for good once its fixture moves -- the same permanent
    loss the re-dating exists to prevent.
    """

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = MatchdayRuntimeRepository(engine=engine)
    original = KICKOFF
    moved = KICKOFF + timedelta(days=38)
    plan, plan_id = _failed_plan_fixture(
        repository, fixture_id="api_football:failed-clean", kickoff=original
    )

    repository.upsert_checkpoint_plan(_reproject(plan, moved, moved - timedelta(hours=25)))

    with Session(engine) as session:
        row = session.get(MatchdayCheckpointPlanModel, plan_id)
        assert row is not None
        assert normalize_repo_time(row.kickoff_utc) == moved


def test_failed_plan_with_provider_evidence_stays_pinned_to_its_window() -> None:
    """A request that was actually sent belongs to the window it was sent for."""

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = MatchdayRuntimeRepository(engine=engine)
    original = KICKOFF
    moved = KICKOFF + timedelta(days=38)
    plan, plan_id = _failed_plan_fixture(
        repository, fixture_id="api_football:failed-with-evidence", kickoff=original
    )
    with Session(engine) as session:
        row = session.get(MatchdayCheckpointPlanModel, plan_id)
        assert row is not None
        row.capture_id = "capture-actually-sent"
        session.commit()

    repository.upsert_checkpoint_plan(_reproject(plan, moved, moved - timedelta(hours=25)))

    with Session(engine) as session:
        row = session.get(MatchdayCheckpointPlanModel, plan_id)
        assert row is not None
        assert normalize_repo_time(row.kickoff_utc) == original
        assert row.status == "FAILED"
        assert session.scalars(select(MatchdayCheckpointPlanRescheduleModel)).all() == []


def test_reschedule_records_the_window_it_overwrites() -> None:
    """The re-date overwrites the plan in place, so the old window is kept here.

    Endpoint captures and the checkpoint audit describe attempts, not the plan
    they were scheduled against, so without this row a re-dated plan loses every
    trace of the window it used to hold.
    """

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = MatchdayRuntimeRepository(engine=engine)
    original = KICKOFF
    moved = KICKOFF + timedelta(days=38)
    plan, plan_id = _failed_plan_fixture(
        repository, fixture_id="api_football:failed-audited", kickoff=original
    )
    with Session(engine) as session:
        before = session.get(MatchdayCheckpointPlanModel, plan_id)
        assert before is not None
        previous_scheduled_at = normalize_repo_time(before.scheduled_at)
        previous_attempt_count = int(before.attempt_count or 0)

    repository.upsert_checkpoint_plan(_reproject(plan, moved, moved - timedelta(hours=25)))

    with Session(engine) as session:
        audits = list(session.scalars(select(MatchdayCheckpointPlanRescheduleModel)))
        row = session.get(MatchdayCheckpointPlanModel, plan_id)
        assert row is not None

    assert len(audits) == 1
    audit = audits[0]
    assert audit.plan_id == plan_id
    assert audit.previous_status == "FAILED"
    assert normalize_repo_time(audit.previous_kickoff_utc) == original
    assert normalize_repo_time(audit.previous_scheduled_at) == previous_scheduled_at
    assert audit.previous_attempt_count == previous_attempt_count
    assert normalize_repo_time(audit.new_kickoff_utc) == moved
    # attempt_count spans windows by design: plan_id excludes the kickoff, so the
    # count belongs to the plan identity rather than to one window.  Resetting it
    # would also silently change which rows repair tooling selects on
    # attempt_count == 1.
    assert int(row.attempt_count or 0) == previous_attempt_count


@pytest.mark.parametrize(
    ("status", "redatable"),
    [
        ("PROVIDER_EMPTY", False),
        ("CONFLICT", False),
        ("SKIPPED_POLICY", True),
        ("SKIPPED_BUDGET", True),
    ],
)
def test_remaining_terminal_statuses_on_reschedule(status: str, redatable: bool) -> None:
    """The remaining terminal statuses, one row each.

    PROVIDER_EMPTY and CONFLICT already describe something that happened
    against the old window. The two SKIPPED verdicts record a decision not to
    collect and never reached the provider, so a window the fixture no longer
    has is not worth keeping them on.
    """

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = MatchdayRuntimeRepository(engine=engine)
    policy = competition_policies(load_matchday_policy())["allsvenskan"]
    original = KICKOFF
    moved = KICKOFF + timedelta(days=38)

    def projection(kickoff: datetime) -> CheckpointPlan:
        return next(
            item
            for item in build_checkpoint_plans(
                fixture_id=f"api_football:{status.lower()}",
                competition_id="allsvenskan",
                season="2026",
                kickoff_utc=kickoff,
                now=kickoff - timedelta(hours=25),
                policy=policy,
            )
            if item.checkpoint == "T24_ODDS"
        )

    plan = projection(original)
    plan_id = repository.upsert_checkpoint_plan(plan)
    repository.transition_checkpoint(
        fixture_id=plan.fixture_id,
        competition_id=plan.competition_id,
        season=plan.season,
        checkpoint=plan.checkpoint,
        policy_version=plan.policy_version,
        status="DUE",
    )
    repository.transition_checkpoint(
        fixture_id=plan.fixture_id,
        competition_id=plan.competition_id,
        season=plan.season,
        checkpoint=plan.checkpoint,
        policy_version=plan.policy_version,
        status=status,
        capture_id="capture-provider-empty" if status == "PROVIDER_EMPTY" else None,
    )

    repository.upsert_checkpoint_plan(projection(moved))

    with Session(engine) as session:
        row = session.get(MatchdayCheckpointPlanModel, plan_id)
        assert row is not None
        audits = list(session.scalars(select(MatchdayCheckpointPlanRescheduleModel)))

    expected = moved if redatable else original
    assert normalize_repo_time(row.kickoff_utc) == expected
    assert len(audits) == (1 if redatable else 0)
    if not redatable:
        assert row.status == status


def test_failed_with_only_a_link_row_stays_pinned() -> None:
    """A link row is provider evidence even when the plan carries no capture_id.

    The link table is what joins a plan to the endpoint capture it produced, so
    a FAILED row reachable from it did reach the provider.
    """

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = MatchdayRuntimeRepository(engine=engine)
    original = KICKOFF
    moved = KICKOFF + timedelta(days=38)
    plan, plan_id = _failed_plan_fixture(
        repository, fixture_id="api_football:failed-linked", kickoff=original
    )

    capture = endpoint_capture_contract(
        endpoint="odds",
        params={"fixture": plan.fixture_id},
        requested_at=original - timedelta(hours=24),
        provider_captured_at=original - timedelta(hours=24),
        status_code=500,
        elapsed_ms=10,
        payload=_odds_payload(),
        fixture_id=plan.fixture_id,
        competition_id=plan.competition_id,
        checkpoint=plan.checkpoint,
        attempt=1,
    )
    repository.insert_endpoint_capture(capture)
    with Session(engine) as session:
        session.add(
            MatchdayEndpointCapturePlanModel(
                link_hash=stable_hash(f"{capture['capture_id']}:{plan_id}:odds"),
                capture_id=str(capture["capture_id"]),
                plan_id=plan_id,
                endpoint="odds",
                link_status="LINKED",
                linked_at=original,
            )
        )
        session.commit()

    repository.upsert_checkpoint_plan(_reproject(plan, moved, moved - timedelta(hours=25)))

    with Session(engine) as session:
        row = session.get(MatchdayCheckpointPlanModel, plan_id)
        assert row is not None
        assert normalize_repo_time(row.kickoff_utc) == original
        assert row.status == "FAILED"
        assert session.scalars(select(MatchdayCheckpointPlanRescheduleModel)).all() == []
