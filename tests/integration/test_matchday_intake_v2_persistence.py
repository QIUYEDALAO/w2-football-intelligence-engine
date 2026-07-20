from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from w2.infrastructure.database import Base
from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayCheckpointPlanModel,
    MatchdayEndpointCaptureModel,
    MatchdayEvidenceManifestModel,
)
from w2.matchday.intake_v2 import (
    build_checkpoint_plans,
    competition_policies,
    endpoint_capture_contract,
    load_matchday_policy,
    market_batch_audit,
    materialize_evidence_manifest,
    normalize_matchday_odds_payload,
    public_manifest_read,
    stable_hash,
)
from w2.matchday.repository import MatchdayRepositoryError, MatchdayRuntimeRepository

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
    audit = market_batch_audit(rows, evaluated_at=NOW, max_age_seconds=3600)
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
    )

    assert [item["checkpoint"] for item in due] == ["T24_ODDS"]
    assert first_claim[0]["claimed_by"] == "worker-a"
    assert first_claim[0]["attempt_count"] == 1
    assert second_claim == []
    with Session(engine) as session:
        row = session.get(MatchdayCheckpointPlanModel, first_claim[0]["id"])
        assert row is not None
        assert row.status == "CAPTURED"
        assert row.capture_id == "capture-1"


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
        market_audit=market_batch_audit(rows, evaluated_at=NOW, max_age_seconds=3600),
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
