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
