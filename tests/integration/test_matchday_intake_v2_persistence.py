from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from w2.infrastructure.database import Base
from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayCheckpointPlanModel,
    MatchdayEndpointCaptureModel,
    MatchdayEndpointCapturePlanModel,
    MatchdayEvidenceManifestModel,
    MatchdayFixtureIdentityModel,
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

    assert repository.insert_fixture_identities([row]) == 1
    assert repository.insert_fixture_identities([row]) == 0
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

    assert repository.insert_fixture_identities([incoming]) == 1
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
